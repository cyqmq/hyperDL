"""
纯 CLI 下载工具 — 无任何 GUI 依赖

用法:
    python -m hyperdownloader.cli <URL>
    hyperdownloader-cli.exe <URL>
"""
from __future__ import annotations

import argparse
import os
import sys
import time

# 确保能找到 hyperdownloader 包
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from hyperdownloader.utils import get_downloads_folder  # noqa: E402
from hyperdownloader.models import DownloadTask, DownloadConfig  # noqa: E402
from hyperdownloader.downloader import TaskDownloader  # noqa: E402


def _format_size(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def _format_speed(bps: float) -> str:
    return f"{_format_size(bps)}/s"


def _format_time(seconds: float) -> str:
    seconds = int(seconds)
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def download(url: str, save_dir: str = "", filename: str = "",
             segments: int = 4, quiet: bool = False) -> int:
    """
    下载文件（纯 CLI，无 GUI 依赖）

    Args:
        url: 下载地址
        save_dir: 保存目录，默认系统下载文件夹
        filename: 文件名，默认从 URL 推断
        segments: 分片数
        quiet: 静默模式

    Returns:
        0 成功，1 失败
    """
    if not save_dir:
        save_dir = get_downloads_folder()
    os.makedirs(save_dir, exist_ok=True)

    config = DownloadConfig(max_segments=segments)
    task = DownloadTask(url=url, save_dir=save_dir, filename=filename or None,
                        config=config)

    last_progress = -1
    bar_len = 25

    def on_progress(p):
        nonlocal last_progress
        if quiet:
            return
        pct = p.progress
        speed = _format_speed(p.speed)
        eta = _format_time(p.eta) if p.eta > 0 else "--:--"
        done = _format_size(p.downloaded)
        total = _format_size(p.total_size) if p.total_size > 0 else "?"
        seg = f"{p.segments_completed}/{p.segments_total}"

        # 进度条
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r  下载 [{bar}] {pct:6.2f}%  {done:>8} / {total:<8}  "
              f"{speed:>10}  ETA {eta}  分片 {seg}  ", end="", flush=True)

    def on_complete(r):
        if not quiet:
            bar = "█" * bar_len
            print(f"\r  下载 [{bar}] {'100.00%':>8}  ✅ 完成")
            print(f"  文件: {r.file_path}")
            print(f"  大小: {_format_size(r.total_size)}")
            print(f"  耗时: {_format_time(r.elapsed)}")
            print(f"  速度: {_format_speed(r.avg_speed)}")

    task.on_progress = on_progress
    task.on_complete = on_complete

    if not quiet:
        print(f"  URL: {url}")
        print(f"  保存: {os.path.join(save_dir, task.filename)}")
        print(f"  分片: {segments}")
        print()

    dl = TaskDownloader(task)
    dl.start()

    while dl.is_running:
        time.sleep(0.3)

    dl.wait()
    return 0 if dl.status.name == "COMPLETED" else 1


def main():
    parser = argparse.ArgumentParser(
        prog="hyperdownloader-cli",
        description="HyperDownloader Core — 纯命令行下载工具（无 GUI 依赖）",
    )
    parser.add_argument("url", help="下载链接")
    parser.add_argument("-o", "--output", default="", help="保存目录（默认系统下载文件夹）")
    parser.add_argument("-n", "--filename", default="", help="文件名（默认从 URL 推断）")
    parser.add_argument("-s", "--segments", type=int, default=4, help="分片数（默认 4）")
    parser.add_argument("-q", "--quiet", action="store_true", help="静默模式")
    args = parser.parse_args()

    if not args.url:
        parser.print_help()
        sys.exit(1)

    sys.exit(download(args.url, args.output, args.filename, args.segments, args.quiet))


if __name__ == "__main__":
    main()
