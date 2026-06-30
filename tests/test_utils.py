"""工具函数单元测试"""
import pytest
from hyperdownloader.utils import (
    format_bytes,
    format_speed,
    format_time,
    SpeedTracker,
    RateLimiter,
)


class TestFormat:
    def test_format_bytes(self):
        assert format_bytes(0) == "0.00 B"
        assert format_bytes(1023) == "1023.00 B"
        assert format_bytes(1024) == "1.00 KB"
        assert format_bytes(1048576) == "1.00 MB"
        assert format_bytes(1073741824) == "1.00 GB"

    def test_format_speed(self):
        assert "/s" in format_speed(1024)

    def test_format_time(self):
        assert format_time(0) == "00:00"
        assert format_time(61) == "01:01"
        assert format_time(3661) == "01:01:01"


class TestSpeedTracker:
    def test_initial_speed(self):
        tracker = SpeedTracker(window_seconds=1.0)
        assert tracker.instant_speed == 0.0
        assert tracker.avg_speed == 0.0
        assert tracker.total_bytes == 0

    def test_record_increases_total(self):
        tracker = SpeedTracker()
        tracker.record(100)
        assert tracker.total_bytes == 100
        tracker.record(200)
        assert tracker.total_bytes == 300

    def test_reset(self):
        tracker = SpeedTracker()
        tracker.record(500)
        tracker.reset()
        assert tracker.total_bytes == 0
        assert tracker.avg_speed == 0.0


class TestRateLimiter:
    def test_no_limit(self):
        limiter = RateLimiter(None)
        # 不限速时应立即返回
        limiter.acquire(1000000)

    def test_with_limit(self):
        limiter = RateLimiter(max_bytes_per_sec=1000)
        # 小量数据应快速通过
        import time
        start = time.time()
        limiter.acquire(100)
        elapsed = time.time() - start
        assert elapsed < 0.5  # 100 bytes 不应该有明显的等待

    def test_max_rate_setter(self):
        limiter = RateLimiter(1000)
        assert limiter.max_rate == 1000
        limiter.max_rate = 2000
        assert limiter.max_rate == 2000
        limiter.max_rate = None
        assert limiter.max_rate is None
