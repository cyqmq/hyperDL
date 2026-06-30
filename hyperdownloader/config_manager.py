"""
配置管理器

从 JSON 配置文件加载设置，支持多级查找：
1. 显式指定的配置文件路径
2. 当前工作目录下的 ``config.json``
3. ``~/.hyperdownloader/config.json``（用户级）

所有配置项均可被代码中的显式参数覆盖。
"""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("hyperdownloader.config")

# 配置文件名
CONFIG_FILENAME = "config.json"
# 用户级配置目录
USER_CONFIG_DIR = os.path.expanduser("~/.hyperdownloader")


@dataclass
class AppConfig:
    """应用配置，对应 config.json 的结构"""

    # ── 下载 ──
    max_segments: int = 4
    """默认分片数"""
    speed_limit: Optional[int] = None
    """全局速度限制（字节/秒）"""
    max_concurrent: int = 3
    """最大并发任务数"""

    # ── 调试 ──
    debug: bool = False
    """是否启用调试模式（输出分片级详细信息）"""

    # ── 路径 ──
    default_save_dir: str = ""
    """默认下载保存目录，为空则使用系统下载文件夹"""
    temp_suffix: str = ".hdt"
    """临时文件后缀"""

    # ── 代理 ──
    proxy_http: Optional[str] = None
    proxy_https: Optional[str] = None
    proxy_socks5: Optional[str] = None

    # ── 网络 ──
    timeout: float = 30.0
    connect_timeout: float = 10.0
    buffer_size: int = 8192
    max_retries: int = 3
    retry_delay: float = 2.0
    verify_ssl: bool = True

    # ── 行为 ──
    resume: bool = True
    """是否启用断点续传"""
    show_progress_bar: bool = True
    """是否显示进度条（仅 CLI 有效）"""


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """
    加载配置，优先级：参数路径 > 工作目录 > 用户目录 > 默认值。

    Args:
        config_path: 显式指定的配置文件路径

    Returns:
        AppConfig 实例
    """
    cfg = AppConfig()

    # 查找配置文件
    paths_to_try: list[str] = []
    if config_path:
        paths_to_try.append(config_path)

    # 工作目录
    cwd_config = os.path.join(os.getcwd(), CONFIG_FILENAME)
    if cwd_config not in paths_to_try:
        paths_to_try.append(cwd_config)

    # 用户目录
    user_config = os.path.join(USER_CONFIG_DIR, CONFIG_FILENAME)
    if user_config not in paths_to_try:
        paths_to_try.append(user_config)

    # 依次尝试加载
    loaded_path = None
    for path in paths_to_try:
        if os.path.isfile(path):
            loaded_path = path
            break

    if loaded_path:
        try:
            with open(loaded_path, "r", encoding="utf-8") as f:
                data: dict = json.load(f)
            _apply_dict(cfg, data)
            logger.info("已加载配置: %s", loaded_path)
        except Exception as e:
            logger.warning("加载配置失败 %s: %s", loaded_path, e)
    else:
        logger.info("未找到配置文件，使用默认配置")

    return cfg


def save_config(cfg: AppConfig, config_path: Optional[str] = None) -> str:
    """
    保存配置到文件。

    Args:
        cfg: 应用配置
        config_path: 目标路径，默认保存到用户目录

    Returns:
        实际保存的文件路径
    """
    path = config_path or os.path.join(USER_CONFIG_DIR, CONFIG_FILENAME)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    data = _to_dict(cfg)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info("配置已保存: %s", path)
    return path


def _apply_dict(cfg: AppConfig, data: dict) -> None:
    """将字典中的值写入 AppConfig（仅覆盖非 None 字段）"""
    for key, value in data.items():
        if hasattr(cfg, key) and value is not None:
            # 处理嵌套字段（如 proxy.http）
            if isinstance(value, dict):
                for sub_key, sub_val in value.items():
                    attr = f"{key}_{sub_key}"
                    if hasattr(cfg, attr) and sub_val is not None:
                        setattr(cfg, attr, sub_val)
            else:
                setattr(cfg, key, value)


def _to_dict(cfg: AppConfig) -> dict:
    """将 AppConfig 转为字典"""
    result: dict = {}
    for field_name in (
        "max_segments", "speed_limit", "max_concurrent", "debug",
        "default_save_dir", "temp_suffix",
        "timeout", "connect_timeout", "buffer_size",
        "max_retries", "retry_delay", "verify_ssl",
        "resume", "show_progress_bar",
    ):
        val = getattr(cfg, field_name)
        if val is not None:
            result[field_name] = val

    # 代理 (嵌套对象)
    proxy: dict[str, Optional[str]] = {}
    for k in ("http", "https", "socks5"):
        val = getattr(cfg, f"proxy_{k}")
        if val is not None:
            proxy[k] = val
    if proxy:
        result["proxy"] = proxy

    return result
