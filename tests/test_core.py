"""核心引擎集成测试"""
import time
from hyperdownloader import (
    HyperDownloader,
    DownloadTask,
    DownloadStatus,
    SchedulerPolicy,
)


class TestHyperDownloader:
    def test_create_instance(self):
        dl = HyperDownloader(max_concurrent=5)
        assert dl.max_concurrent == 5
        assert dl.active_count == 0
        assert dl.pending_count == 0
        assert dl.completed_count == 0

    def test_start_stop(self):
        dl = HyperDownloader()
        dl.start()
        dl.stop()
        assert dl.active_count == 0

    def test_create_task_static(self):
        task = HyperDownloader.create_task(
            url="http://example.com/file.zip",
            save_dir="/tmp/downloads",
            filename="test.zip",
            priority=5,
        )
        assert task.url == "http://example.com/file.zip"
        assert task.filename == "test.zip"
        assert task.priority == 5

    def test_max_concurrent_setter(self):
        dl = HyperDownloader(max_concurrent=3)
        assert dl.max_concurrent == 3
        dl.max_concurrent = 10
        assert dl.max_concurrent == 10

    def test_global_speed_limit(self):
        dl = HyperDownloader(global_speed_limit=102400)
        assert dl.global_speed_limit == 102400
        dl.global_speed_limit = None
        assert dl.global_speed_limit is None

    def test_format_methods(self):
        assert "MB" in HyperDownloader.format_size(1048576)
        assert "/s" in HyperDownloader.format_speed(1024)
        assert isinstance(HyperDownloader.format_time(120), str)


class TestScheduler:
    def test_enqueue_and_status(self):
        dl = HyperDownloader(max_concurrent=2)
        dl.start()

        task = DownloadTask(
            url="http://example.com/file.zip",
            save_dir="/tmp",
        )
        task_id = dl.download(task)
        assert task_id is not None

        # 任务应该立即进入运行或等待状态
        time.sleep(0.3)
        total = dl.active_count + dl.pending_count
        assert total == 1

        dl.stop(cancel_pending=True)

    def test_pause_resume_cancel(self):
        dl = HyperDownloader(max_concurrent=1)
        dl.start()

        task = DownloadTask(
            url="http://example.com/file.zip",
            save_dir="/tmp",
        )
        task_id = dl.download(task)

        # 取消
        result = dl.cancel(task_id)
        assert result is True

        dl.stop()
