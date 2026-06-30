"""
任务调度器模块

管理多个下载任务的排队、并发控制、暂停/恢复/取消。
支持多种调度策略（FIFO / LIFO / 优先级）。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from .downloader import TaskDownloader
from .enums import DownloadStatus, SchedulerPolicy
from .models import DownloadResult, DownloadTask
from .utils import RateLimiter

logger = logging.getLogger("hyperdownloader.scheduler")


class DownloadScheduler:
    """
    下载任务调度器。

    特性:
    - 并发上限控制
    - FIFO / LIFO / 优先级调度
    - 全局速率限制
    - 暂停 / 恢复 / 取消
    - 任务完成 / 失败自动回调
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        policy: SchedulerPolicy = SchedulerPolicy.FIFO,
        global_speed_limit: Optional[int] = None,
    ):
        """
        Args:
            max_concurrent: 最大并发下载任务数
            policy: 调度策略
            global_speed_limit: 全局速度限制（字节/秒）
        """
        self._max_concurrent = max_concurrent
        self._policy = policy
        self._rate_limiter = RateLimiter(global_speed_limit)

        # 队列
        self._pending: list[DownloadTask] = []  # 等待队列
        self._active: dict[str, TaskDownloader] = {}  # 运行中
        self._completed: list[DownloadResult] = []  # 已完成结果
        self._lock = threading.Lock()

        # 后台线程
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # 回调
        self._on_task_complete: Optional[callable] = None
        self._on_task_progress: Optional[callable] = None

    # ── 回调注册 ──

    @property
    def on_task_complete(self) -> Optional[callable]:
        return self._on_task_complete

    @on_task_complete.setter
    def on_task_complete(self, callback: Optional[callable]) -> None:
        """注册全局完成回调 callback(result: DownloadResult)"""
        self._on_task_complete = callback

    @property
    def on_task_progress(self) -> Optional[callable]:
        return self._on_task_progress

    @on_task_progress.setter
    def on_task_progress(self, callback: Optional[callable]) -> None:
        """注册全局进度回调 callback(progress: DownloadProgress)"""
        self._on_task_progress = callback

    # ── 队列管理 ──

    def enqueue(self, task: DownloadTask) -> str:
        """
        将一个下载任务加入队列。

        Returns:
            任务 ID
        """
        # 如果没设回调，沿用全局回调
        if not task.on_progress and self._on_task_progress:
            task.on_progress = self._on_task_progress
        if not task.on_complete and self._on_task_complete:
            task.on_complete = self._on_task_complete

        with self._lock:
            self._pending.append(task)
            logger.info("任务入队: %s [%s]", task.url, task.task_id)

        return task.task_id

    def enqueue_many(self, tasks: list[DownloadTask]) -> list[str]:
        """批量入队"""
        return [self.enqueue(t) for t in tasks]

    def pause_task(self, task_id: str) -> bool:
        """暂停指定任务"""
        with self._lock:
            dl = self._active.get(task_id)
        if dl:
            dl.pause()
            logger.info("任务已暂停: %s", task_id)
            return True
        # 如果还在队列中，标记为暂停
        with self._lock:
            for t in self._pending:
                if t.task_id == task_id:
                    t.status = DownloadStatus.PAUSED
                    return True
        return False

    def resume_task(self, task_id: str) -> bool:
        """恢复指定任务"""
        with self._lock:
            dl = self._active.get(task_id)
        if dl:
            dl.resume()
            logger.info("任务已恢复: %s", task_id)
            return True
        with self._lock:
            for t in self._pending:
                if t.task_id == task_id:
                    t.status = DownloadStatus.PENDING
                    return True
        return False

    def cancel_task(self, task_id: str) -> bool:
        """取消指定任务"""
        with self._lock:
            dl = self._active.get(task_id)
        if dl:
            dl.cancel()
            logger.info("任务已取消: %s", task_id)
            with self._lock:
                self._active.pop(task_id, None)
            return True
        with self._lock:
            for i, t in enumerate(self._pending):
                if t.task_id == task_id:
                    t.status = DownloadStatus.CANCELLED
                    self._pending.pop(i)
                    return True
        return False

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    @property
    def completed_count(self) -> int:
        with self._lock:
            return len(self._completed)

    def get_active_tasks(self) -> list[DownloadTask]:
        """获取所有正在下载的任务"""
        with self._lock:
            return [dl.task for dl in self._active.values()]

    def get_pending_tasks(self) -> list[DownloadTask]:
        with self._lock:
            return list(self._pending)

    def get_completed_results(self) -> list[DownloadResult]:
        with self._lock:
            return list(self._completed)

    # ── 生命周期 ──

    def start(self) -> None:
        """启动调度器后台线程"""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="scheduler",
            daemon=True,
        )
        self._thread.start()
        logger.info("调度器已启动 (max_concurrent=%d)", self._max_concurrent)

    def stop(self, cancel_pending: bool = False) -> None:
        """
        停止调度器。

        Args:
            cancel_pending: 是否取消所有等待中的任务
        """
        self._running = False
        self._stop_event.set()

        # 取消活跃任务
        with self._lock:
            for dl in list(self._active.values()):
                dl.cancel()
            self._active.clear()

        if cancel_pending:
            with self._lock:
                for t in self._pending:
                    t.status = DownloadStatus.CANCELLED
                self._pending.clear()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("调度器已停止")

    def wait_all(self, timeout: Optional[float] = None) -> None:
        """等待所有任务完成"""
        deadline = time.time() + timeout if timeout else None
        while True:
            with self._lock:
                if not self._pending and not self._active:
                    break
            if deadline and time.time() >= deadline:
                break
            time.sleep(0.5)

    # ── 内部调度循环 ──

    def _run_loop(self) -> None:
        """调度器主循环"""
        while self._running and not self._stop_event.is_set():
            self._dispatch()
            self._cleanup_completed()
            self._stop_event.wait(timeout=0.3)

    def _dispatch(self) -> None:
        """将等待中的任务调度到活跃槽位"""
        with self._lock:
            available = self._max_concurrent - len(self._active)
            if available <= 0 or not self._pending:
                return

            # 按策略选取任务
            candidates = self._select_candidates(available)

        for task in candidates:
            dl = TaskDownloader(task, global_rate_limiter=self._rate_limiter)
            with self._lock:
                self._active[task.task_id] = dl
            dl.start()
            logger.debug("任务开始下载: %s", task.task_id)

    def _select_candidates(self, count: int) -> list[DownloadTask]:
        """根据调度策略选取候选任务"""
        with self._lock:
            if self._policy == SchedulerPolicy.LIFO:
                # 后进先出
                selected = self._pending[-count:]
                self._pending = self._pending[:-count]
                return selected
            elif self._policy == SchedulerPolicy.PRIORITY:
                # 按优先级排序（高优先级在前）
                self._pending.sort(key=lambda t: (-t.priority, t.created_at))
                selected = self._pending[:count]
                self._pending = self._pending[count:]
                return selected
            else:
                # FIFO（默认）
                selected = self._pending[:count]
                self._pending = self._pending[count:]
                return selected

    def _cleanup_completed(self) -> None:
        """清理已完成/失败/取消的下载器"""
        with self._lock:
            finished_ids = [
                tid
                for tid, dl in self._active.items()
                if dl.status
                in (
                    DownloadStatus.COMPLETED,
                    DownloadStatus.FAILED,
                    DownloadStatus.CANCELLED,
                )
            ]
            for tid in finished_ids:
                dl = self._active.pop(tid)
                # 记录结果
                result = DownloadResult(
                    task_id=dl.task.task_id,
                    url=dl.task.url,
                    file_path=dl.task.file_path,
                    status=dl.status,
                    total_size=dl.progress.total_size,
                    elapsed=dl.progress.elapsed,
                    avg_speed=dl.progress.avg_speed,
                    error_message=dl.progress.error_message,
                    segments_count=dl.progress.segments_total,
                )
                self._completed.append(result)
                logger.info(
                    "任务结束: %s [%s]",
                    dl.task.url,
                    dl.status.name,
                )
