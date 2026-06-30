"""
数据模型模块

定义下载任务、配置、进度、分片等核心数据结构。
所有模型均为纯 dataclass，不依赖任何 GUI 类型。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import urlparse

from .enums import DownloadStatus, SegmentStatus


# ──────────────────────────────────────────────
# 回调类型别名（完全解耦，仅传递数据）
# ──────────────────────────────────────────────
ProgressCallback = Callable[["DownloadProgress"], None]
"""进度回调: 接收 DownloadProgress 对象，无返回值"""


@dataclass
class Headers:
    """自定义 HTTP 请求头"""
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
    referer: Optional[str] = None
    cookies: Optional[str] = None
    extra: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, str]:
        d: dict[str, str] = {
            "User-Agent": self.user_agent,
        }
        if self.referer:
            d["Referer"] = self.referer
        if self.cookies:
            d["Cookie"] = self.cookies
        d.update(self.extra)
        return d


@dataclass
class ProxyConfig:
    """代理配置"""
    http: Optional[str] = None
    https: Optional[str] = None
    socks5: Optional[str] = None

    def to_dict(self) -> dict[str, str]:
        d: dict[str, str] = {}
        if self.http:
            d["http"] = self.http
        if self.https:
            d["https"] = self.https
        if self.socks5:
            d["socks5"] = self.socks5
        return d


@dataclass
class DownloadConfig:
    """下载配置（每个任务可选覆盖）"""
    # ── 并发 ──
    max_segments: int = 4
    """最大分片数（同时下载的线程数）"""

    # ── 重试 ──
    max_retries: int = 3
    """每个分片的最大重试次数"""
    retry_delay: float = 2.0
    """重试等待基秒数（指数退避）"""

    # ── 网络 ──
    timeout: float = 30.0
    """单次连接超时（秒）"""
    connect_timeout: float = 10.0
    """TCP 连接超时（秒）"""
    buffer_size: int = 8192
    """读写缓冲区大小（字节）"""
    speed_limit: Optional[int] = None
    """全局速度限制（字节/秒），None 表示不限速"""
    segment_speed_limits: dict[int, Optional[int]] = field(default_factory=dict)
    """各分片的独立速度限制 {分片索引: 字节/秒}，优先级高于 speed_limit"""

    # ── HTTP 头 / 代理 ──
    headers: Headers = field(default_factory=Headers)
    proxy: Optional[ProxyConfig] = None

    # ── 断点续传 ──
    resume: bool = True
    """是否启用断点续传"""
    temp_suffix: str = ".hdt"
    """临时文件后缀"""

    # ── 校验 ──
    verify_ssl: bool = True
    check_hash: bool = False
    """是否在下载完成后校验文件哈希"""


@dataclass
class DownloadSegment:
    """下载分片"""
    index: int
    start: int
    end: int
    downloaded: int = 0
    status: SegmentStatus = SegmentStatus.PENDING
    retries: int = 0
    speed: float = 0.0
    """当前分片瞬时速度 (bytes/s)"""

    @property
    def size(self) -> int:
        return self.end - self.start + 1

    @property
    def progress(self) -> float:
        if self.size == 0:
            return 100.0
        return round(self.downloaded / self.size * 100, 2)


@dataclass
class DownloadProgress:
    """
    下载进度快照（纯数据，可用于驱动任何 UI）
    GUI 层可基于此数据绘制进度条 / 状态文字
    """
    task_id: str
    url: str
    file_path: str
    status: DownloadStatus

    # ── 总量 ──
    total_size: int = 0
    downloaded: int = 0

    # ── 速度与时间 ──
    speed: float = 0.0
    """当前瞬时速度 (bytes/s)"""
    avg_speed: float = 0.0
    """平均速度 (bytes/s)"""
    elapsed: float = 0.0
    """已耗时间 (秒)"""
    eta: float = 0.0
    """预估剩余时间 (秒)"""

    # ── 分片 ──
    segments_total: int = 0
    segments_completed: int = 0
    segments_speed: list[float] = field(default_factory=list)
    """每个分片的当前速度 [bytes/s]，索引对应分片编号"""

    # ── 错误 ──
    error_message: str = ""

    @property
    def progress(self) -> float:
        if self.total_size <= 0:
            return 0.0
        return round(self.downloaded / self.total_size * 100, 2)

    @property
    def is_finished(self) -> bool:
        return self.status in (
            DownloadStatus.COMPLETED,
            DownloadStatus.FAILED,
            DownloadStatus.CANCELLED,
        )


@dataclass
class DownloadTask:
    """一个完整的下载任务"""
    url: str
    save_dir: str
    filename: Optional[str] = None
    config: DownloadConfig = field(default_factory=DownloadConfig)
    on_progress: Optional[ProgressCallback] = None
    on_complete: Optional[Callable[["DownloadResult"], None]] = None
    expected_sha256: Optional[str] = None
    """下载完成后校验 SHA256，不匹配则标记为失败"""

    # ── 内部字段（调度器使用）─
    task_id: str = ""
    priority: int = 0
    """数值越大优先级越高"""
    status: DownloadStatus = DownloadStatus.PENDING
    created_at: float = 0.0

    # 自动生成字段
    def __post_init__(self) -> None:
        import time
        import hashlib

        if not self.task_id:
            raw = f"{self.url}{time.time_ns()}"
            self.task_id = hashlib.md5(raw.encode()).hexdigest()[:12]
        if not self.filename:
            self.filename = self._guess_filename()
        if not self.created_at:
            self.created_at = time.time()

    def _guess_filename(self) -> str:
        """从 URL 猜测文件名"""
        path = urlparse(self.url).path
        name = os.path.basename(path)
        if not name or "." not in name:
            name = f"download_{self.task_id[:8]}"
        return name

    @property
    def file_path(self) -> str:
        return os.path.join(self.save_dir, self.filename or "unknown")

    @property
    def temp_path(self) -> str:
        return self.file_path + self.config.temp_suffix


@dataclass
class DownloadResult:
    """下载完成后的结果"""
    task_id: str
    url: str
    file_path: str
    status: DownloadStatus
    total_size: int = 0
    elapsed: float = 0.0
    avg_speed: float = 0.0
    error_message: str = ""
    segments_count: int = 0
