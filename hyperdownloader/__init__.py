"""
HyperDownloader Core — 高性能多线程下载引擎
=============================================
完全解耦，不依赖任何 GUI 框架，可无缝集成到其他 Python 项目中。
"""

from .enums import DownloadStatus, SegmentStatus, SchedulerPolicy
from .models import (
    DownloadTask,
    DownloadConfig,
    DownloadProgress,
    DownloadSegment,
    DownloadResult,
    ProxyConfig,
    Headers,
)
from .utils import format_bytes, format_speed, format_time, get_downloads_folder
from .core import HyperDownloader
from .config_manager import AppConfig, load_config, save_config

__all__ = [
    # 枚举
    "DownloadStatus",
    "SegmentStatus",
    "SchedulerPolicy",
    # 数据模型
    "DownloadTask",
    "DownloadConfig",
    "DownloadProgress",
    "DownloadSegment",
    "DownloadResult",
    "ProxyConfig",
    "Headers",
    # 核心入口
    "HyperDownloader",
    # 配置管理
    "AppConfig",
    "load_config",
    "save_config",
    # 工具
    "get_downloads_folder",
    "format_bytes",
    "format_speed",
    "format_time",
]

__version__ = "1.0.7"
