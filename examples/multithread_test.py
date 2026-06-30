"""
多线程验证测试 — 对分片 0 限速 50 KB/s，其他分片不限速

如果真的是多线程下载，会看到：
  - 分片 0 速度 ~50 KB/s（被限速）
  - 分片 1/2/3 速度 ~3~6 MB/s（全速）

如果只是伪多线程（实际串行），所有分片速度会相近或依次执行。
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hyperdownloader.utils import get_downloads_folder, format_bytes, format_speed, format_time
from hyperdownloader.models import DownloadTask, DownloadConfig
from hyperdownloader.downloader import TaskDownloader

DEFAULT_DOWNLOAD_DIR = get_downloads_folder()


def on_progress(p):
    """进度回调 — 显示总分片速度对比"""
    bar_len = 20
    filled = int(bar_len * p.progress / 100)
    bar = "█" * filled + "░" * (bar_len - filled)

    # 各分片速度详情
    seg_details = " | ".join(
        f"#{i}: {format_speed(s)}"
        for i, s in enumerate(p.segments_speed)
    )

    print(
        f"\r  总进度 [{bar}] {p.progress:5.1f}%  "
        f"总速度 {format_speed(p.speed)}  "
        f"分片 [{p.segments_completed}/{p.segments_total}]",
        end="", flush=True,
    )
    # 第二行：分片速度详情
    print(f"\n  {'':>4}{'─' * 50}")
    print(f"  {'':>4}{seg_details}")
    print(f"  {'':>4}{'─' * 50}", end="", flush=True)


def on_complete(r):
    print(f"\n  ✅ 下载完成")
    print(f"  文件: {r.file_path}")
    print(f"  大小: {format_bytes(r.total_size)}")
    print(f"  耗时: {format_time(r.elapsed)}")
    print(f"  平均速度: {format_speed(r.avg_speed)}")


def main():
    print("=" * 70)
    print("  HyperDownloader Core — 多线程验证测试")
    print("  ─────────────────────────────────────")
    print("  分片 0 限速 50 KB/s，其余不限速")
    print("  若为真多线程 → 分片0明显慢于其他")
    print("=" * 70)

    URL = "https://qqdl.gtimg.cn/qqfile/QQNT/9.9.31/release/092069d7/QQ_9.9.31_260528_x64_01.exe"

    # 配置：分片0限速 50 KB/s = 51200 bytes/s
    config = DownloadConfig(
        max_segments=4,
        segment_speed_limits={0: 51200},  # 仅分片0限速
    )

    task = DownloadTask(
        url=URL,
        save_dir=DEFAULT_DOWNLOAD_DIR,
        filename=f"QQ_multithread_test_{int(time.time())}.exe",
        config=config,
        on_progress=on_progress,
        on_complete=on_complete,
    )

    print(f"\n  文件: {task.filename}")
    print(f"  保存: {task.file_path}")
    print(f"  分片: {task.config.max_segments}")
    print(f"  限速: {config.segment_speed_limits}")
    print()

    dl = TaskDownloader(task)
    dl.start()

    while dl.is_running:
        time.sleep(1)

    dl.wait()
    print()


if __name__ == "__main__":
    main()
