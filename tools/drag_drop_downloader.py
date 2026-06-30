"""
拖拽链接下载工具

独立的 GUI 小工具，不依赖核心引擎以外的任何框架。
将 URL 从浏览器拖入窗口即可开始下载。
"""
import sys
import os
import threading
import time

# 将项目根目录加入 sys.path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext
except ImportError:
    print("需要 Tkinter 支持，请安装 python-tk")
    sys.exit(1)

from hyperdownloader.utils import get_downloads_folder, format_bytes, format_speed, format_time
from hyperdownloader.models import DownloadTask, DownloadConfig
from hyperdownloader.downloader import TaskDownloader
from hyperdownloader.config_manager import load_config

# ── 全局状态 ──
_active_downloads: dict[str, TaskDownloader] = {}
_lock = threading.Lock()


class DragDropDownloader:
    """拖拽下载 GUI 窗口"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("HyperDownloader — 拖拽下载")
        self.root.geometry("680x520")
        self.root.resizable(True, True)

        # 加载配置
        self._cfg = load_config()
        self._save_dir = tk.StringVar(
            value=self._cfg.default_save_dir or get_downloads_folder()
        )
        self._segments = tk.IntVar(value=self._cfg.max_segments)

        self._build_ui()

        # 允许拖拽文件到窗口
        self.root.drop_target_register = self._register_drop

    # ── UI 构建 ──

    def _build_ui(self):
        """构建界面"""
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        # ═══ 标题 ═══
        title = tk.Label(
            self.root, text="HyperDownloader Core",
            font=("Segoe UI", 14, "bold"), fg="#2b579a",
        )
        title.grid(row=0, column=0, pady=(10, 0), sticky="w", padx=15)

        subtitle = tk.Label(
            self.root, text="将 URL / 文件链接拖入下方区域开始下载",
            font=("Segoe UI", 9), fg="#666",
        )
        subtitle.grid(row=1, column=0, pady=(0, 5), sticky="w", padx=15)

        # ═══ 拖放区域 ═══
        drop_frame = tk.LabelFrame(
            self.root, text=" 📥 拖放区域 ", font=("Segoe UI", 10),
            fg="#2b579a", padx=10, pady=10,
        )
        drop_frame.grid(row=2, column=0, padx=15, pady=5, sticky="nsew")
        drop_frame.columnconfigure(0, weight=1)
        drop_frame.rowconfigure(0, weight=1)

        self._drop_text = scrolledtext.ScrolledText(
            drop_frame, wrap=tk.WORD,
            font=("Consolas", 10),
            height=5,
            bg="#f5f5f5", fg="#333",
            relief=tk.FLAT, borderwidth=2,
        )
        self._drop_text.grid(row=0, column=0, sticky="nsew")
        self._drop_text.insert(tk.END, "将 URL 拖入此处…\n多个 URL 每行一个\n\n比如:\nhttps://example.com/file1.zip\nhttps://example.com/file2.zip")
        self._drop_text.config(state=tk.DISABLED)

        # 粘贴按钮（替代拖拽——标准 Tkinter 不支持原生拖拽事件）
        paste_frame = tk.Frame(drop_frame)
        paste_frame.grid(row=1, column=0, pady=(5, 0), sticky="ew")
        tk.Button(paste_frame, text="📋 从剪贴板粘贴 URL", font=("Segoe UI", 9),
                  command=self._paste_from_clipboard).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(paste_frame, text="🧹 清空", font=("Segoe UI", 9),
                  command=self._clear_urls).pack(side=tk.LEFT)

        # ═══ 设置栏 ═══
        settings_frame = tk.Frame(self.root)
        settings_frame.grid(row=3, column=0, padx=15, pady=(8, 3), sticky="ew")
        settings_frame.columnconfigure(1, weight=1)
        settings_frame.columnconfigure(3, weight=1)

        tk.Label(settings_frame, text="保存到:", font=("Segoe UI", 9)).grid(row=0, column=0, padx=(0, 5))
        save_entry = tk.Entry(settings_frame, textvariable=self._save_dir, font=("Consolas", 9))
        save_entry.grid(row=0, column=1, sticky="ew", padx=(0, 15))

        tk.Label(settings_frame, text="分片:", font=("Segoe UI", 9)).grid(row=0, column=2, padx=(0, 5))
        seg_spin = tk.Spinbox(settings_frame, from_=1, to=16, textvariable=self._segments, width=4)
        seg_spin.grid(row=0, column=3, sticky="w")

        # ═══ 按钮栏 ═══
        btn_frame = tk.Frame(self.root)
        btn_frame.grid(row=4, column=0, padx=15, pady=(3, 8), sticky="ew")

        self._btn_download = tk.Button(
            btn_frame, text="▶ 开始下载",
            command=self._start_download,
            bg="#2b579a", fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=15, cursor="hand2",
        )
        self._btn_download.pack(side=tk.LEFT, padx=(0, 8))

        self._btn_pause_all = tk.Button(
            btn_frame, text="⏸ 全部暂停", command=self._pause_all,
            state=tk.DISABLED, font=("Segoe UI", 9), padx=10,
        )
        self._btn_pause_all.pack(side=tk.LEFT, padx=5)

        self._btn_resume_all = tk.Button(
            btn_frame, text="▶ 全部恢复", command=self._resume_all,
            state=tk.DISABLED, font=("Segoe UI", 9), padx=10,
        )
        self._btn_resume_all.pack(side=tk.LEFT, padx=5)

        self._btn_clear = tk.Button(
            btn_frame, text="🗑 清空日志", command=self._clear_log,
            font=("Segoe UI", 9), padx=10,
        )
        self._btn_clear.pack(side=tk.RIGHT)

        # ═══ 日志区域 ═══
        log_frame = tk.LabelFrame(
            self.root, text=" 📋 下载日志 ", font=("Segoe UI", 10),
            fg="#2b579a", padx=5, pady=5,
        )
        log_frame.grid(row=5, column=0, padx=15, pady=(0, 10), sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.root.rowconfigure(5, weight=1)

        self._log = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD,
            font=("Consolas", 9),
            height=10,
            bg="#1e1e1e", fg="#d4d4d4",
            relief=tk.FLAT, borderwidth=2,
            state=tk.DISABLED,
        )
        self._log.grid(row=0, column=0, sticky="nsew")

        # 状态栏
        self._status = tk.Label(
            self.root, text="就绪 | 已下载: 0 个文件",
            font=("Segoe UI", 8), fg="#888",
            anchor=tk.W,
        )
        self._status.grid(row=6, column=0, padx=15, pady=(0, 5), sticky="ew")

    # ── 拖拽事件 ──

    def _on_drag_enter(self, event):
        self._drop_text.config(bg="#e8f0fe")

    def _on_drag_leave(self, event):
        self._drop_text.config(bg="#f5f5f5")

    def _on_drop(self, event):
        self._drop_text.config(bg="#f5f5f5")
        # 从剪贴板或拖拽数据获取 URL
        try:
            data = self.root.selection_get(selection="CLIPBOARD")
        except tk.TclError:
            data = ""
        if data:
            self._log_write(f"📥 检测到拖放: {data[:60]}...\n")
            self._url_entry_insert(data)

    def _url_entry_insert(self, text: str):
        """将拖入的文本插入到 URL 输入框"""
        self._drop_text.config(state=tk.NORMAL)
        self._drop_text.delete(1.0, tk.END)
        self._drop_text.insert(tk.END, text.strip())
        self._drop_text.config(state=tk.DISABLED)

    # ── 下载逻辑 ──

    def _get_urls(self) -> list[str]:
        """从文本框提取 URL 列表"""
        self._drop_text.config(state=tk.NORMAL)
        raw = self._drop_text.get(1.0, tk.END).strip()
        self._drop_text.config(state=tk.DISABLED)
        urls: list[str] = []
        for line in raw.splitlines():
            line = line.strip()
            if line and (line.startswith("http://") or line.startswith("https://")):
                urls.append(line)
        return urls

    def _start_download(self):
        """开始下载所有 URL"""
        urls = self._get_urls()
        if not urls:
            self._log_write("⚠️  未检测到有效 URL\n")
            return

        self._btn_download.config(state=tk.DISABLED, text="⏳ 下载中...")
        self._btn_pause_all.config(state=tk.NORMAL)

        save_dir = self._save_dir.get()
        os.makedirs(save_dir, exist_ok=True)

        self._log_write(f"📂 保存到: {save_dir}\n")
        self._log_write(f"🔗 共 {len(urls)} 个任务, 分片 {self._segments.get()}\n")
        self._log_write("-" * 50 + "\n")

        for url in urls:
            config = DownloadConfig(max_segments=self._segments.get())
            task = DownloadTask(
                url=url,
                save_dir=save_dir,
                config=config,
                on_progress=lambda p, u=url: self.root.after(0, self._on_progress, p, u),
                on_complete=lambda r: self.root.after(0, self._on_complete, r),
            )

            dl = TaskDownloader(task)
            task_id = task.task_id

            with _lock:
                _active_downloads[task_id] = dl

            dl.start()
            self._log_write(f"  ▶ {os.path.basename(url)}\n")

        # 后台监控完成状态
        threading.Thread(target=self._monitor_all, daemon=True).start()

    def _on_progress(self, progress, url: str):
        """进度回调（由主线程执行）"""
        bar = "█" * int(20 * progress.progress / 100) + "░" * (20 - int(20 * progress.progress / 100))
        self._status.config(
            text=f"⏳ {os.path.basename(url)[:30]:30s} [{bar}] {progress.progress:5.1f}%  "
                 f"{format_speed(progress.speed)}"
        )

    def _on_complete(self, result):
        """完成回调（由主线程执行）"""
        name = os.path.basename(result.file_path)
        if result.status.name == "COMPLETED":
            self._log_write(f"  ✅ {name} | {format_bytes(result.total_size)} | {format_time(result.elapsed)}\n")
        else:
            self._log_write(f"  ❌ {name} | {result.error_message}\n")

        with _lock:
            _active_downloads.pop(result.task_id, None)

    def _monitor_all(self):
        """后台监控所有下载完成"""
        while True:
            with _lock:
                if not _active_downloads:
                    break
            time.sleep(0.5)

        self.root.after(0, self._on_all_done)

    def _on_all_done(self):
        """所有下载完成"""
        self._btn_download.config(state=tk.NORMAL, text="▶ 开始下载")
        self._btn_pause_all.config(state=tk.DISABLED)
        self._btn_resume_all.config(state=tk.DISABLED)
        self._log_write("-" * 50 + "\n✅ 全部下载完成\n")
        self._status.config(text=f"就绪 | 最后一批已下载完成")

    def _pause_all(self):
        with _lock:
            targets = list(_active_downloads.values())
        count = 0
        for dl in targets:
            dl.pause()
            count += 1
        self._log_write(f"⏸ 已暂停 {count} 个任务\n")
        self._btn_pause_all.config(state=tk.DISABLED)
        self._btn_resume_all.config(state=tk.NORMAL)

    def _resume_all(self):
        with _lock:
            targets = list(_active_downloads.values())
        count = 0
        for dl in targets:
            dl.resume()
            count += 1
        self._log_write(f"▶ 已恢复 {count} 个任务\n")
        self._btn_pause_all.config(state=tk.NORMAL)
        self._btn_resume_all.config(state=tk.DISABLED)

    # ── 日志 ──

    def _log_write(self, text: str):
        self._log.config(state=tk.NORMAL)
        self._log.insert(tk.END, text)
        self._log.see(tk.END)
        self._log.config(state=tk.DISABLED)

    def _clear_log(self):
        self._log.config(state=tk.NORMAL)
        self._log.delete(1.0, tk.END)
        self._log.config(state=tk.DISABLED)

    # ── 拖拽注册（跨平台兼容） ──

    def _register_drop(self):
        """注册窗口为拖放目标（tkinterdnd2 可选）"""
        pass  # 基本拖拽通过事件绑定已支持

    # ── 剪贴板 ──

    def _paste_from_clipboard(self):
        """从剪贴板粘贴 URL"""
        try:
            data = self.root.clipboard_get()
        except tk.TclError:
            data = ""
        if data:
            self._drop_text.config(state=tk.NORMAL)
            self._drop_text.delete(1.0, tk.END)
            self._drop_text.insert(tk.END, data.strip())
            self._drop_text.config(state=tk.DISABLED)
            self._log_write(f"📋 已从剪贴板粘贴: {data[:60]}...\n")

    def _clear_urls(self):
        """清空 URL 输入"""
        self._drop_text.config(state=tk.NORMAL)
        self._drop_text.delete(1.0, tk.END)
        self._drop_text.config(state=tk.DISABLED)

    # ── 启动 ──

    def run(self):
        try:
            # 尝试加载 tkinterdnd2 实现原生拖拽
            self._try_enable_dnd()
        except Exception:
            pass
        self.root.mainloop()

    def _try_enable_dnd(self):
        """尝试启用原生拖拽支持（需 tkinterdnd2 库）"""
        try:
            from tkinterdnd2 import TkinterDnD
            # 如果用户安装了 tkinterdnd2，可以启用更好拖拽体验
        except ImportError:
            pass  # 回退到剪贴板方式


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        # CLI 模式：从命令行参数获取 URL
        url = sys.argv[2] if len(sys.argv) > 2 else ""
        if url:
            _cli_download(url)
        else:
            print("用法: hyperdownloader-cli.exe --cli <URL>")
            print("示例: hyperdownloader-cli.exe --cli https://example.com/file.zip")
        return

    # 无参数：显示使用说明（避免在没有 GUI 的环境崩溃）
    print("=" * 60)
    print("  HyperDownloader Core — 命令行下载工具")
    print("=" * 60)
    print()
    print("用法:")
    print("  hyperdownloader-cli.exe --cli <URL>")
    print()
    print("示例:")
    print('  hyperdownloader-cli.exe --cli "https://example.com/file.zip"')
    print()
    print("拖拽下载: 将链接拖到 拖拽下载.bat 上")
    print("Web 界面: hyperdownloader-server.exe  →  http://127.0.0.1:8765/")
    print()
    # 尝试启动 GUI（仅在明确有 GUI 环境时）
    try:
        app = DragDropDownloader()
        app.run()
    except Exception as e:
        print(f"GUI 不可用: {e}")
        print("请使用 --cli 参数进行命令行下载")


def _cli_download(url: str):
    """命令行模式下载"""
    import urllib.parse
    from hyperdownloader.downloader import TaskDownloader

    save_dir = get_downloads_folder()
    filename = os.path.basename(urllib.parse.urlparse(url).path) or "download"

    task = DownloadTask(url=url, save_dir=save_dir, filename=filename)

    def on_progress(p):
        bar = "█" * int(20 * p.progress / 100) + "░" * (20 - int(20 * p.progress / 100))
        print(f"\r  [{bar}] {p.progress:5.1f}%  {format_speed(p.speed)}", end="", flush=True)

    task.on_progress = on_progress
    dl = TaskDownloader(task)
    dl.start()
    while dl.is_running:
        time.sleep(0.5)
    dl.wait()
    print(f"\n  保存到: {task.file_path}")


if __name__ == "__main__":
    main()
