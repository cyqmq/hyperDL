"""
基础使用示例 — 单个文件下载（直接使用下载引擎，不经过调度器）
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hyperdownloader.utils import get_downloads_folder, format_bytes as format_size, format_speed, format_time
from hyperdownloader.models import DownloadTask
from hyperdownloader.downloader import TaskDownloader

DEFAULT_DOWNLOAD_DIR = get_downloads_folder()


def on_progress(p):
    """进度回调 — 实时进度条"""
    bar_len = 30
    filled = int(bar_len * p.progress / 100)
    bar = "█" * filled + "░" * (bar_len - filled)
    done = format_size(p.downloaded)
    total = format_size(p.total_size) if p.total_size > 0 else "?"
    speed = format_speed(p.speed)
    eta = format_time(p.eta) if p.eta > 0 else "--:--"
    seg = f"{p.segments_completed}/{p.segments_total}"

    print(
        f"\r  进度 [{bar}] {p.progress:6.2f}%  "
        f"{done:>8} / {total:<8}  "
        f"{speed:>10}  ETA {eta}  分片 {seg}  ",
        end="", flush=True,
    )


def on_complete(r):
    """完成回调"""
    bar = "█" * 30
    print(f"\r  进度 [{bar}] {'100.00%':>8}  ✅ 下载完成")
    print(f"  ├─ 文件: {r.file_path}")
    print(f"  ├─ 大小: {format_size(r.total_size)}")
    print(f"  ├─ 耗时: {format_time(r.elapsed)}")
    print(f"  └─ 速度: {format_speed(r.avg_speed)}")


def main():
    print("=" * 70)
    print("  HyperDownloader Core — 多线程下载引擎")
    print("=" * 70)

    URL = "https://qqdl.gtimg.cn/qqfile/QQNT/9.9.31/release/092069d7/QQ_9.9.31_260528_x64_01.exe"
    # 使用唯一文件名避免与已有文件冲突
    import time
    task = DownloadTask(url=URL, save_dir=DEFAULT_DOWNLOAD_DIR,
                        filename=f"QQ_test_{int(time.time())}.exe",
                        on_progress=on_progress, on_complete=on_complete)

    print(f"\n  文件: {task.filename}")
    print(f"  保存: {task.file_path}")
    print(f"  分片: {task.config.max_segments} 线程")
    print()

    # 直接使用 TaskDownloader（不经过调度器）
    print("  ▶ 正在连接服务器...", end="", flush=True)
    dl = TaskDownloader(task)
    dl.start()

    # 轮询等待完成（同时检查进度）
    while dl.is_running:
        time.sleep(0.5)

    dl.wait()
    print()


if __name__ == "__main__":
    main()
    main()
