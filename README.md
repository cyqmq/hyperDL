# HyperDownloader Core

> **高性能多线程下载引擎** — 完全解耦，不依赖任何 GUI 框架。

## 设计目标

`HyperDownloader Core` 是一个纯 Python 的多线程下载引擎，核心设计哲学是**完全解耦**：

- ✅ **零 GUI 依赖** — 核心库不含任何 GUI 代码，只通过回调传递纯数据
- ✅ **可插拔集成** — 任何 GUI 框架（Tkinter、PyQt、WxPython、Web 等）均可通过 `ProgressCallback` 驱动
- ✅ **面向接口** — 所有 UI 交互通过 `DownloadProgress` 数据类和回调函数实现
- ✅ **开箱即用** — `DownloadProgress` 已包含进度百分比、速度、ETA、分片状态等所有 UI 所需字段

## 架构概览

```
┌─────────────────────────────────────────────────┐
│               HyperDownloader (Facade)           │
│             核心引擎入口，用户直接交互               │
├─────────────────────────────────────────────────┤
│               DownloadScheduler                   │
│       任务调度器（并发控制 / 排队 / 策略）           │
├────────────────────┬────────────────────────────┤
│   TaskDownloader   │   TaskDownloader            │
│   (单任务下载器)    │   (单任务下载器)              │
├────────┬──────────┼────────┬───────────────────┤
│ Seg-0  │ Seg-1    │ Seg-0  │ Seg-1  │ Seg-2    │
│ (线程) │ (线程)   │ (线程)  │ (线程) │ (线程)   │
└────────┴──────────┴────────┴───────────────────┘
         ↑ 回调传纯数据，不依赖任何 GUI
    ┌──────────────────────────────────┐
    │   任何 GUI / CLI / 其他项目      │
    └──────────────────────────────────┘
```

## 快速开始

### 安装

```bash
pip install hyperdownloader-core
```

或直接使用源码：

```bash
git clone https://github.com/cyqmq/hyperDL.git
cd hyperDL
pip install -r requirements.txt
```

### 基础用法

```python
from hyperdownloader import HyperDownloader, DownloadTask

# 1. 创建引擎
dl = HyperDownloader(max_concurrent=5)

# 2. 定义进度回调（纯控制台输出，可替换为任何 UI 更新）
def on_progress(progress):
    print(f"\r{progress.progress:.1f}% - {progress.speed/1024:.1f} KB/s", end="")

# 3. 创建下载任务
task = DownloadTask(
    url="https://example.com/large-file.zip",
    save_dir="./downloads",
    on_progress=on_progress,
)

# 4. 开始下载
task_id = dl.download(task)

# 5. 等待完成
dl.wait_all()
dl.stop()
```

### 集成到 GUI 项目（示例：Tkinter）

```python
# 完全相同的 API，只是把回调接入 Tkinter
def on_progress(progress):
    # progress 是纯数据对象，可驱动任何 UI
    progress_bar["value"] = progress.progress
    speed_label.config(text=f"{progress.speed/1024:.1f} KB/s")
    status_label.config(text=progress.status.name)

task = DownloadTask(url="...", save_dir="...", on_progress=on_progress)
```

## 核心特性

| 特性 | 说明 |
|------|------|
| 🚀 **多线程分片下载** | 支持 HTTP Range 请求，文件自动切分并发下载 |
| ⏸️ **暂停 / 恢复** | 支持断点续传，临时文件可自动恢复 |
| 🔄 **自动重试** | 指数退避重试策略，可配置重试次数 |
| 📊 **速度限制** | 全局速率限制（令牌桶算法） |
| 📋 **任务调度** | FIFO / LIFO / 优先级 三种策略 |
| 🔌 **完全解耦** | 纯数据回调，不依赖任何 GUI 框架 |
| 🌐 **代理支持** | HTTP / HTTPS / SOCKS5 |
| 🧪 **可测试** | 完整单元测试覆盖 |

## 深入使用

### 配置项

```python
from hyperdownloader import DownloadConfig, Headers, ProxyConfig

config = DownloadConfig(
    max_segments=8,           # 最大分片数（线程数）
    max_retries=5,            # 最大重试次数
    retry_delay=1.0,          # 重试基秒（指数退避）
    timeout=60.0,             # 超时时间
    speed_limit=500_000,      # 限速 500 KB/s
    resume=True,              # 启用断点续传
    headers=Headers(
        user_agent="MyApp/1.0",
        referer="https://example.com",
    ),
    proxy=ProxyConfig(
        http="http://127.0.0.1:8080",
        https="http://127.0.0.1:8080",
    ),
)
```

### 调度策略

```python
from hyperdownloader import HyperDownloader, SchedulerPolicy

# FIFO（先进先出，默认）
dl = HyperDownloader(policy=SchedulerPolicy.FIFO)

# LIFO（后进先出）
dl = HyperDownloader(policy=SchedulerPolicy.LIFO)

# 按优先级（高优先级任务先下载）
dl = HyperDownloader(policy=SchedulerPolicy.PRIORITY)

# 带优先级的任务
from hyperdownloader import DownloadTask
urgent = DownloadTask(url="...", save_dir="...", priority=10)
normal = DownloadTask(url="...", save_dir="...", priority=0)
```

### 任务管理

```python
# 暂停
dl.pause(task_id)

# 恢复
dl.resume(task_id)

# 取消
dl.cancel(task_id)

# 查询状态
active = dl.active_tasks       # list[DownloadTask]
pending = dl.pending_tasks     # list[DownloadTask]
results = dl.completed_results # list[DownloadResult]
```

## 项目结构

```
hyperdownloader-core/
├── hyperdownloader/        # 核心库
│   ├── __init__.py         # 包入口，导出公开 API
│   ├── enums.py            # 枚举定义
│   ├── models.py           # 数据模型（纯 dataclass）
│   ├── utils.py            # 工具函数
│   ├── segment.py          # 分片下载器
│   ├── downloader.py       # 单任务下载器
│   ├── scheduler.py        # 任务调度器
│   └── core.py             # 引擎 Facade
├── examples/               # 使用示例
│   ├── simple_download.py  # 单文件下载
│   └── batch_download.py   # 批量下载 + 暂停/恢复
├── tests/                  # 单元测试
├── pyproject.toml          # 项目配置
└── README.md
```

## 运行测试

```bash
pytest tests/ -v
```

## 许可证

MIT
