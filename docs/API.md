# HyperDownloader Core — API 文档

> 版本: 1.0.2

## 目录

- [Python SDK](#python-sdk)
  - [HyperDownloader](#hyperdownloader-引擎)
  - [DownloadTask](#downloadtask-下载任务)
  - [DownloadConfig](#downloadconfig-配置)
  - [DownloadProgress](#downloadprogress-进度数据)
  - [TaskDownloader](#taskdownloader-直接下载器)
  - [config_manager](#config_manager-配置管理)
  - [utils](#utils-工具函数)
- [REST API](#rest-api-服务器)
  - [启动](#启动)
  - [端点列表](#端点列表)
  - [curl 示例](#curl-示例)
  - [第三方前端接入](#第三方前端接入)
- [拖拽下载工具](#拖拽下载工具)

---

## Python SDK

### HyperDownloader 引擎

核心入口类，提供调度器管理多个下载任务。

```python
from hyperdownloader import HyperDownloader

# 基本用法
dl = HyperDownloader(max_concurrent=3)
dl.start()

task = DownloadTask(url="...", save_dir="./downloads")
dl.download(task)
dl.wait_all()
dl.stop()
```

#### 从配置文件加载

```python
# 方式一：自动搜索 config.json
dl = HyperDownloader.from_config()

# 方式二：指定配置文件
dl = HyperDownloader.from_config("my_config.json")

# 方式三：代码参数覆盖配置文件
dl = HyperDownloader(max_concurrent=5, config_path="config.json")
```

#### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `max_concurrent` | `int` | 最大并发任务数 |
| `global_speed_limit` | `int \| None` | 全局速度限制 (bytes/s) |
| `debug` | `bool` | 调试模式开关 |
| `active_tasks` | `list[DownloadTask]` | 运行中的任务 |
| `pending_tasks` | `list[DownloadTask]` | 等待中的任务 |
| `completed_results` | `list[DownloadResult]` | 已完成的结果 |
| `active_count` | `int` | 运行中任务数 |
| `pending_count` | `int` | 等待中任务数 |
| `completed_count` | `int` | 已完成任务数 |

#### 方法

| 方法 | 说明 |
|------|------|
| `start()` | 启动引擎 |
| `stop(cancel_pending=False)` | 停止引擎 |
| `wait_all(timeout=None)` | 等待所有任务完成 |
| `download(task)` | 添加下载任务 |
| `download_many(tasks)` | 批量添加 |
| `pause(task_id)` | 暂停任务 |
| `resume(task_id)` | 恢复任务 |
| `cancel(task_id)` | 取消任务 |
| `load_config(path=None)` | 重新加载配置 |
| `save_config(path=None)` | 保存当前配置 |
| `create_task(url, save_dir, ...)` | 快速创建任务 |

---

### DownloadTask 下载任务

```python
from hyperdownloader import DownloadTask, DownloadConfig

task = DownloadTask(
    url="https://example.com/file.zip",
    save_dir="~/Downloads",
    filename="myfile.zip",              # 可选，默认从 URL 推断
    config=DownloadConfig(max_segments=4),
    priority=5,                          # 优先级调度
    expected_sha256="a1b2c3...",         # 下载后自动校验
    on_progress=my_progress_callback,    # 进度回调
    on_complete=my_complete_callback,    # 完成回调
)
```

#### expected_sha256 校验

下载完成后自动计算 SHA256，与期望值对比：

- ✅ 匹配 → 标记 `COMPLETED`
- ❌ 不匹配 → 标记 `FAILED`，自动删除损坏文件

```python
task = DownloadTask(url="...", save_dir="...", expected_sha256="abc123...")
```

---

### DownloadConfig 配置

```python
from hyperdownloader import DownloadConfig, Headers, ProxyConfig

config = DownloadConfig(
    # 并发
    max_segments=4,              # 分片数（线程数）

    # 重试
    max_retries=3,               # 最大重试次数
    retry_delay=2.0,             # 重试基秒（指数退避）

    # 网络
    timeout=30.0,                # 超时时间
    connect_timeout=10.0,        # 连接超时
    buffer_size=8192,            # 缓冲区大小
    speed_limit=500_000,         # 限速 500 KB/s

    # 分片独立限速（调试用）
    segment_speed_limits={0: 51200},  # 分片0限速50KB/s

    # HTTP
    headers=Headers(
        user_agent="MyApp/1.0",
        referer="https://example.com",
        cookies="session=abc",
    ),
    proxy=ProxyConfig(
        http="http://127.0.0.1:7890",
        https="http://127.0.0.1:7890",
    ),

    # 其他
    resume=True,                 # 断点续传
    verify_ssl=True,             # SSL 验证
    check_hash=False,            # 哈希校验
    temp_suffix=".hdt",          # 临时文件后缀
)
```

---

### DownloadProgress 进度数据

纯数据类，可用于驱动任何 GUI 框架。

```python
@dataclass
class DownloadProgress:
    task_id: str
    url: str
    file_path: str
    status: DownloadStatus       # PENDING / RUNNING / PAUSED / COMPLETED / FAILED / CANCELLED
    total_size: int              # 总大小 (bytes)
    downloaded: int              # 已下载 (bytes)
    speed: float                 # 当前速度 (bytes/s)
    avg_speed: float             # 平均速度 (bytes/s)
    elapsed: float               # 已耗时间 (s)
    eta: float                   # 预估剩余 (s)
    segments_total: int          # 总分片数
    segments_completed: int      # 已完成分片
    segments_speed: list[float]  # 各分片速度
    error_message: str           # 错误信息

    @property
    def progress(self) -> float:  # 0~100 百分比
    @property
    def is_finished(self) -> bool:  # 是否终结态
```

**GUI 集成示例（Tkinter）：**

```python
def on_progress(p):
    progress_bar["value"] = p.progress
    speed_label.config(text=f"{p.speed/1024:.1f} KB/s")
    status_label.config(text=p.status.name)
```

---

### TaskDownloader 直接下载器

绕过调度器，直接下载一个任务。适用于 API 服务器或单任务场景。

```python
from hyperdownloader.downloader import TaskDownloader
from hyperdownloader.models import DownloadTask

task = DownloadTask(url="...", save_dir="...")
dl = TaskDownloader(task)
dl.start()

# 轮询进度
while dl.is_running:
    time.sleep(0.5)
    p = dl.progress
    print(f"{p.progress:.1f}% - {p.speed/1024:.1f} KB/s")

dl.wait()
print(f"完成: {dl.status.name}")
```

---

### config_manager 配置管理

```python
from hyperdownloader import AppConfig, load_config, save_config

# 加载配置（自动搜索 config.json）
cfg = load_config()
print(cfg.max_segments)  # 4

# 直接操作配置对象
cfg = AppConfig(max_segments=8, debug=True, speed_limit=10_000_000)

# 保存配置
save_config(cfg, "my_config.json")
```

配置文件查找优先级：**显式路径 > 工作目录 `config.json` > `~/.hyperdownloader/config.json`**

---

### utils 工具函数

```python
from hyperdownloader.utils import (
    format_bytes,      # 1024 → "1.00 KB"
    format_speed,      # 1024 → "1.00 KB/s"
    format_time,       # 3661 → "01:01:01"
    get_downloads_folder,  # 获取系统真实下载目录
    compute_file_hash,     # 计算文件哈希
    verify_file_hash,      # 验证文件哈希
)
```

`get_downloads_folder()` 在 Windows 上使用 `SHGetKnownFolderPath` API，
即使修改了系统下载文件夹位置也能正确返回。

---

## REST API 服务器

基于 Python 标准库 `http.server`，**零额外依赖**。

### 启动

```bash
# 默认端口 8765
python -m hyperdownloader.api_server

# 指定端口
python -m hyperdownloader.api_server --port 8765 --host 127.0.0.1
```

启动后同时提供：
- Web 界面: `http://127.0.0.1:8765/`
- API 地址: `http://127.0.0.1:8765/api`

### 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/tasks` | 获取所有任务列表及状态 |
| `POST` | `/api/tasks` | 创建新的下载任务 |
| `GET` | `/api/tasks/{id}` | 获取单个任务详情 |
| `POST` | `/api/tasks/{id}/pause` | 暂停任务 |
| `POST` | `/api/tasks/{id}/resume` | 恢复任务 |
| `POST` | `/api/tasks/{id}/cancel` | 取消任务 |
| `GET` | `/api/stats` | 获取引擎统计信息 |
| `GET` | `/api/config` | 获取当前配置 |

### curl 示例

```bash
# 创建任务
curl -X POST http://127.0.0.1:8765/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/file.zip", "max_segments": 4}'
# → {"task_id":"abc123","status":"PENDING"}

# 查看所有任务
curl http://127.0.0.1:8765/api/tasks

# 查看单个任务
curl http://127.0.0.1:8765/api/tasks/abc123

# 暂停
curl -X POST http://127.0.0.1:8765/api/tasks/abc123/pause

# 取消
curl -X POST http://127.0.0.1:8765/api/tasks/abc123/cancel

# 统计
curl http://127.0.0.1:8765/api/stats
# → {"running":1,"pending":0,"paused":0,"failed":0,"completed":0}
```

### 第三方前端接入

```javascript
// 创建任务
async function startDownload(url) {
  const res = await fetch('http://127.0.0.1:8765/api/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, max_segments: 4 }),
  });
  const { task_id } = await res.json();

  // 轮询进度
  const timer = setInterval(async () => {
    const r = await fetch(`http://127.0.0.1:8765/api/tasks/${task_id}`);
    const data = await r.json();
    console.log(`${data.progress}% - ${data.speed} bytes/s`);
    if (data.status === 'COMPLETED' || data.status === 'FAILED') {
      clearInterval(timer);
    }
  }, 3000);
}
```

```python
# Python 接入
import requests, time

r = requests.post("http://127.0.0.1:8765/api/tasks", json={
    "url": "https://example.com/file.zip",
})
task_id = r.json()["task_id"]

while True:
    r = requests.get(f"http://127.0.0.1:8765/api/tasks/{task_id}")
    data = r.json()
    print(f"{data['status']}: {data['progress']:.1f}%")
    if data["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
        break
    time.sleep(1)
```

#### 创建任务请求体

```json
{
  "url": "https://example.com/file.zip",
  "save_dir": "~/Downloads",
  "filename": "myfile.zip",
  "max_segments": 4,
  "expected_sha256": "a1b2c3d4..."
}
```

所有字段均为可选，除 `url` 外。

#### 任务状态响应

```json
{
  "task_id": "abc123",
  "url": "https://...",
  "filename": "file.zip",
  "status": "RUNNING",
  "progress": 45.23,
  "downloaded": 7340032,
  "total_size": 16241440,
  "speed": 1048576.0,
  "avg_speed": 950272.0,
  "elapsed": 7.73,
  "eta": 8.48,
  "segments_total": 4,
  "segments_completed": 2,
  "segments_speed": [262144.0, 524288.0, 0.0, 0.0],
  "error": "",
  "file_path": "/Users/name/Downloads/file.zip"
}
```

---

## 拖拽下载工具

独立的 GUI 小工具，不依赖核心引擎以外的任何框架。

### GUI 窗口

```bash
py tools/drag_drop_downloader.py
```

弹出 Tkinter 窗口，将 URL 拖入或粘贴即可下载，支持暂停/恢复全部任务。

### 批处理拖拽

将浏览器中的链接拖到 `tools/拖拽下载.bat` 上即可下载。

### PowerShell 拖拽

支持同时拖入多个 `.url` 文件：

```powershell
.\tools\DropDownload.ps1 "https://example.com/file1.zip"
```

### 命令行快速下载

```bash
py tools/drag_drop_downloader.py --cli "https://example.com/file.zip"
```
