"""端到端冒烟测试（不需要人工交互）。

覆盖：落盘、过期判定、清理删文件、钉住豁免、启动恢复。
运行： .venv/bin/python tests/smoke.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QColor, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from screenfloat.config import Config  # noqa: E402
from screenfloat.store import ShotStore  # noqa: E402

PASS, FAIL = "  [PASS]", "  [FAIL]"
_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"{PASS} {name}")
    else:
        print(f"{FAIL} {name} {detail}")
        _failures.append(name)


def make_pixmap(w: int = 120, h: int = 80, color: str = "#4C8DFF") -> QPixmap:
    pm = QPixmap(w, h)
    pm.fill(QColor(color))
    return pm


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841 - 保持引用

    tmp = Path(tempfile.mkdtemp(prefix="screenfloat_test_"))
    cfg = Config()
    cfg.cache_dir = str(tmp / "cache")
    cfg.expire_minutes = 30

    store = ShotStore(cfg)

    print("\n=== 落盘 ===")
    shot = store.add_pixmap(make_pixmap())
    check("文件已写入", shot.path.exists(), f"({shot.path})")
    check("扩展名为 .png", shot.path.suffix == ".png")
    check("文件名带shot_ 前缀", shot.path.name.startswith("shot_"))
    size = shot.path.stat().st_size
    check("文件非空", size > 0, f"(size={size})")

    print("\n=== 过期判定 ===")
    check("刚创建不算过期", not store.is_expired(shot))
    shot.created_at = time.time() - 29 * 60
    check("29 分钟未过期", not store.is_expired(shot))
    shot.created_at = time.time() - 31 * 60
    check("31 分钟已过期", store.is_expired(shot))

    print("\n=== 钉住豁免 ===")
    shot.pinned = True
    check("钉住后即使很久也不过期", not store.is_expired(shot))
    shot.pinned = False

    print("\n=== sweep 清理 ===")
    path_before = shot.path
    gone = store.sweep()
    check("sweep 返回1 条", len(gone) == 1, f"(实际 {len(gone)})")
    check("文件已被删除", not path_before.exists())
    check("列表已清空", len(store.shots()) == 0)

    print("\n=== 关闭即删除 ===")
    s2 = store.add_pixmap(make_pixmap(color="#FF5A5F"))
    p2 = s2.path
    store.remove(s2)
    check("手动关闭后文件删除", not p2.exists())

    print("\n=== 不自动清除模式 ===")
    cfg.expire_minutes = 0
    s3 = store.add_pixmap(make_pixmap(color="#FFD166"))
    s3.created_at = time.time() - 86400  # 一天前
    check("ttl=0 时不视为过期", not store.is_expired(s3))
    check("ttl=0 时 sweep 不清理", store.sweep() == [])
    check("文件仍在", s3.path.exists())
    cfg.expire_minutes = 30

    print("\n=== 启动恢复 ===")
    # 用干净目录，避免前面用例残留的文件干扰恢复计数
    cfg.cache_dir = str(tmp / "cache_restore")
    store2 = ShotStore(cfg)
    fresh = store2.add_pixmap(make_pixmap(color="#34C759"))
    stale_path = cfg.cache_path / "shot_20990101_000000_000.png"
    stale_path.write_bytes(b"stale")
    os.utime(stale_path, (0, 0))  # 时间戳设为 1970，必然过期

    store3 = ShotStore(cfg)
    restored = store3.sweep_startup()
    restored_paths = [s.path for s in restored]
    check("新鲜截图被恢复", fresh.path in restored_paths)
    check("过期残留被删除", not stale_path.exists())
    check("恢复数量为 1", len(restored) == 1, f"(实际 {len(restored)})")

    print("\n=== 清空全部 ===")
    store3.clear_all()
    check("clear_all 后无文件", not fresh.path.exists())
    check("clear_all 后列表为空", len(store3.shots()) == 0)

    print("\n=== 多张并存 ===")
    cfg.cache_dir = str(tmp / "cache_multi")
    store4 = ShotStore(cfg)
    shots = [store4.add_pixmap(make_pixmap(50 + i * 10, 40)) for i in range(5)]
    check("5 张全部落盘", all(s.path.exists() for s in shots))
    check("文件名互不冲突", len({s.path.name for s in shots}) == 5)

    print("\n=== 极端并发落盘（模拟同一微秒连拍）===")
    cfg.cache_dir = str(tmp / "cache_race")
    store5 = ShotStore(cfg)
    rapid = [store5.add_pixmap(make_pixmap(30, 30, "#34C759")) for _ in range(20)]
    check("20 张全部落盘", all(s.path.exists() for s in rapid))
    check("20 张文件名全唯一", len({s.path.name for s in rapid}) == 20,
          f"(实际 {len({s.path.name for s in rapid})})")

    # 清理测试目录
    import shutil

    shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 46)
    if _failures:
        print(f"结果：{len(_failures)} 项失败 -> {_failures}")
        return 1
    print("结果：全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())