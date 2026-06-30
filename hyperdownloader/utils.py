"""
工具函数模块

提供格式化、哈希校验、速度计算、系统路径获取等通用能力。
"""
from __future__ import annotations

import hashlib
import logging
import os
import sys
import threading
import time
from typing import Optional

logger = logging.getLogger("hyperdownloader")


# ──────────────────────────────────────────────
# 系统路径
# ──────────────────────────────────────────────

def get_downloads_folder() -> str:
    """
    获取系统真实的「下载」文件夹路径。

    在 Windows 上通过 SHGetKnownFolderPath API 获取，
    即使用户在文件夹属性中修改了默认位置也能正确返回。
    Linux / macOS 回退到 ``~/Downloads``。
    """
    if sys.platform == "win32":
        return _get_windows_downloads_folder()
    return os.path.expanduser("~/Downloads")


def _get_windows_downloads_folder() -> str:
    """Windows 专用：调用 Shell API 获取 Downloads 真实路径"""
    try:
        import ctypes
        import ctypes.wintypes
        import uuid as _uuid

        # KNOWNFOLDERID: {374DE290-123F-4565-9164-39C4925E467B}
        g = _uuid.UUID("{374DE290-123F-4565-9164-39C4925E467B}")
        GUID_TYPE = ctypes.c_char * 16
        guid = GUID_TYPE(*g.bytes_le)

        ptr = ctypes.c_wchar_p()
        func = ctypes.windll.shell32.SHGetKnownFolderPath
        func.argtypes = [
            ctypes.POINTER(GUID_TYPE),
            ctypes.wintypes.DWORD,
            ctypes.wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_wchar_p),
        ]
        func.restype = ctypes.wintypes.HRESULT

        hr = func(ctypes.byref(guid), 0, None, ctypes.byref(ptr))
        if hr == 0:
            path = ptr.value
            ctypes.windll.ole32.CoTaskMemFree(ptr)
            return path
    except Exception:
        logger.debug("无法通过 Shell API 获取 Downloads 路径，使用回退方案", exc_info=True)
    return os.path.expanduser("~/Downloads")


# ──────────────────────────────────────────────
# 格式化
# ──────────────────────────────────────────────

def format_bytes(size: float) -> str:
    """将字节数转为人类可读的字符串"""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def format_speed(bytes_per_sec: float) -> str:
    """将字节/秒格式化为可读速度"""
    return f"{format_bytes(bytes_per_sec)}/s"


def format_time(seconds: float) -> str:
    """将秒数格式化为 hh:mm:ss 或 mm:ss"""
    seconds = int(seconds)
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


# ──────────────────────────────────────────────
# 哈希校验
# ──────────────────────────────────────────────

def compute_file_hash(
    file_path: str,
    algorithm: str = "sha256",
    buffer_size: int = 65536,
    progress_callback: Optional[callable] = None,
) -> str:
    """
    计算文件哈希。

    Args:
        file_path: 文件路径
        algorithm: 哈希算法 (md5 / sha1 / sha256 / sha512)
        buffer_size: 读缓冲区大小
        progress_callback: 进度回调 callback(progress_float)

    Returns:
        十六进制哈希字符串
    """
    if algorithm not in ("md5", "sha1", "sha256", "sha512"):
        raise ValueError(f"不支持的哈希算法: {algorithm}")

    hasher = hashlib.new(algorithm)
    file_size = os.path.getsize(file_path)
    read_bytes = 0

    with open(file_path, "rb") as f:
        while chunk := f.read(buffer_size):
            hasher.update(chunk)
            read_bytes += len(chunk)
            if progress_callback and file_size > 0:
                progress_callback(read_bytes / file_size * 100)

    return hasher.hexdigest()


def verify_file_hash(
    file_path: str,
    expected_hash: str,
    algorithm: str = "sha256",
) -> bool:
    """验证文件哈希是否匹配（不区分大小写）"""
    actual = compute_file_hash(file_path, algorithm)
    return actual.lower() == expected_hash.lower()


# ──────────────────────────────────────────────
# 速度计算器（滑动窗口）
# ──────────────────────────────────────────────

class SpeedTracker:
    """
    基于滑动窗口的瞬时/平均速度计算器。
    线程安全。高频调用优化：每 8 次记录才裁剪一次窗口。
    """

    def __init__(self, window_seconds: float = 3.0):
        self._window = window_seconds
        self._lock = threading.Lock()
        self._samples: list[tuple[float, int]] = []
        self._total_bytes: int = 0
        self._start_time: float = time.time()
        self._counter: int = 0  # 裁剪节流计数器

    def record(self, bytes_count: int) -> None:
        """记录本次读取的字节数"""
        if bytes_count <= 0:
            return
        now = time.time()
        with self._lock:
            self._total_bytes += bytes_count
            self._samples.append((now, self._total_bytes))
            # 每 8 次记录裁剪一次，减少高频 O(n) 开销
            self._counter += 1
            if self._counter & 7 == 0:  # 每 8 次
                cutoff = now - self._window
                s = self._samples
                while len(s) > 2 and s[0][0] < cutoff:
                    s.pop(0)

    @property
    def instant_speed(self) -> float:
        """瞬时速度 (bytes/s)，基于滑动窗口"""
        with self._lock:
            if len(self._samples) < 2:
                return 0.0
            t1, b1 = self._samples[0]
            t2, b2 = self._samples[-1]
            elapsed = t2 - t1
            if elapsed <= 0:
                return 0.0
            return (b2 - b1) / elapsed

    @property
    def avg_speed(self) -> float:
        """平均速度 (bytes/s)"""
        with self._lock:
            elapsed = time.time() - self._start_time
            if elapsed <= 0:
                return 0.0
            return self._total_bytes / elapsed

    @property
    def total_bytes(self) -> int:
        with self._lock:
            return self._total_bytes

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()
            self._total_bytes = 0
            self._start_time = time.time()


# ──────────────────────────────────────────────
# 速率限制器（令牌桶）
# ──────────────────────────────────────────────

class RateLimiter:
    """
    基于令牌桶的速率限制器，用于控制下载速度。
    线程安全。
    """

    def __init__(self, max_bytes_per_sec: Optional[int]):
        """
        Args:
            max_bytes_per_sec: 每秒最大字节数，None 表示不限速
        """
        self._max_rate = max_bytes_per_sec
        self._tokens = 0.0
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, bytes_needed: int) -> None:
        """获取指定字节数的令牌，如果超出速率则阻塞等待"""
        rate = self._max_rate
        if rate is None or rate <= 0:
            return

        # 快速路径：先检查再获取锁
        with self._lock:
            self._refill()
            if self._tokens >= bytes_needed:
                self._tokens -= bytes_needed
                return

            # 令牌不足，计算等待时间
            deficit = bytes_needed - self._tokens
            wait = deficit / rate
            self._tokens = 0.0

        # 释放锁后等待（避免阻塞其他线程）
        if wait > 0:
            time.sleep(wait)

        with self._lock:
            self._refill()
            self._tokens = max(0.0, self._tokens - bytes_needed)

    def _refill(self) -> None:
        """补充令牌"""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self._tokens + elapsed * (self._max_rate or 0),
            (self._max_rate or 0) * 2,  # 最大爆发量
        )
        self._last_refill = now

    @property
    def max_rate(self) -> Optional[int]:
        return self._max_rate

    @max_rate.setter
    def max_rate(self, value: Optional[int]) -> None:
        with self._lock:
            self._max_rate = value
