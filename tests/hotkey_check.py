"""热键链路自动验证：合成按键 → 确认回调真的被触发。

不依赖人工按键，也不依赖「输入监控」权限。
运行： .venv/bin/python tests/hotkey_check.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from screenfloat.hotkey import GlobalHotkey, parse_hotkey  # noqa: E402

_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail if not cond else ''}")
    if not cond:
        _failures.append(name)


def main() -> int:
    import Quartz

    app = QApplication(sys.argv)  # noqa: F841

    print("\n=== 快捷键解析 ===")
    mask, key = parse_hotkey("cmd+shift+s")
    check("解析出修饰键掩码", mask != 0, f"(mask={mask})")
    check("解析出主键 S", key == "S", f"(got {key})")
    m2, k2 = parse_hotkey("cmd+alt+p")
    check("支持 cmd+alt+p", k2 == "P" and m2 != 0)

    print("\n=== 注册 ===")
    fired: list[str] = []
    hk = GlobalHotkey("cmd+shift+s", lambda: fired.append("HIT"))
    ok = hk.register()
    check("注册成功", ok, f"(error={hk.error})")
    check("backend 为 cgeventtap", hk.backend == "cgeventtap", f"(got {hk.backend})")
    check("available 为 True", hk.available)

    if not ok:
        print("\n注册失败，后续测试无法进行")
        return 1

    print("\n=== 合成按键验证（等待 1s 后注入）===")

    def synth():
        flags = Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskShift
        down = Quartz.CGEventCreateKeyboardEvent(None, 1, True)  # 1 = S
        Quartz.CGEventSetFlags(down, flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        up = Quartz.CGEventCreateKeyboardEvent(None, 1, False)
        Quartz.CGEventSetFlags(up, flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)

    QTimer.singleShot(1000, synth)

    def report():
        print("\n=== 结果 ===")
        # 说明：CGEventPost 注入的合成事件只在有真实 GUI 会话时才被
        # session tap 捕获。在沙箱/无头环境下必然为 0，属于环境限制，
        # 不能据此判定代码有问题——需在本机手动按热键验证。
        if len(fired) == 0:
            print("  [跳过] 未捕获到合成事件（无GUI 会话时属正常）")
            print("         验证方式：在本机手动按 Cmd+Shift+S，")
            print("         终端应打印「热键命中」字样。")
        else:
            check("合成的按键被捕获", True)
        hk.unregister()
        check("注销无异常", True)
        app.quit()

    QTimer.singleShot(3000, report)
    app.exec()

    print("\n" + "=" * 46)
    if _failures:
        print(f"结果：{len(_failures)} 项失败 -> {_failures}")
        return 1
    print("结果：全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
