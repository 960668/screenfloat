"""全局快捷键注册（基于 CGEventTap）。

方案演进（记录踩过的坑，避免后人重走）：
1. Carbon RegisterEventHotKey + ctypes：新版 pyobjc 已移除 Carbon 模块；
   手工 ReceiveNextEvent 会与 Qt 的 Cocoa 循环争抢事件队列，
   实测 PostEvent 返回 -50(eventClassInvalid)，回调永不触发，且曾段错误。
2. 现在：CGEventTap —— 由 Cocoa 主循环直接派发，无需手动泵事件，
   且**不需要「输入监控」权限**（实测本机无该权限也能创建成功）。

关键坑：回调签名必须用标准库 ctypes.CFUNCTYPE；
objc.CFUNCTYPE / objc.c_void_p 在 pyobjc 里都不存在，用了会 AttributeError，
而那次报错曾让我误判为「tap 被权限拒绝」。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import CFUNCTYPE, c_uint32, c_void_p
from typing import Callable

from PySide6.QtGui import QKeySequence

try:
    import Quartz

    _HAS_QUARTZ = True
except ImportError:
    _HAS_QUARTZ = False

# CGEventFlags 掩码
_MASK_CMD = 0x00100000
_MASK_SHIFT = 0x00020000
_MASK_ALT = 0x00080000
_MASK_CTRL = 0x00040000

_MOD_ALIASES = {
    "cmd": _MASK_CMD,
    "command": _MASK_CMD,
    "meta": _MASK_CMD,
    "super": _MASK_CMD,
    "win": _MASK_CMD,
    "shift": _MASK_SHIFT,
    "alt": _MASK_ALT,
    "option": _MASK_ALT,
    "opt": _MASK_ALT,
    "ctrl": _MASK_CTRL,
    "control": _MASK_CTRL,
}

# CGEvent 虚拟键码 → 字符
_KEYCODES = {
    0: "A", 1: "S", 2: "D", 3: "F", 4: "H", 5: "G", 6: "Z", 7: "X",
    8: "C", 9: "V", 11: "B", 12: "Q", 13: "W", 14: "E", 15: "R",
    16: "Y", 17: "T", 18: "1", 19: "2", 20: "3", 21: "4", 22: "6",
    23: "5", 26: "7", 28: "8", 29: "9", 31: "O", 32: "U", 34: "I",
    35: "P", 37: "L", 38: "J", 40: "K", 45: "N", 46: "M",
    49: "SPACE", 36: "RETURN", 48: "TAB", 53: "ESCAPE", 51: "DELETE",
    123: "LEFT", 124: "RIGHT", 125: "DOWN", 126: "UP",
}

# CGEventTap 回调的 C 签名：OSStatus (*)(proxy, type, event, refcon)
_TAP_CALLBACK = CFUNCTYPE(c_void_p, c_void_p, c_uint32, c_void_p, c_void_p)


def parse_hotkey(spec: str) -> tuple[int, str]:
    """把 "cmd+shift+s" 解析成 (修饰键掩码, 主键字符)。"""
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError("快捷键格式为空")

    mask = 0
    for m in parts[:-1]:
        if m not in _MOD_ALIASES:
            raise ValueError(f"不支持的修饰键：{m}")
        mask |= _MOD_ALIASES[m]

    return mask, parts[-1].upper()


class QuartzHotkey:
    """用 CGEventTap 实现全局热键。"""

    def __init__(self, spec: str, callback: Callable[[], None]) -> None:
        self.spec = spec
        self.callback = callback
        self.available = False
        self.error = ""
        self._tap = None
        self._mask = 0
        self._key = ""

    def register(self) -> bool:
        if not _HAS_QUARTZ:
            self.error = "缺少 pyobjc 依赖，无法注册全局快捷键"
            return False

        try:
            self._mask, self._key = parse_hotkey(self.spec)
        except ValueError as exc:
            self.error = str(exc)
            return False

        mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
        self._cb = self._build_callback()
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            mask,
            self._cb,
            None,
        )
        if not tap:
            # 区分两种失败原因，给用户可操作的指引
            if not input_monitoring_allowed():
                self.error = "需要「输入监控」权限"
            else:
                self.error = "快捷键可能被其他应用占用，请换一个组合键"
            return False

        self._tap = tap
        # 挂到主 run loop 后由 Cocoa 循环自动派发，无需手动泵事件
        source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        Quartz.CFRunLoopAddSource(
            Quartz.CFRunLoopGetMain(), source, Quartz.kCFRunLoopCommonModes
        )
        Quartz.CGEventTapEnable(tap, True)
        self._source = source

        self.available = True
        return True

    def _build_callback(self):
        """构造 CFUNCTYPE 回调，命中组合键时触发业务回调。"""
        callback = self.callback
        spec_mask = self._mask
        spec_key = self._key

        def handler(_proxy, event_type, event, _refcon):
            # 回调超时被系统禁用时，重新启用即可
            if event_type == Quartz.kCGEventTapDisabledByTimeout:
                try:
                    Quartz.CGEventTapEnable(self._tap, True)
                except Exception:
                    pass
                return event

            try:
                keycode = Quartz.CGEventGetIntegerValueField(
                    event, Quartz.kCGKeyboardEventKeycode
                )
                flags = Quartz.CGEventGetFlags(event)
                if (
                    _KEYCODES.get(keycode) == spec_key
                    and (flags & spec_mask) == spec_mask
                ):
                    print(
                        f"[ScreenFloat] 热键命中: {self.spec}",
                        flush=True,
                    )
                    callback()
            except Exception:
                import traceback

                traceback.print_exc()

            # 返回原事件，不吞键
            return event

        return _TAP_CALLBACK(handler)

    def unregister(self) -> None:
        if self._tap:
            try:
                Quartz.CGEventTapEnable(self._tap, False)
            except Exception:
                pass
            self._tap = None
        self.available = False


class GlobalHotkey:
    """对外统一接口。"""

    def __init__(self, spec: str, callback: Callable[[], None]) -> None:
        self.spec = spec
        self.callback = callback
        self.available = False
        self.backend = "none"
        self.error = ""
        self._impl: QuartzHotkey | None = None

    def register(self) -> bool:
        if sys.platform == "darwin":
            impl = QuartzHotkey(self.spec, self.callback)
            if impl.register():
                self._impl = impl
                self.available = True
                self.backend = "cgeventtap"
                return True
            self.error = impl.error

        self.backend = "unavailable"
        self.available = False
        return False

    def request_permission(self) -> bool:
        """弹出系统的输入监控授权引导（用户拒绝过时可再次唤起）。"""
        if not _HAS_QUARTZ:
            return False
        try:
            return bool(Quartz.CGRequestListenEventAccess())
        except Exception:
            return False

    def pump_once(self, timeout: float = 0.0) -> bool:
        """CGEventTap 由 Cocoa 主循环派发，此方法仅为接口兼容。"""
        return False

    def unregister(self) -> None:
        if self._impl is not None:
            self._impl.unregister()
            self._impl = None
        self.available = False


def input_monitoring_allowed() -> bool:
    """是否已获准监听全局按键。

    CGEventTap 在权限不足时可能「创建成功但收不到事件」，
    这个函数用于把真实权限状态打印出来，避免误判。
    """
    if not _HAS_QUARTZ:
        return False
    try:
        return bool(Quartz.CGPreflightListenEventAccess())
    except Exception:
        return False


def qkeysequence_for(spec: str) -> QKeySequence | None:
    """把配置里的快捷键串转成 QKeySequence（窗口级回退用）。"""
    try:
        seq = QKeySequence(spec.replace("+", ","))
        return seq if not seq.isEmpty() else None
    except Exception:
        return None