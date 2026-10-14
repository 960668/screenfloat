"""配置读写：缓存目录、过期时长、快捷键。

所有偏好存在 ~/.screenfloat/config.json，缺字段时用默认值补齐，
这样后续版本新增配置项不会让老配置文件失效。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

CONFIG_DIR = Path.home() / ".screenfloat"
CONFIG_FILE = CONFIG_DIR / "config.json"

# 默认缓存目录放「图片」下面，用户在访达里一眼能找到
DEFAULT_CACHE_DIR = Path.home() / "Pictures" / "ScreenFloatCache"


@dataclass
class Config:
    # 截图自动保存的本地目录
    cache_dir: str = str(DEFAULT_CACHE_DIR)
    # 过期分钟数，0 表示永不自动清除
    expire_minutes: int = 30
    # 全局快捷键，默认 ⌘⇧S
    hotkey: str = "cmd+shift+s"
    # 悬浮卡片最大宽度（逻辑像素）
    float_max_width: int = 320
    # 拖拽投送时是否临时隐藏悬浮窗（True 更干净，False 更稳）
    hide_during_drag: bool = False
    # 启动后是否直接进菜单栏常驻
    start_minimized: bool = True

    @property
    def cache_path(self) -> Path:
        return Path(self.cache_dir).expanduser()

    @property
    def expire_seconds(self) -> int:
        return 0 if self.expire_minutes == 0 else self.expire_minutes * 60

    @classmethod
    def load(cls) -> "Config":
        raw: dict = {}
        if CONFIG_FILE.exists():
            try:
                raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                # 配置损坏时不阻塞启动，直接回退默认配置
                raw = {}

        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in raw.items() if k in known}
        return cls(**clean)

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )