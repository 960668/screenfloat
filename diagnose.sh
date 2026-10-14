#!/bin/bash
# ScreenFloat 诊断脚本
#
# 双击没反应时，在终端运行这个脚本，会逐项检查并告诉你问题在哪。
# 用法： ./diagnose.sh

APP="/Applications/ScreenFloat.app"
LOG_DIR="$HOME/.screenfloat"
LOG="$LOG_DIR/screenfloat.log"

echo "════════════════════════════════════════"
echo " ScreenFloat 诊断"
echo "════════════════════════════════════════"
echo ""

fail_count=0
ok()   { echo "  ✅ $1"; }
bad()  { echo "  ❌ $1"; fail_count=$((fail_count+1)); }
warn() { echo "  ⚠️  $1"; }

echo "【1】应用文件"
if [ -d "$APP" ]; then
  ok "应用存在：$APP"
else
  bad "应用不存在，请重新运行 build_app.sh --install"
  echo ""
  echo "找不到应用，请先到项目目录执行："
  echo "  cd $(dirname "$0") && ./build_app.sh --install"
  exit 1
fi

echo ""
echo "【2】运行库"
RES="$APP/Contents/Resources"
if [ -x "$RES/bin/python3.13" ]; then
  ok "Python 解释器"
else
  bad "缺少 Python 解释器"
fi
if [ -f "$RES/lib/libpython3.13.dylib" ]; then
  ok "libpython 动态库"
else
  bad "缺少 libpython3.13.dylib"
fi
if [ -d "$RES/screenfloat" ]; then
  ok "程序代码"
else
  bad "缺少程序代码"
fi
if [ -x "$APP/Contents/MacOS/ScreenFloat" ]; then
  ok "启动器"
else
  bad "启动器无执行权限"
fi

echo ""
echo "【3】运行状态"
if pgrep -f "m screenfloat" > /dev/null 2>&1; then
  ok "程序正在运行"
  echo "     → 若看不到界面，请点菜单栏右上角的图标"
else
  warn "程序当前未运行"
fi

echo ""
echo "【4】日志"
if [ -f "$LOG" ]; then
  ok "日志文件：$LOG"
  echo "     最后 5 行："
  tail -5 "$LOG" | sed 's/^/       /'
else
  warn "没有日志文件（说明程序从未成功启动过）"
fi

echo ""
echo "【5】权限（macOS 隐私保护）"
PY="$RES/bin/python3.13"
if [ -x "$PY" ] && [ -f "$RES/lib/libpython3.13.dylib" ]; then
  ALLOW=$(DYLD_LIBRARY_PATH="$RES/lib" PYTHONPATH="$RES" "$PY" -c \
    "import Quartz; print(Quartz.CGPreflightListenEventAccess())" 2>/dev/null)
  SCREEN=$(DYLD_LIBRARY_PATH="$RES/lib" PYTHONPATH="$RES" "$PY" -c \
    "import Quartz; print(Quartz.CGPreflightScreenCaptureAccess())" 2>/dev/null)

  if [ "$ALLOW" = "True" ]; then
    ok "输入监控权限已授权（全局快捷键可用）"
  else
    warn "未授权「输入监控」→ 全局快捷键不可用"
    echo "     去：系统设置 → 隐私与安全性 → 输入监控 → 勾选 ScreenFloat"
  fi

  if [ "$SCREEN" = "True" ]; then
    ok "屏幕录制权限已授权（能截到真实屏幕）"
  else
    warn "未授权「屏幕与系统音频录制」→ 截到的是桌面壁纸"
    echo "     去：系统设置 → 隐私与安全性 → 屏幕与系统音频录制"
  fi
fi

echo ""
echo "════════════════════════════════════════"
if [ "$fail_count" -eq 0 ]; then
  echo "诊断结论：文件完整。"
  echo ""
  echo "若双击仍无反应，依次尝试："
  echo "  1. 菜单栏右上角找图标（程序可能已在运行）"
  echo "  2. 终端运行本项目的 run.command 看报错"
  echo "  3. 重装： ./build_app.sh --install"
else
  echo "诊断结论：发现 $fail_count 项文件缺失，请重新打包："
  echo "  ./build_app.sh --install"
fi
echo "════════════════════════════════════════"