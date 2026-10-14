"""PySide6 对象失效场景测试。

复现并验证修复：悬浮窗被关闭后，Python 引用仍在但 C++ 对象已销毁，
此时调用其方法会抛 RuntimeError，导致定时器崩溃、程序静默退出。

运行： .venv/bin/python tests/stale_object_check.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shiboken6  # noqa: E402
from PySide6.QtGui import QColor, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from screenfloat.config import Config  # noqa: E402
from screenfloat.floatwin import ManagerWindow  # noqa: E402
from screenfloat.store import ShotStore  # noqa: E402

_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail if not cond else ''}")
    if not cond:
        _failures.append(name)


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841

    tmp = Path(tempfile.mkdtemp(prefix="sf_stale_"))
    cfg = Config()
    cfg.cache_dir = str(tmp)
    store = ShotStore(cfg)
    manager = ManagerWindow(cfg)
    manager.store = store

    print("\n=== 制造失效窗口 ===")
    shots = []
    for i in range(3):
        pm = QPixmap(200, 120)
        pm.fill(QColor("#4C8DFF"))
        shots.append(store.add_pixmap(pm))
    wins = [manager.spawn(s) for s in shots]
    check("创建 3 个悬浮窗", len(manager.windows()) == 3)

    # 正常 tick 应不报错
    try:
        manager.tick_all()
        check("窗口存活时 tick 正常", True)
    except RuntimeError as exc:
        check("窗口存活时 tick 正常", False, f"({exc})")

    print("\n=== 销毁窗口后 tick（关键场景）===")
    # 直接销毁 C++ 对象：close + deleteLater + 处理事件
    victim = wins[0]
    victim.close()
    del victim
    # 强制 Qt 真正回收对象
    app.processEvents()

    try:
        manager.tick_all()
        check("窗口销毁后 tick 不崩溃", True)
    except RuntimeError as exc:
        check("窗口销毁后 tick 不崩溃", False, f"({exc})")

    print("\n=== shiboken6.isValid 判断正确性 ===")
    gone = wins[0]
    print(f"    isValid(已销毁对象) = {shiboken6.isValid(gone)}")
    check("isValid 能识别失效对象", not shiboken6.isValid(gone))

    alive = wins[1]
    check("isValid 能识别存活对象", shiboken6.isValid(alive))

    print("\n=== on_window_closed 容错 ===")
    try:
        manager.on_window_closed(gone)
        check("对失效窗口调用关闭不崩溃", True)
    except RuntimeError as exc:
        check("对失效窗口调用关闭不崩溃", False, f"({exc})")

    print("\n=== close_all 容错 ===")
    try:
        manager.close_all()
        check("close_all 不崩溃", True)
    except RuntimeError as exc:
        check("close_all 不崩溃", False, f"({exc})")
    check("close_all 后列表清空", len(manager.windows()) == 0)

    print("\n=== 连续销毁多个后仍稳定 ===")
    store2 = ShotStore(cfg)
    manager2 = ManagerWindow(cfg)
    manager2.store = store2
    pm = QPixmap(150, 90)
    pm.fill(QColor("#FF5A5F"))
    w2 = [manager2.spawn(store2.add_pixmap(pm)) for _ in range(5)]
    for w in w2:
        w.close()
    del w2
    app.processEvents()
    try:
        for _ in range(5):
            manager2.tick_all()
            manager2.close_all()
        check("反复 tick/close 循环稳定", True)
    except RuntimeError as exc:
        check("反复 tick/close 循环稳定", False, f"({exc})")

    shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 46)
    if _failures:
        print(f"结果：{len(_failures)} 项失败 -> {_failures}")
        return 1
    print("结果：全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())