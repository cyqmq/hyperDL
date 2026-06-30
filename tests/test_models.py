"""数据模型单元测试"""
from hyperdownloader.enums import DownloadStatus, SegmentStatus, SchedulerPolicy
from hyperdownloader.models import (
    DownloadTask,
    DownloadConfig,
    DownloadProgress,
    DownloadSegment,
    DownloadResult,
    Headers,
    ProxyConfig,
)


class TestEnums:
    def test_download_status_values(self):
        assert DownloadStatus.PENDING is not None
        assert DownloadStatus.RUNNING is not None
        assert DownloadStatus.COMPLETED is not None
        assert DownloadStatus.FAILED is not None
        assert DownloadStatus.PAUSED is not None
        assert DownloadStatus.CANCELLED is not None

    def test_segment_status_values(self):
        assert SegmentStatus.PENDING is not None
        assert SegmentStatus.DOWNLOADING is not None
        assert SegmentStatus.COMPLETED is not None

    def test_scheduler_policy_values(self):
        assert SchedulerPolicy.FIFO is not None
        assert SchedulerPolicy.LIFO is not None
        assert SchedulerPolicy.PRIORITY is not None


class TestDownloadSegment:
    def test_size_calculation(self):
        seg = DownloadSegment(index=0, start=0, end=99)
        assert seg.size == 100

    def test_progress(self):
        seg = DownloadSegment(index=0, start=0, end=99, downloaded=50)
        assert seg.progress == 50.0


class TestDownloadProgress:
    def test_progress_percentage(self):
        p = DownloadProgress(
            task_id="test",
            url="http://example.com/file.zip",
            file_path="/tmp/file.zip",
            status=DownloadStatus.RUNNING,
            total_size=1000,
            downloaded=250,
        )
        assert p.progress == 25.0

    def test_progress_zero_total(self):
        p = DownloadProgress(
            task_id="test",
            url="http://example.com/file.zip",
            file_path="/tmp/file.zip",
            status=DownloadStatus.RUNNING,
            total_size=0,
            downloaded=0,
        )
        assert p.progress == 0.0

    def test_is_finished(self):
        for status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED):
            p = DownloadProgress(
                task_id="t", url="u", file_path="f",
                status=status,
            )
            assert p.is_finished


class TestDownloadTask:
    def test_auto_generate_task_id(self):
        task = DownloadTask(url="http://example.com/file.zip", save_dir="/tmp")
        assert len(task.task_id) == 12

    def test_auto_guess_filename(self):
        task = DownloadTask(url="http://example.com/file.zip", save_dir="/tmp")
        assert task.filename == "file.zip"

    def test_guess_filename_from_path(self):
        task = DownloadTask(
            url="http://example.com/downloads/myfile.tar.gz",
            save_dir="/tmp",
        )
        assert task.filename == "myfile.tar.gz"


class TestHeaders:
    def test_default_headers(self):
        h = Headers()
        d = h.to_dict()
        assert "User-Agent" in d

    def test_custom_headers(self):
        h = Headers(referer="http://example.com", cookies="session=abc")
        d = h.to_dict()
        assert d["Referer"] == "http://example.com"
        assert d["Cookie"] == "session=abc"

    def test_extra_headers(self):
        h = Headers(extra={"X-Custom": "value"})
        d = h.to_dict()
        assert d["X-Custom"] == "value"
