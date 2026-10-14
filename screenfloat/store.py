"""截图缓存与生命周期管理。

每张截图落盘到缓存目录，记录创建时间；超过过期时长（默认 30 分钟）后
自动删除文件并关闭对应悬浮窗。进程启动时也会清理上次退出残留的老图，
避免异常退出后缓存无限堆积。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QPixmap

from .config import Config

# 清理巡检间隔：60 秒足够细，又不至于空转
SWEEP_INTERVAL_MS = 60_000
FILE_PREFIX = "shot_"
FILE_SUFFIX = ".png"


@dataclass
class Shot:
    """一张截图的运行时记录。"""

    path: Path
    created_at: float
    pinned: bool = False
    # 悬浮窗由 app 层在创建后回填，store 不感知 UI
    window: object | None = field(default=None, repr=False)

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.time() - self.created_at)


class ShotStore(QObject):
    """管理缓存目录中的截图文件与过期清理。"""

    # 文件被清理时发出，携带文件路径
    expired = Signal(str)

    def __init__(self, config: Config, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self._shots: dict[str, Shot] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(SWEEP_INTERVAL_MS)
        self._timer.timeout.connect(self.sweep)

    # ------------------------------------------------------------------ 目录

    def ensure_dir(self) -> Path:
        d = self.config.cache_path
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------ 写入

    def add_pixmap(self, pixmap: QPixmap) -> Shot:
        """把截图存盘并登记，返回记录。

        文件名用微秒级时间戳并在冲突时追加序号——
        同一毫秒内连拍两张时也能各自落盘，不会互相覆盖。
        """
        d = self.ensure_dir()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = d / f"{FILE_PREFIX}{stamp}{FILE_SUFFIX}"

        # 极端情况下（时间戳回拨/并发）仍可能撞名，追加序号兜底
        seq = 1
        while path.exists():
            path = d / f"{FILE_PREFIX}{stamp}_{seq}{FILE_SUFFIX}"
            seq += 1

        if not pixmap.save(str(path), "PNG"):
            raise RuntimeError(f"截图保存失败：{path}")

        shot = Shot(path=path, created_at=time.time())
        self._shots[str(path)] = shot
        return shot

    def register_existing(self, path: Path) -> Shot:
        """把磁盘上已有的文件纳入管理（用于恢复悬浮窗）。"""
        key = str(path)
        if key in self._shots:
            return self._shots[key]
        shot = Shot(path=path, created_at=path.stat().st_mtime)
        self._shots[key] = shot
        return shot

    # ------------------------------------------------------------------ 读取

    def shots(self) -> list[Shot]:
        return list(self._shots.values())

    def find_by_path(self, path: Path | str) -> Shot | None:
        return self._shots.get(str(path))

    # ------------------------------------------------------------------ 清理

    def is_expired(self, shot: Shot) -> bool:
        """钉住的图片永不过期；未开启过期（0）时同样不过期。"""
        if shot.pinned:
            return False
        ttl = self.config.expire_seconds
        if ttl <= 0:
            return False
        return shot.age_seconds >= ttl

    def _remove(self, shot: Shot, close_window: bool = True) -> None:
        """从管理列表移除并删文件，可选先关掉悬浮窗。"""
        self._shots.pop(str(shot.path), None)

        if close_window and shot.window is not None:
            win = shot.window
            shot.window = None
            try:
                win.close()
            except RuntimeError:
                # 窗口已被 C++ 侧销毁，忽略
                pass

        try:
            shot.path.unlink(missing_ok=True)
        except OSError:
            # 文件可能已被用户手动删除
            pass

        self.expired.emit(str(shot.path))

    def remove(self, shot: Shot) -> None:
        """手动关闭时调用：关窗 + 删文件（钉住时只关窗不删）。"""
        if shot.pinned:
            shot.pinned = False
            self._shots[str(shot.path)] = shot
        self._remove(shot)

    def sweep(self) -> list[Shot]:
        """巡检所有截图，清掉已过期的。返回被清掉的列表。"""
        gone = [s for s in self._shots.values() if self.is_expired(s)]
        for shot in gone:
            self._remove(shot)
        return gone

    def sweep_startup(self) -> list[Shot]:
        """启动时清理缓存目录：清掉过期文件，并把仍然新鲜的重新登记。

        覆盖两种情况——上次进程退出后新产生的截图（会被恢复出来重新显示），
        以及早已过期的残留（直接删掉）。
        """
        d = self.ensure_dir()
        ttl = self.config.expire_seconds
        restored: list[Shot] = []

        for path in sorted(d.glob(f"{FILE_PREFIX}*{FILE_SUFFIX}")):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue

            # ttl <= 0 表示不自动过期，此时只把文件登记起来
            expired = ttl > 0 and (time.time() - mtime) >= ttl
            if expired:
                path.unlink(missing_ok=True)
                continue

            self._shots[str(path)] = Shot(path=path, created_at=mtime)
            restored.append(self._shots[str(path)])

        return restored

    def clear_all(self) -> None:
        """清空缓存（托盘菜单「清空缓存」用）。"""
        for shot in list(self._shots.values()):
            self._remove(shot)

        # 兜底删掉目录里没被登记的文件
        d = self.config.cache_path
        if d.exists():
            for p in d.glob(f"{FILE_PREFIX}*{FILE_SUFFIX}"):
                p.unlink(missing_ok=True)

    # ------------------------------------------------------------------ 定时

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()