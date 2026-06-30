"""
数据校验与代理配置示例
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hyperdownloader.utils import get_downloads_folder, format_bytes, format_speed, format_time
from hyperdownloader.models import DownloadTask, DownloadConfig, ProxyConfig, Headers
from hyperdownloader.downloader import TaskDownloader

DEFAULT_DOWNLOAD_DIR = get_downloads_folder()


def on_progress(p):
    bar_len = 25
    filled = int(bar_len * p.progress / 100)
    bar = "█" * filled + "░" * (bar_len - filled)
    print(
        f"\r  进度 [{bar}] {p.progress:6.2f}%  "
        f"{format_speed(p.speed):>10}  "
        f"ETA {format_time(p.eta) if p.eta > 0 else '--:--'}  "
        f"分片 {p.segments_completed}/{p.segments_total}  ",
        end="", flush=True,
    )


def on_complete(r):
    status = "✅" if r.status.name == "COMPLETED" else "❌"
    print(f"\n  {status} 状态: {r.status.name}")
    print(f"  文件: {r.file_path}")
    print(f"  大小: {format_bytes(r.total_size)}")
    print(f"  耗时: {format_time(r.elapsed)}")
    if r.error_message:
        print(f"  错误: {r.error_message}")


def main():
    print("=" * 70)
    print("  HyperDownloader Core — 数据校验 & 代理配置")
    print("=" * 70)

    # ── 示例 1: SHA256 校验 ──
    print("\n  ─── 示例 1: 带 SHA256 校验的下载 ───")
    print("  先下载文件，然后计算其 SHA256 用于后续校验\n")

    URL = "https://qqdl.gtimg.cn/qqfile/QQNT/9.9.31/release/092069d7/QQ_9.9.31_260528_x64_01.exe"
    ts = int(time.time())

    # 第一次下载：不校验，拿到真实哈希
    task1 = DownloadTask(
        url=URL,
        save_dir=DEFAULT_DOWNLOAD_DIR,
        filename=f"QQ_noverify_{ts}.exe",
        on_progress=on_progress,
        on_complete=on_complete,
    )
    dl1 = TaskDownloader(task1)
    dl1.start()
    while dl1.is_running:
        time.sleep(0.5)
    dl1.wait()

    if dl1.status.name != "COMPLETED":
        print("\n  ❌ 第一次下载失败，无法继续")
        return

    # 计算实际 SHA256
    import hashlib
    hasher = hashlib.sha256()
    with open(task1.file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    real_hash = hasher.hexdigest()
    print(f"\n  文件 SHA256: {real_hash}")
    print(f"  文件大小: {format_bytes(os.path.getsize(task1.file_path))}")

    # ── 示例 2: 传入 expected_sha256 校验 ──
    print("\n  ─── 示例 2: 传入 expected_sha256 自动校验 ───")
    print(f"  期望哈希: {real_hash[:16]}...\n")

    task2 = DownloadTask(
        url=URL,
        save_dir=DEFAULT_DOWNLOAD_DIR,
        filename=f"QQ_verify_{ts}.exe",
        expected_sha256=real_hash,  # <-- 传入正确哈希，应通过
        on_progress=on_progress,
        on_complete=on_complete,
    )
    dl2 = TaskDownloader(task2)
    dl2.start()
    while dl2.is_running:
        time.sleep(0.5)
    dl2.wait()

    # ── 示例 3: 错误哈希（模拟校验失败）──
    print("\n  ─── 示例 3: 故意传入错误哈希（应失败）───")
    print("  期望哈希: aaaa...（错误值）\n")

    task3 = DownloadTask(
        url=URL,
        save_dir=DEFAULT_DOWNLOAD_DIR,
        filename=f"QQ_wronghash_{ts}.exe",
        expected_sha256="aaaa" + "0" * 60,  # 错误哈希
        on_progress=on_progress,
        on_complete=on_complete,
    )
    dl3 = TaskDownloader(task3)
    dl3.start()
    while dl3.is_running:
        time.sleep(0.5)
    dl3.wait()

    # ── 示例 4: 代理配置 ──
    print("\n  ─── 示例 4: 代理配置示例 ───")
    print("  （此示例仅展示配置方式，实际代理地址需自行替换）\n")

    proxy_config = DownloadConfig(
        proxy=ProxyConfig(
            http="http://127.0.0.1:7890",
            https="http://127.0.0.1:7890",
            # socks5="socks5://127.0.0.1:1080",
        ),
        headers=Headers(
            user_agent="HyperDownloader/1.0",
            referer="https://example.com",
        ),
    )
    task4 = DownloadTask(
        url="https://example.com/file.zip",
        save_dir=DEFAULT_DOWNLOAD_DIR,
        config=proxy_config,
        on_complete=on_complete,
    )
    print(f"  代理: {task4.config.proxy}")
    print(f"  UA: {task4.config.headers.user_agent}")
    print(f"  任务已创建，取消执行（代理地址为示例）")
    # 不实际执行，仅为展示
    print()


if __name__ == "__main__":
    main()
