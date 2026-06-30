"""
配置文件使用示例

演示如何：
1. 从 config.json 加载配置
2. 在运行时修改配置
3. 保存配置到文件
4. 使用 debug 模式
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hyperdownloader import HyperDownloader, AppConfig, load_config, save_config
from hyperdownloader.utils import get_downloads_folder, format_bytes, format_speed, format_time
from hyperdownloader.models import DownloadTask
from hyperdownloader.downloader import TaskDownloader

DEFAULT_DOWNLOAD_DIR = get_downloads_folder()


def on_progress(p):
    bar = "█" * int(20 * p.progress / 100) + "░" * (20 - int(20 * p.progress / 100))
    print(
        f"\r  进度 [{bar}] {p.progress:6.2f}%  "
        f"{format_speed(p.speed):>10}  "
        f"分片 {p.segments_completed}/{p.segments_total}  ",
        end="", flush=True,
    )


def on_complete(r):
    status = "✅" if r.status.name == "COMPLETED" else "❌"
    print(f"\n  {status} {r.status.name}  |  {format_bytes(r.total_size)}  |  {format_time(r.elapsed)}")


def main():
    print("=" * 70)
    print("  HyperDownloader Core — 配置文件示例")
    print("=" * 70)

    # ── 方式 1: 从配置文件创建 ──
    print("\n  📋 方式 1: from_config() 读取 config.json")
    dl = HyperDownloader.from_config("config.json")
    print(f"     max_segments={dl._app_config.max_segments}")
    print(f"     speed_limit={dl._app_config.speed_limit}")
    print(f"     debug={dl.debug}")
    dl.stop()

    # ── 方式 2: 编程方式覆盖配置 ──
    print("\n  📋 方式 2: 代码参数覆盖配置文件")
    dl2 = HyperDownloader(
        max_concurrent=2,
        global_speed_limit=5_000_000,  # 5 MB/s
        config_path="config.json",
    )
    print(f"     max_concurrent={dl2.max_concurrent}")
    print(f"     speed_limit={dl2.global_speed_limit} bytes/s")
    dl2.stop()

    # ── 方式 3: 运行时修改配置 ──
    print("\n  📋 方式 3: 运行时修改配置")
    dl3 = HyperDownloader(config_path="config.json")
    dl3.max_concurrent = 6
    dl3.global_speed_limit = None   # 不限速
    dl3.debug = True                # 开启调试模式
    print(f"     max_concurrent={dl3.max_concurrent}")
    print(f"     speed_limit={dl3.global_speed_limit}")
    print(f"     debug={dl3.debug}")

    # 保存当前配置
    saved = dl3.save_config()
    print(f"     配置已保存: {saved}")
    dl3.stop()

    # ── 方式 4: 修改 config.json 后重载 ──
    print("\n  📋 方式 4: 修改文件后重新加载配置")
    dl4 = HyperDownloader()
    dl4.debug = True
    print(f"     加载前 debug={dl4.debug}")
    # 假设用户手动编辑了 config.json, 然后:
    dl4.load_config()
    print(f"     重载后 debug={dl4.debug}")
    dl4.stop()

    # ── 方式 5: 直接操作 AppConfig ──
    print("\n  📋 方式 5: 直接操作 AppConfig 对象")
    cfg = AppConfig(
        max_segments=8,
        speed_limit=10_000_000,
        debug=True,
        max_concurrent=5,
    )
    print(f"     segments={cfg.max_segments}")
    print(f"     speed={cfg.speed_limit} bytes/s")
    print(f"     debug={cfg.debug}")
    print(f"     concurrent={cfg.max_concurrent}")

    # ── 实际下载测试 ──
    print("\n" + "=" * 70)
    print("  🔄 实际下载测试 (debug 模式)")
    print("=" * 70)

    URL = "https://qqdl.gtimg.cn/qqfile/QQNT/9.9.31/release/092069d7/QQ_9.9.31_260528_x64_01.exe"

    task = DownloadTask(
        url=URL,
        save_dir=DEFAULT_DOWNLOAD_DIR,
        filename=f"QQ_config_test_{int(time.time())}.exe",
        on_progress=on_progress,
        on_complete=on_complete,
    )

    dl5 = HyperDownloader.from_config("config.json")
    dl5.debug = True

    # 直接用 TaskDownloader 避免调度器
    dt = TaskDownloader(task, global_rate_limiter=None)
    dt.start()
    while dt.is_running:
        time.sleep(0.5)
    dt.wait()
    dl5.stop()
    print()


if __name__ == "__main__":
    main()
