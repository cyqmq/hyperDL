"""
REST API 服务器 — 直接使用 TaskDownloader，不经过调度器

提供 JSON API 供第三方前端（Web / 桌面 App）接入。

启动:
    python -m hyperdownloader.api_server [--port 8765]
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from hyperdownloader import DownloadTask, DownloadConfig, DownloadStatus
from hyperdownloader.downloader import TaskDownloader
from hyperdownloader.utils import get_downloads_folder
from hyperdownloader.config_manager import load_config

logger = logging.getLogger("hyperdownloader.api")
_STATIC_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools")
)

# ── 全局任务仓库（支持多任务并发下载）──
_tasks: dict[str, TaskDownloader] = {}       # 所有任务（运行中 + 排队中）
_tasks_lock = threading.Lock()
_max_concurrent = 5                           # 最大并发下载数
_pending_queue: list[dict] = []               # 排队等待的任务参数
_queue_lock = threading.Lock()
_queue_thread_running = False


def _start_task_directly(url: str, save_dir: str, filename: Optional[str] = None,
                         segments: int = 4, expected_sha256: Optional[str] = None) -> str:
    """直接启动一个下载任务（不排队）"""
    config = DownloadConfig(max_segments=segments)
    task = DownloadTask(
        url=url, save_dir=save_dir, filename=filename,
        config=config, expected_sha256=expected_sha256,
    )
    dl = TaskDownloader(task)
    with _tasks_lock:
        _tasks[task.task_id] = dl
    dl.start()
    logger.info("任务已启动: %s [%s]", url, task.task_id)
    return task.task_id


def _try_start_task(url: str, save_dir: str, filename: Optional[str] = None,
                    segments: int = 4, expected_sha256: Optional[str] = None) -> tuple[str, bool]:
    """
    尝试启动任务。如果并发数未满则立即启动，否则加入排队队列。

    Returns:
        (task_id, 是否立即启动)
    """
    with _tasks_lock:
        running = sum(1 for d in _tasks.values()
                      if d.status == DownloadStatus.RUNNING)
        if running < _max_concurrent:
            # 有可用槽位，直接启动
            return _start_task_directly(url, save_dir, filename, segments, expected_sha256), True

    # 并发已满，加入排队队列
    with _queue_lock:
        _pending_queue.append({
            "url": url, "save_dir": save_dir, "filename": filename,
            "segments": segments, "expected_sha256": expected_sha256,
        })
    logger.info("并发已满，任务排队: %s (运行中 %d)", url, running)
    _ensure_queue_worker()
    return "", False


def _ensure_queue_worker():
    """确保排队调度线程在运行"""
    global _queue_thread_running
    if _queue_thread_running:
        return
    _queue_thread_running = True
    t = threading.Thread(target=_queue_worker, daemon=True, name="api-queue")
    t.start()


def _queue_worker():
    """排队调度线程：监视频道，有空位就取出排队任务"""
    import time
    global _queue_thread_running
    try:
        while True:
            # 检查是否有空位
            with _tasks_lock:
                running = sum(1 for d in _tasks.values()
                              if d.status == DownloadStatus.RUNNING)
            # 清理已完成的任务
            _cleanup_finished()

            if running < _max_concurrent:
                with _queue_lock:
                    if _pending_queue:
                        item = _pending_queue.pop(0)
                        with _tasks_lock:
                            new_running = sum(1 for d in _tasks.values()
                                              if d.status == DownloadStatus.RUNNING)
                            if new_running < _max_concurrent:
                                _start_task_directly(
                                    item["url"], item["save_dir"], item["filename"],
                                    item["segments"], item["expected_sha256"],
                                )
                                continue
                            else:
                                # 又被占满了，放回去
                                _pending_queue.insert(0, item)

            if not _pending_queue:
                break  # 队列为空，结束线程

            time.sleep(1)
    finally:
        _queue_thread_running = False


def _cleanup_finished():
    """清理已结束的任务"""
    with _tasks_lock:
        finished = [
            tid for tid, dl in list(_tasks.items())
            if dl.status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED)
        ]
        for tid in finished:
            _tasks.pop(tid, None)


def _snapshot(dl: TaskDownloader) -> dict:
    """获取 TaskDownloader 的快照"""
    p = dl.progress
    return {
        "task_id": p.task_id,
        "url": p.url,
        "filename": os.path.basename(p.file_path),
        "status": p.status.name,
        "progress": p.progress,
        "downloaded": p.downloaded,
        "total_size": p.total_size,
        "speed": round(p.speed, 2),
        "avg_speed": round(p.avg_speed, 2),
        "elapsed": round(p.elapsed, 2),
        "eta": round(p.eta, 2) if p.eta > 0 else 0,
        "segments_total": p.segments_total,
        "segments_completed": p.segments_completed,
        "segments_speed": [round(s, 2) for s in p.segments_speed],
        "error": p.error_message,
        "file_path": p.file_path,
    }


# ═══════════════════════════════════════════════
#  HTTP Handler
# ═══════════════════════════════════════════════

class APIHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path.rstrip("/")
        try:
            if path == "/api/tasks":
                self._list_tasks()
            elif path.startswith("/api/tasks/"):
                self._get_task(path)
            elif path == "/api/stats":
                self._stats()
            elif path == "/api/config":
                self._get_config()
            else:
                self._serve_static()
        except Exception as e:
            self._send(500, {"error": str(e)})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path.rstrip("/")
        body = self._read_body()
        if body is None:
            return
        try:
            if path == "/api/tasks":
                self._create_task(body)
            elif path.endswith("/pause"):
                self._pause_task(path)
            elif path.endswith("/resume"):
                self._resume_task(path)
            elif path.endswith("/cancel"):
                self._cancel_task(path)
            else:
                self._send(404, {"error": "Not Found"})
        except Exception as e:
            self._send(500, {"error": str(e)})

    def do_OPTIONS(self):
        self._cors()
        self.send_response(204)
        self.end_headers()

    # ── 工具 ──

    def _read_body(self) -> Optional[dict]:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self._send(400, {"error": "Invalid JSON"})
            return None

    def _send(self, status: int, data):
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode())

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, fmt, *args):
        pass  # 静默日志，避免刷屏

    def _task_id_from_path(self, path: str) -> str:
        """从 /api/tasks/{id}/action 提取 task_id"""
        return path.split("/api/tasks/")[1].split("/")[0]

    # ── API 端点 ──

    def _list_tasks(self):
        """GET /api/tasks"""
        with _tasks_lock:
            items = [_snapshot(dl) for dl in _tasks.values()]
        with _queue_lock:
            queued = len(_pending_queue)
        running = sum(1 for t in items if t["status"] == "RUNNING")
        pending = sum(1 for t in items if t["status"] == "PENDING")
        paused = sum(1 for t in items if t["status"] == "PAUSED")
        completed = sum(1 for t in items if t["status"] == "COMPLETED")
        self._send(200, {
            "tasks": items,
            "count": len(items),
            "queue": {
                "running": running,
                "pending": pending,
                "paused": paused,
                "completed": completed,
                "queued": queued,
                "max_concurrent": _max_concurrent,
            },
        })

    def _get_task(self, path: str):
        """GET /api/tasks/{id}"""
        tid = self._task_id_from_path(path)
        with _tasks_lock:
            dl = _tasks.get(tid)
        if dl is None:
            self._send(404, {"error": "Task not found"})
        else:
            self._send(200, _snapshot(dl))

    def _create_task(self, body: dict):
        """POST /api/tasks"""
        url = body.get("url", "").strip()
        if not url:
            self._send(400, {"error": "Missing 'url' field"})
            return
        save_dir = body.get("save_dir") or get_downloads_folder()
        filename = body.get("filename")
        segments = body.get("max_segments", 4)
        expected_sha256 = body.get("expected_sha256")
        os.makedirs(save_dir, exist_ok=True)
        tid, immediate = _try_start_task(url, save_dir, filename, segments, expected_sha256)
        if immediate:
            self._send(201, {
                "task_id": tid, "url": url,
                "save_dir": save_dir, "filename": filename or "",
                "status": "RUNNING",
            })
        else:
            self._send(202, {
                "url": url,
                "message": "并发已满，任务已排队，有空位时自动开始",
                "status": "QUEUED",
            })

    def _pause_task(self, path: str):
        tid = self._task_id_from_path(path)
        with _tasks_lock:
            dl = _tasks.get(tid)
        if dl: dl.pause(); self._send(200, {"success": True})
        else: self._send(404, {"error": "Not found"})

    def _resume_task(self, path: str):
        tid = self._task_id_from_path(path)
        with _tasks_lock:
            dl = _tasks.get(tid)
        if dl: dl.resume(); self._send(200, {"success": True})
        else: self._send(404, {"error": "Not found"})

    def _cancel_task(self, path: str):
        tid = self._task_id_from_path(path)
        with _tasks_lock:
            dl = _tasks.pop(tid, None)
        if dl: dl.cancel(); self._send(200, {"success": True})
        else: self._send(404, {"error": "Not found"})

    def _stats(self):
        """GET /api/stats"""
        _cleanup_finished()
        with _tasks_lock:
            vals = list(_tasks.values())
        with _queue_lock:
            queued = len(_pending_queue)
        running = sum(1 for d in vals if d.status == DownloadStatus.RUNNING)
        pending = sum(1 for d in vals if d.status == DownloadStatus.PENDING)
        paused = sum(1 for d in vals if d.status == DownloadStatus.PAUSED)
        failed = sum(1 for d in vals if d.status == DownloadStatus.FAILED)
        completed = sum(1 for d in vals if d.status == DownloadStatus.COMPLETED)
        self._send(200, {
            "running": running, "pending": pending, "paused": paused,
            "failed": failed, "completed": completed, "total": len(vals),
            "queued": queued, "max_concurrent": _max_concurrent,
        })

    def _get_config(self):
        cfg = load_config()
        self._send(200, {
            "max_segments": cfg.max_segments,
            "speed_limit": cfg.speed_limit,
            "max_concurrent": cfg.max_concurrent,
            "debug": cfg.debug,
            "timeout": cfg.timeout,
            "verify_ssl": cfg.verify_ssl,
            "resume": cfg.resume,
        })

    # ── 静态文件 ──

    def _serve_static(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("", "/"):
            path = "/web_demo.html"
        file_path = os.path.normpath(os.path.join(_STATIC_DIR, path.lstrip("/")))
        if not file_path.startswith(_STATIC_DIR) or not os.path.isfile(file_path):
            self._send(404, {"error": "Not Found"})
            return
        ext = os.path.splitext(file_path)[1].lower()
        mime = {".html": "text/html; charset=utf-8", ".js": "application/javascript",
                ".css": "text/css", ".png": "image/png", ".ico": "image/x-icon"}
        self.send_response(200)
        self.send_header("Content-Type", mime.get(ext, "application/octet-stream"))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        with open(file_path, "rb") as f:
            self.wfile.write(f.read())


# ═══════════════════════════════════════════════
#  启动
# ═══════════════════════════════════════════════

def run_server(host: str = "127.0.0.1", port: int = 8765):
    server = HTTPServer((host, port), APIHandler)
    server.timeout = 0.5  # 定期检查 KeyboardInterrupt

    print(f"╔══════════════════════════════════════════════╗")
    print(f"║  HyperDownloader API Server                 ║")
    print(f"╠══════════════════════════════════════════════╣")
    print(f"║  🚀 服务已启动                               ║")
    print(f"║  🌐 Web 界面: http://{host}:{port}/           ║")
    print(f"║  📡 API 地址: http://{host}:{port}/api        ║")
    print(f"╚══════════════════════════════════════════════╝")
    print(f"  按 Ctrl+C 停止")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹  正在停止...")
    finally:
        with _tasks_lock:
            for dl in list(_tasks.values()):
                dl.cancel()
        server.server_close()
        print("✅ 已停止")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="HyperDownloader API Server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()
