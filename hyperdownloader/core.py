"""
核心引擎入口模块

提供 HyperDownloader 主类，作为整个下载引擎的 Facade。
用户只需实例化该类即可使用全部功能。
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from .config_manager import AppConfig, load_config, save_config
from .downloader import TaskDownloader
from .enums import DownloadStatus, SchedulerPolicy
from .models import (
    DownloadConfig,
    DownloadProgress,
    DownloadResult,
    DownloadTask,
    Headers,
    ProxyConfig,
)
from .scheduler import DownloadScheduler
from .utils import format_bytes, format_speed, format_time, get_downloads_folder

logger = logging.getLogger("hyperdownloader")


class HyperDownloader:
    """
    HyperDownloader 核心引擎。

    支持从 config.json 读取配置::

        # 从配置文件加载
        dl = HyperDownloader.from_config("config.json")

        # 或手动指定参数（会覆盖配置文件中的值）
        dl = HyperDownloader(max_concurrent=5, config_path="config.json")

        # 编程方式修改配置
        dl.load_config("config.json")
        dl.debug = True
        dl.max_concurrent = 5
    """

    def __init__(
        self,
        max_concurrent: Optional[int] = None,
        policy: SchedulerPolicy = SchedulerPolicy.FIFO,
        global_speed_limit: Optional[int] = None,
        default_config: Optional[DownloadConfig] = None,
        config_path: Optional[str] = None,
    ):
        """
        Args:
            max_concurrent: 最大并发下载任务数（覆盖配置文件）
            policy: 任务调度策略
            global_speed_limit: 全局下载速度限制（覆盖配置文件）
            default_config: 默认下载配置
            config_path: 配置文件路径，None 则自动搜索
        """
        # 加载配置文件
        self._app_config: AppConfig = load_config(config_path)

        # 代码参数覆盖配置文件
        if max_concurrent is not None:
            self._app_config.max_concurrent = max_concurrent
        if global_speed_limit is not None:
            self._app_config.speed_limit = global_speed_limit

        self._default_config = default_config or DownloadConfig()
        self._scheduler = DownloadScheduler(
            max_concurrent=self._app_config.max_concurrent,
            policy=policy,
            global_speed_limit=self._app_config.speed_limit,
        )
        self._started = False
        self._setup_logging()

    @classmethod
    def from_config(cls, config_path: str = "config.json") -> "HyperDownloader":
        """从配置文件创建引擎实例"""
        return cls(config_path=config_path)

    # ── 配置管理 ──

    def load_config(self, config_path: Optional[str] = None) -> None:
        """重新加载配置文件"""
        self._app_config = load_config(config_path)
        self._apply_config()
        logger.info("配置已重新加载")

    def save_config(self, config_path: Optional[str] = None) -> str:
        """保存当前配置到文件"""
        return save_config(self._app_config, config_path)

    def _apply_config(self) -> None:
        """将 AppConfig 应用到引擎当前设置"""
        self._scheduler._max_concurrent = self._app_config.max_concurrent
        self._scheduler._rate_limiter.max_rate = self._app_config.speed_limit

    # ── 配置属性 ──

    @property
    def debug(self) -> bool:
        return self._app_config.debug

    @debug.setter
    def debug(self, value: bool) -> None:
        self._app_config.debug = value
        level = logging.DEBUG if value else logging.INFO
        logging.getLogger("hyperdownloader").setLevel(level)
        logger.info("调试模式: %s", "开启" if value else "关闭")

    @property
    def max_concurrent(self) -> int:
        return self._scheduler._max_concurrent

    @max_concurrent.setter
    def max_concurrent(self, value: int) -> None:
        self._scheduler._max_concurrent = max(1, value)
        self._app_config.max_concurrent = self._scheduler._max_concurrent

    @property
    def global_speed_limit(self) -> Optional[int]:
        return self._scheduler._rate_limiter.max_rate

    @global_speed_limit.setter
    def global_speed_limit(self, value: Optional[int]) -> None:
        self._scheduler._rate_limiter.max_rate = value
        self._app_config.speed_limit = value

    # ── 生命周期 ──

    def start(self) -> None:
        """启动引擎（启动调度器后台线程）"""
        if self._started:
            return
        self._scheduler.start()
        self._started = True
        logger.info("HyperDownloader 引擎已启动")

    def stop(self, cancel_pending: bool = False) -> None:
        """停止引擎"""
        self._scheduler.stop(cancel_pending=cancel_pending)
        self._started = False
        logger.info("HyperDownloader 引擎已停止")

    def wait_all(self, timeout: Optional[float] = None) -> None:
        """等待所有任务完成"""
        self._scheduler.wait_all(timeout=timeout)

    # ── 任务管理 ──

    def download(
        self,
        task: DownloadTask,
    ) -> str:
        """
        添加一个下载任务。

        Args:
            task: 下载任务对象

        Returns:
            任务 ID
        """
        if not self._started:
            self.start()

        # 确保保存目录存在
        os.makedirs(task.save_dir, exist_ok=True)

        return self._scheduler.enqueue(task)

    def download_many(self, tasks: list[DownloadTask]) -> list[str]:
        """批量添加下载任务"""
        return [self.download(t) for t in tasks]

    def pause(self, task_id: str) -> bool:
        """暂停指定任务"""
        return self._scheduler.pause_task(task_id)

    def resume(self, task_id: str) -> bool:
        """恢复指定任务"""
        return self._scheduler.resume_task(task_id)

    def cancel(self, task_id: str) -> bool:
        """取消指定任务"""
        return self._scheduler.cancel_task(task_id)

    # ── 查询 ──

    @property
    def active_tasks(self) -> list[DownloadTask]:
        return self._scheduler.get_active_tasks()

    @property
    def pending_tasks(self) -> list[DownloadTask]:
        return self._scheduler.get_pending_tasks()

    @property
    def completed_results(self) -> list[DownloadResult]:
        return self._scheduler.get_completed_results()

    @property
    def pending_count(self) -> int:
        return self._scheduler.pending_count

    @property
    def active_count(self) -> int:
        return self._scheduler.active_count

    @property
    def completed_count(self) -> int:
        return self._scheduler.completed_count

    # ── 回调 ──

    @property
    def on_task_complete(self) -> Optional[callable]:
        return self._scheduler.on_task_complete

    @on_task_complete.setter
    def on_task_complete(self, callback: Optional[callable]) -> None:
        self._scheduler.on_task_complete = callback

    @property
    def on_task_progress(self) -> Optional[callable]:
        return self._scheduler.on_task_progress

    @on_task_progress.setter
    def on_task_progress(self, callback: Optional[callable]) -> None:
        self._scheduler.on_task_progress = callback

    # ── 工具方法 ──

    @staticmethod
    def create_task(
        url: str,
        save_dir: str,
        filename: Optional[str] = None,
        priority: int = 0,
        expected_sha256: Optional[str] = None,
        on_progress=None,
        on_complete=None,
        **config_kwargs,
    ) -> DownloadTask:
        """
        快速创建一个 DownloadTask。

        Args:
            url: 下载地址
            save_dir: 保存目录
            filename: 文件名（None 则自动从 URL 推断）
            priority: 优先级（越大越优先）
            expected_sha256: 下载完成后校验 SHA256
            on_progress: 进度回调
            on_complete: 完成回调
            **config_kwargs: 覆盖 DownloadConfig 的字段

        Returns:
            DownloadTask 实例
        """
        config = DownloadConfig(**{
            k: v for k, v in config_kwargs.items()
            if hasattr(DownloadConfig, k)
        })
        return DownloadTask(
            url=url,
            save_dir=save_dir,
            filename=filename,
            config=config,
            on_progress=on_progress,
            on_complete=on_complete,
            priority=priority,
            expected_sha256=expected_sha256,
        )

    @staticmethod
    def format_size(size: float) -> str:
        return format_bytes(size)

    @staticmethod
    def format_speed(speed: float) -> str:
        return format_bytes(speed) + "/s"

    @staticmethod
    def format_time(seconds: float) -> str:
        return format_time(seconds)

    # ── 内部 ──

    @staticmethod
    def _setup_logging() -> None:
        """配置默认日志（仅首次）"""
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter(
                    "[%(levelname)s] %(name)s: %(message)s"
                )
            )
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
