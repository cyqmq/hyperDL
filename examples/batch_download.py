"""
批量下载示例 — 多任务管理与进度展示
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hyperdownloader.utils import get_downloads_folder

from hyperdownloader import HyperDownloader, DownloadTask, SchedulerPolicy


# 系统默认下载文件夹
DEFAULT_DOWNLOAD_DIR = get_downloads_folder()


def create_progress_callback(name: str):
    """为每个任务创建带标签的进度回调"""
    def callback(progress):
        bar = "█" * int(progress.progress / 5) + "░" * (20 - int(progress.progress / 5))
        print(
            f"\r[{name:20s}] {bar} {progress.progress:5.1f}% "
            f"{HyperDownloader.format_speed(progress.speed):>10s}",
            end="",
            flush=True,
        )
    return callback


def main():
    # 使用优先级调度策略
    downloader = HyperDownloader(
        max_concurrent=3,
        policy=SchedulerPolicy.PRIORITY,
    )

    urls = [
        ("https://speed.hetzner.de/100MB.bin", "100MB-test"),
        ("https://speed.hetzner.de/10MB.bin", "10MB-test"),
        ("https://speed.hetzner.de/1GB.bin", "1GB-test"),
    ]

    print(f"批量下载 {len(urls)} 个文件（并发数: {downloader.max_concurrent}）")
    print("=" * 70)

    tasks = []
    for i, (url, name) in enumerate(urls):
        task = DownloadTask(
            url=url,
            save_dir=DEFAULT_DOWNLOAD_DIR,
            filename=f"{name}.bin",
            priority=i,  # 最后一个优先级最高
            on_progress=create_progress_callback(name),
        )
        tasks.append(task)

    # 批量添加
    task_ids = downloader.download_many(tasks)
    print(f"任务已入队: {task_ids}\n")

    # 等待 3 秒后暂停第一个任务
    time.sleep(3)
    if task_ids:
        print(f"\n⏸️  暂停任务: {task_ids[0]}")
        downloader.pause(task_ids[0])

    # 再等 2 秒后恢复
    time.sleep(2)
    if task_ids:
        print(f"\n▶️  恢复任务: {task_ids[0]}")
        downloader.resume(task_ids[0])

    # 等待所有任务完成
    downloader.wait_all()
    print("\n\n" + "=" * 70)
    print("所有任务已完成！")

    # 打印结果
    results = downloader.completed_results
    for r in results:
        status = "✅" if r.status.name == "COMPLETED" else "❌"
        print(f"  {status} {r.url}")
        print(f"     保存到: {r.file_path}")
        print(f"     大小: {HyperDownloader.format_size(r.total_size)}")
        print(f"     平均速度: {HyperDownloader.format_speed(r.avg_speed)}")

    downloader.stop()


if __name__ == "__main__":
    main()
