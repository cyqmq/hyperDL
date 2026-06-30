"""
枚举定义模块
"""
from enum import Enum, auto


class DownloadStatus(Enum):
    """单个下载任务的生命周期状态"""

    PENDING = auto()        # 等待调度
    RUNNING = auto()        # 下载中
    PAUSED = auto()         # 已暂停
    COMPLETED = auto()      # 已完成
    FAILED = auto()         # 失败（可重试）
    CANCELLED = auto()      # 已取消


class SegmentStatus(Enum):
    """下载分片的状态"""

    PENDING = auto()        # 等待下载
    DOWNLOADING = auto()    # 下载中
    COMPLETED = auto()      # 已完成
    FAILED = auto()         # 失败
    RETRYING = auto()       # 重试中


class SchedulerPolicy(Enum):
    """任务调度策略"""

    FIFO = auto()           # 先进先出（默认）
    LIFO = auto()           # 后进先出
    PRIORITY = auto()       # 按优先级
