"""
分片下载模块

管理单个 HTTP Range 分片的下载，支持断点续传、重试、速率限制。
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

import requests

from .enums import SegmentStatus
from .models import DownloadConfig, DownloadSegment
from .utils import RateLimiter, SpeedTracker

logger = logging.getLogger("hyperdownloader.segment")


class SegmentDownloader:
    """
    单个分片的下载器，运行在独立线程中。
    """

    def __init__(
        self,
        segment: DownloadSegment,
        url: str,
        temp_path: str,
        config: DownloadConfig,
        rate_limiter: Optional[RateLimiter] = None,
        segment_rate_limiter: Optional[RateLimiter] = None,
    ):
        """
        Args:
            segment: 分片信息
            url: 下载地址
            temp_path: 临时文件路径
            config: 下载配置
            rate_limiter: 全局速率限制器
            segment_rate_limiter: 分片独立速率限制器（优先级高于 rate_limiter）
        """
        self.segment = segment
        self._url = url
        self._temp_path = temp_path
        self._config = config
        self._rate_limiter = segment_rate_limiter or rate_limiter
        self._speed_tracker = SpeedTracker()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._error: Optional[str] = None

    # ── 公开属性 ──

    @property
    def speed(self) -> float:
        return self._speed_tracker.instant_speed

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── 生命周期 ──

    def start(self) -> None:
        """在新线程中启动分片下载"""
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"seg-{self.segment.index}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """请求停止下载"""
        self._stop_event.set()

    def wait(self, timeout: Optional[float] = None) -> None:
        """等待线程结束"""
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    # ── 核心逻辑 ──

    def _run(self) -> None:
        """线程入口"""
        self.segment.status = SegmentStatus.DOWNLOADING
        retries = 0

        while retries <= self._config.max_retries:
            if self._stop_event.is_set():
                self.segment.status = SegmentStatus.PENDING
                return

            try:
                self._download_range()
                self.segment.status = SegmentStatus.COMPLETED
                return
            except requests.RequestException as e:
                retries += 1
                self.segment.retries = retries
                logger.warning(
                    "分片 %d 下载失败 (第 %d/%d 次): %s",
                    self.segment.index,
                    retries,
                    self._config.max_retries,
                    e,
                )
                if retries <= self._config.max_retries:
                    self.segment.status = SegmentStatus.RETRYING
                    # 指数退避
                    delay = self._config.retry_delay * (2 ** (retries - 1))
                    self._sleep(delay)
                else:
                    self.segment.status = SegmentStatus.FAILED
                    self._error = str(e)
                    logger.error(
                        "分片 %d 重试耗尽，下载失败: %s",
                        self.segment.index,
                        e,
                    )
                    return
            except Exception as e:
                self.segment.status = SegmentStatus.FAILED
                self._error = str(e)
                logger.exception("分片 %d 发生意外错误", self.segment.index)
                return

    def _download_range(self) -> None:
        """执行 HTTP Range 请求并写入临时文件"""
        headers = self._config.headers.to_dict()
        range_start = self.segment.start + self.segment.downloaded
        range_end = self.segment.end

        if range_start > range_end:
            # 已全部下载完成
            self.segment.downloaded = self.segment.size
            return

        headers["Range"] = f"bytes={range_start}-{range_end}"

        resp = requests.get(
            self._url,
            headers=headers,
            proxies=self._config.proxy.to_dict() if self._config.proxy else None,
            timeout=(self._config.connect_timeout, self._config.timeout),
            verify=self._config.verify_ssl,
            stream=True,
        )
        resp.raise_for_status()

        # 写入临时文件（分片独立偏移）
        lock = threading.Lock()
        with open(self._temp_path, "r+b") as f:
            f.seek(range_start)

            for chunk in resp.iter_content(chunk_size=self._config.buffer_size):
                if self._stop_event.is_set():
                    return

                if not chunk:
                    continue

                # 速率限制
                if self._rate_limiter:
                    self._rate_limiter.acquire(len(chunk))

                f.write(chunk)

                with lock:
                    self.segment.downloaded += len(chunk)
                    self._speed_tracker.record(len(chunk))
                    self.segment.speed = self._speed_tracker.instant_speed

    def _sleep(self, duration: float) -> None:
        """可中断的睡眠"""
        self._stop_event.wait(timeout=duration)
