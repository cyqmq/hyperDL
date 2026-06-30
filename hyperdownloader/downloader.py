"""
单任务下载器模块

管理一个下载任务的所有分片，协调多线程分段下载。
支持断点续传、进度回调、速率限制。
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from typing import Optional

import requests

from .enums import DownloadStatus, SegmentStatus
from .models import (
    DownloadConfig,
    DownloadProgress,
    DownloadResult,
    DownloadSegment,
    DownloadTask,
)
from .segment import SegmentDownloader
from .utils import RateLimiter
from .utils import RateLimiter, SpeedTracker

logger = logging.getLogger("hyperdownloader.downloader")


class TaskDownloader:
    """
    单任务下载器。

    负责将一个 URL 切分为多个分片，并发下载，合并文件，进度汇报。
    每个 TaskDownloader 实例对应一个 DownloadTask。
    """

    def __init__(
        self,
        task: DownloadTask,
        global_rate_limiter: Optional[RateLimiter] = None,
    ):
        self._task = task
        self._config = task.config
        self._rate_limiter = global_rate_limiter
        self._segments: list[DownloadSegment] = []
        self._segment_downloaders: list[SegmentDownloader] = []
        self._speed_tracker = SpeedTracker()
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._error: Optional[str] = None
        self._total_size: int = 0
        self._start_time: float = 0.0
        self._elapsed: float = 0.0

    # ── 公开属性 ──

    @property
    def task(self) -> DownloadTask:
        return self._task

    @property
    def progress(self) -> DownloadProgress:
        """生成当前进度的快照"""
        downloaded = sum(s.downloaded for s in self._segments)
        completed = sum(
            1 for s in self._segments if s.status == SegmentStatus.COMPLETED
        )

        now = time.time()
        elapsed = (now - self._start_time) if self._start_time > 0 else 0.0
        speed = downloaded / elapsed if elapsed > 0 and downloaded > 0 else 0.0

        return DownloadProgress(
            task_id=self._task.task_id,
            url=self._task.url,
            file_path=self._task.file_path,
            status=self._task.status,
            total_size=self._total_size,
            downloaded=downloaded,
            speed=speed,
            avg_speed=speed,
            elapsed=elapsed,
            eta=(self._total_size - downloaded) / speed if speed > 0 else 0.0,
            segments_total=len(self._segments),
            segments_completed=completed,
            segments_speed=[sd.speed for sd in self._segment_downloaders],
            error_message=self._error or "",
        )

    @property
    def status(self) -> DownloadStatus:
        return self._task.status

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── 生命周期 ──

    def start(self) -> None:
        """启动下载（新线程）"""
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"dl-{self._task.task_id[:8]}",
            daemon=True,
        )
        self._thread.start()

    def pause(self) -> None:
        """暂停下载"""
        self._task.status = DownloadStatus.PAUSED
        self._stop_event.set()
        for sd in self._segment_downloaders:
            sd.stop()

    def resume(self) -> None:
        """恢复下载"""
        if self._task.status != DownloadStatus.PAUSED:
            return
        self._task.status = DownloadStatus.RUNNING
        self.start()

    def cancel(self) -> None:
        """取消下载，清理临时文件"""
        self._task.status = DownloadStatus.CANCELLED
        self._stop_event.set()
        for sd in self._segment_downloaders:
            sd.stop()

        temp = self._task.temp_path
        if os.path.exists(temp):
            try:
                os.remove(temp)
            except OSError:
                pass

    def wait(self, timeout: Optional[float] = None) -> None:
        """等待下载线程结束"""
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    # ── 核心逻辑 ──

    def _run(self) -> None:
        """下载线程主逻辑"""
        self._task.status = DownloadStatus.RUNNING
        self._start_time = time.time()
        # 立即发出首次进度回调，让 UI 能第一时间响应
        self._report_progress()

        try:
            # Step 1: 探测文件大小 & 服务端能力
            self._probe_server()

            # Step 2: 初始化临时文件
            self._init_temp_file()

            # Step 3: 切分 & 启动分片下载
            self._split_and_download()

            # Step 4: 等待所有分片完成
            self._wait_segments()

            # Step 5: 合并 / 重命名文件
            self._finalize()

        except _SkipDownload:
            # 文件已存在且完整，正常跳过
            pass
        except Exception as e:
            self._task.status = DownloadStatus.FAILED
            self._error = str(e)
            logger.exception("任务 %s 下载失败", self._task.task_id)
            self._report_progress()
            self._report_complete()

    def _probe_server(self) -> None:
        """探测服务器，获取文件大小和 Range 支持

        使用 GET + stream=True 而非 HEAD，因为 HEAD 默认不追踪重定向，
        对于有 302 跳转的 URL（如 7-zip.org -> GitHub CDN）会拿不到实际文件大小。
        """
        headers = self._config.headers.to_dict()
        resp = requests.get(
            self._task.url,
            headers=headers,
            proxies=self._config.proxy.to_dict() if self._config.proxy else None,
            timeout=(self._config.connect_timeout, self._config.timeout),
            verify=self._config.verify_ssl,
            stream=True,
        )
        resp.raise_for_status()

        # 获取文件大小
        content_length = resp.headers.get("Content-Length")
        self._total_size = int(content_length) if content_length else 0

        # 是否支持 Range
        accept_ranges = resp.headers.get("Accept-Ranges", "").lower()
        self._support_range = (
            accept_ranges == "bytes" and self._total_size > 0
        )

        # 关闭探测请求的连接，后续 segment 会新建连接
        resp.close()

        # 检查是否已有完整文件（断点续传）
        if self._config.resume and os.path.exists(self._task.file_path):
            existing_size = os.path.getsize(self._task.file_path)
            if self._total_size > 0 and existing_size >= self._total_size:
                logger.info("文件已完整下载，跳过: %s", self._task.file_path)
                self._task.status = DownloadStatus.COMPLETED
                self._report_progress()
                self._report_complete()
                # 抛异常回到外层，但标记已完成
                raise _SkipDownload()

    def _init_temp_file(self) -> None:
        """初始化临时文件（快速预分配空间）"""
        if self._total_size <= 0:
            return

        temp_path = self._task.temp_path
        if os.path.exists(temp_path):
            if self._config.resume and os.path.getsize(temp_path) >= self._total_size:
                return
        else:
            # 使用 ftruncate 快速预分配，比 seek+write 快得多
            with open(temp_path, "wb") as f:
                f.truncate(self._total_size)

    def _split_and_download(self) -> None:
        """切分文件并启动各分片下载线程"""
        if self._total_size <= 0:
            # 不支持 Range 或无法获取大小 -> 单线程下载
            seg = DownloadSegment(index=0, start=0, end=0)
            self._segments = [seg]
            sd = SegmentDownloader(
                segment=seg,
                url=self._task.url,
                temp_path=self._task.temp_path,
                config=self._config,
                rate_limiter=self._rate_limiter,
                segment_rate_limiter=None,
            )
            self._segment_downloaders = [sd]
            sd.start()
            return

        # 判断分片数
        max_segments = self._config.max_segments
        if not self._support_range:
            max_segments = 1

        seg_size = self._total_size // max_segments
        segments: list[DownloadSegment] = []

        for i in range(max_segments):
            start = i * seg_size
            end = (i + 1) * seg_size - 1 if i < max_segments - 1 else self._total_size - 1
            seg = DownloadSegment(index=i, start=start, end=end)

            # 断点续传：恢复已下载量
            if self._config.resume and os.path.exists(self._task.temp_path):
                seg.downloaded = self._get_downloaded_range(start, end)

            segments.append(seg)

        self._segments = segments

        # 构建分片下载器（支持每分片独立限速）
        seg_limits = self._config.segment_speed_limits or {}
        self._segment_downloaders = []
        for s in segments:
            seg_rl: Optional[RateLimiter] = None
            limit = seg_limits.get(s.index)
            if limit is not None:
                seg_rl = RateLimiter(limit)
            self._segment_downloaders.append(
                SegmentDownloader(
                    segment=s,
                    url=self._task.url,
                    temp_path=self._task.temp_path,
                    config=self._config,
                    rate_limiter=self._rate_limiter,
                    segment_rate_limiter=seg_rl,
                )
            )

        # 启动所有分片
        for sd in self._segment_downloaders:
            sd.start()

    def _get_downloaded_range(self, start: int, end: int) -> int:
        """检查临时文件中该分片已下载了多少字节"""
        try:
            with open(self._task.temp_path, "rb") as f:
                f.seek(start)
                data = f.read(end - start + 1)
                # 从后往前数非零字节
                downloaded = 0
                for byte in reversed(data):
                    if byte != 0:
                        break
                    downloaded += 1
                return len(data) - downloaded
        except OSError:
            return 0

    def _wait_segments(self) -> None:
        """等待所有分片下载完成，期间汇报进度"""
        interval = 0.3
        while True:
            if self._stop_event.is_set():
                return

            all_done = all(
                sd.segment.status
                in (SegmentStatus.COMPLETED, SegmentStatus.FAILED)
                for sd in self._segment_downloaders
            )

            self._report_progress()

            if all_done:
                break

            self._stop_event.wait(timeout=interval)

        # 检查是否所有分片都成功
        all_success = all(
            sd.segment.status == SegmentStatus.COMPLETED
            for sd in self._segment_downloaders
        )
        if not all_success:
            self._task.status = DownloadStatus.FAILED
            failed_segs = [
                sd for sd in self._segment_downloaders
                if sd.segment.status == SegmentStatus.FAILED
            ]
            self._error = (
                f"{len(failed_segs)} 个分片下载失败"
            )

    def _finalize(self) -> None:
        """下载完成后重命名临时文件为目标文件，并校验哈希"""
        if self._task.status == DownloadStatus.CANCELLED:
            return

        if self._task.status == DownloadStatus.FAILED:
            self._report_progress()
            self._report_complete()
            return

        temp = self._task.temp_path
        dest = self._task.file_path

        # 单分片时，临时文件就是完整文件
        if os.path.exists(temp):
            try:
                if os.path.exists(dest):
                    os.remove(dest)
                os.rename(temp, dest)
            except OSError as e:
                self._task.status = DownloadStatus.FAILED
                self._error = f"文件重命名失败: {e}"
                self._report_progress()
                self._report_complete()
                return

        # ── SHA256 校验 ──
        expected = self._task.expected_sha256
        if expected:
            logger.info("正在校验 SHA256 ...")
            try:
                actual_hash = self._compute_sha256(dest)
                if actual_hash.lower() != expected.lower():
                    self._task.status = DownloadStatus.FAILED
                    self._error = (
                        f"SHA256 不匹配: 期望 {expected}, 实际 {actual_hash}"
                    )
                    logger.error(self._error)
                    # 删除损坏的文件
                    try:
                        os.remove(dest)
                    except OSError:
                        pass
                    self._report_progress()
                    self._report_complete()
                    return
                logger.info("SHA256 校验通过: %s", actual_hash)
            except Exception as e:
                self._task.status = DownloadStatus.FAILED
                self._error = f"SHA256 校验失败: {e}"
                logger.error(self._error)
                self._report_progress()
                self._report_complete()
                return

        self._task.status = DownloadStatus.COMPLETED
        self._elapsed = time.time() - self._start_time
        logger.info("下载完成: %s -> %s", self._task.url, dest)
        self._report_progress()
        self._report_complete()

    # ── 回调 ──

    def _report_progress(self) -> None:
        """触发进度回调"""
        if self._task.on_progress:
            try:
                self._task.on_progress(self.progress)
            except Exception:
                logger.warning("进度回调异常", exc_info=True)

    def _report_complete(self) -> None:
        """触发完成回调"""
        if self._task.on_complete:
            try:
                elapsed = time.time() - self._start_time
                downloaded = sum(s.downloaded for s in self._segments)
                result = DownloadResult(
                    task_id=self._task.task_id,
                    url=self._task.url,
                    file_path=self._task.file_path,
                    status=self._task.status,
                    total_size=self._total_size,
                    elapsed=elapsed,
                    avg_speed=downloaded / elapsed if elapsed > 0 else 0.0,
                    error_message=self._error or "",
                    segments_count=len(self._segments),
                )
                self._task.on_complete(result)
            except Exception:
                logger.warning("完成回调异常", exc_info=True)

    # ── 哈希校验 ──

    def _compute_sha256(self, file_path: str) -> str:
        """计算文件的 SHA256 哈希"""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()


class _SkipDownload(Exception):
    """内部异常：标记文件已存在无需下载"""
    pass
