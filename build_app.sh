#!/bin/bash
# 把 ScreenFloat 打包成可双击运行的 ScreenFloat.app
#
# 用法：
#   ./build_app.sh            仅生成 dist/ScreenFloat.app
#   ./build_app.sh --install  生成并安装到 /Applications，最后在访达中定位
#
# 关键取舍：不整体复制 .venv（1.3G），只挑截图功能真正需要的文件，
# 砍掉占 645M 的 QtWebEngineCore（截图用不到）。

set -euo pipefail

INSTALL_TO_APPS=0
if [ "${1:-}" = "--install" ]; then
  INSTALL_TO_APPS=1
fi

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$PROJECT_DIR/.venv"
BUILD_DIR="$PROJECT_DIR/dist"
APP="$BUILD_DIR/ScreenFloat.app"
CONTENTS="$APP/Contents"
MACOS_DIR="$CONTENTS/MacOS"
RES_DIR="$CONTENTS/Resources"

PY_VER="3.13"
# 注意是 lib/python3.13，不是 lib/3.13
PY_DIR="python$PY_VER"
SITE="$VENV/lib/$PY_DIR/site-packages"

echo "==> 检查源环境"
if [ ! -d "$SITE" ]; then
  echo "错误：找不到 $SITE"
  echo "请先运行： python -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

echo "==> 准备构建目录"
rm -rf "$APP"
mkdir -p "$MACOS_DIR" "$RES_DIR" "$BUILD_DIR"

echo "==> 复制 Python 运行时（排除无关测试包）"
# venv 的 lib 与 bin：bin 需要解释器本体，lib 需要 site-packages
mkdir -p "$RES_DIR/lib/$PY_DIR" "$RES_DIR/bin" "$RES_DIR/lib-dynload"
rsync -a --exclude='__pycache__' \
      --exclude='*.dist-info' \
      --exclude='*.pyc' \
      "$SITE/" \
      "$RES_DIR/lib/$PY_DIR/site-packages/"

# 解释器本体
for f in python python3 python3.13; do
  if [ -e "$VENV/bin/$f" ]; then
    cp -L "$VENV/bin/$f" "$RES_DIR/bin/$f" 2>/dev/null || true
  fi
done

# libpython 动态库：解释器启动必需，@rpath 指向 Resources/lib
# 注意必须从原 venv 读取 base_prefix，不能用刚复制出来的解释器（它此时还缺 dylib）
PY_BASE="$("$VENV/bin/python3.13" -c 'import sys; print(sys.base_prefix)' 2>/dev/null || true)"
echo "    Python 基础路径: ${PY_BASE:-未找到}"

if [ -n "$PY_BASE" ] && [ -f "$PY_BASE/lib/libpython$PY_VER.dylib" ]; then
  cp -L "$PY_BASE/lib/libpython$PY_VER.dylib" "$RES_DIR/lib/"
  echo "    已复制 libpython$PY_VER.dylib"
else
  echo "    警告：未找到 libpython$PY_VER.dylib，打包后可能无法启动"
fi

# Python 标准库（C 扩展模块等），保证脱离原环境也能运行
if [ -n "$PY_BASE" ] && [ -d "$PY_BASE/lib/$PY_DIR" ]; then
  rsync -a \
        --exclude='site-packages' \
        --exclude='__pycache__' \
        --exclude='test' \
        --exclude='tests' \
        --exclude='idlelib' \
        --exclude='tkinter' \
        --exclude='lib2to3' \
        --exclude='ensurepip' \
        "$PY_BASE/lib/$PY_DIR/" \
        "$RES_DIR/lib/$PY_DIR/"
  echo "    已复制 Python 标准库"
fi

echo "==> 复制项目源码"
mkdir -p "$RES_DIR/screenfloat"
rsync -a --exclude='__pycache__' --exclude='*.pyc' \
      "$PROJECT_DIR/screenfloat/" "$RES_DIR/screenfloat/"

echo "==> 裁剪无用组件（QtWebEngineCore 等）"
# 截图功能只用 QtCore/QtGui/QtWidgets，这些大件可以安全移除
for big in \
  "PySide6/Qt/lib/QtWebEngineCore.framework" \
  "PySide6/Qt/lib/QtWebEngineWidgets.framework" \
  "PySide6/Qt/lib/QtWebEngineQuick.framework" \
  "PySide6/Qt/lib/QtPdf.framework" \
  "PySide6/Qt/lib/QtQuick.framework" \
  "PySide6/Qt/lib/QtQml.framework" \
  "PySide6/Qt/lib/Qt3D" \
  "PySide6/Qt/qml" \
  "PySide6/Qt/translations" \
  "PySide6/Qt/assistant" \
  "PySide6/Qt/designer" \
  "PySide6/qmlls" \
  "PySide6/qmlformat" \
  "PySide6/qmlimportscanner" \
  "PySide6/qmllint" \
  "PySide6/qmlcachegen" \
  "PySide6/Assistant.app" \
  "PySide6/QtWebEngineCore.abi3.so" \
  "PySide6/QtWebEngineWidgets.abi3.so" \
  "PySide6/QtWebEngineQuick.abi3.so" \
  "PySide6/QtPdf.abi3.so" \
  "PySide6/QtQuick.abi3.so" \
  "PySide6/QtQml.abi3.so" \
  ; do
  [ -e "$RES_DIR/lib/$PY_DIR/site-packages/$big" ] && \
    rm -rf "$RES_DIR/lib/$PY_DIR/site-packages/$big" || true
done

# 移除 ffmpeg 相关解码库（截图用不到）
rm -f "$RES_DIR/lib/$PY_DIR/site-packages/PySide6/Qt/lib/"libav*.dylib 2>/dev/null || true

echo "==> 写入启动器"
# 注意：heredoc 加引号会阻止变量展开，所以内部路径用占位符 __PYDIR__，
# 构建后再用 sed 替换成实际的版本目录
cat > "$MACOS_DIR/ScreenFloat" <<'LAUNCHER'
#!/bin/bash
# ScreenFloat 启动器：由 .app 双击触发，不显示终端窗口
CONTENTS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RES="$CONTENTS_DIR/Resources"
PY="$RES/bin/python3.13"
LOG_DIR="$HOME/.screenfloat"
LOG="$LOG_DIR/screenfloat.log"

mkdir -p "$LOG_DIR" 2>/dev/null

# 启动失败时把原因写进日志，并弹窗告知（否则双击后毫无反馈）
fail() {
  echo "[ScreenFloat] 启动失败：$1" >> "$LOG"
  osascript -e "display alert \"ScreenFloat 启动失败\" message \"$1\"" 2>/dev/null
  exit 1
}

[ -x "$PY" ] || fail "未找到 Python 运行时，请重新运行 build_app.sh。"
[ -f "$RES/lib/libpython3.13.dylib" ] || fail "缺少运行库，请重新运行 build_app.sh。"
[ -d "$RES/screenfloat" ] || fail "缺少程序代码，请重新运行 build_app.sh。"

export PYTHONPATH="$RES"
export PYTHONHOME=""
# 解释器的 @rpath 指向 Resources/lib，必须显式给出动态库搜索路径，
# 否则启动时报 libpython3.x.dylib 缺失
export DYLD_LIBRARY_PATH="$RES/lib:$RES/lib/__PYDIR__/site-packages/PySide6/Qt/lib"
export DYLD_FALLBACK_LIBRARY_PATH="$RES/lib"
export QT_PLUGIN_PATH="$RES/lib/__PYDIR__/site-packages/PySide6/Qt/plugins"
export QT_QPA_PLATFORM_PLUGIN_PATH="$QT_PLUGIN_PATH/platforms"

# 注意：这里不要用「锁文件存在就退出」的粗略判断——
# 进程异常退出后锁文件会残留，之后双击将永远静默退出，
# 表现为「双击没反应」。真正的单实例判断交给程序内的 QLockFile，
# 它会校验锁对应的进程是否存活。

cd "$RES" || fail "无法进入程序目录"
"$PY" -u -m screenfloat >>"$LOG" 2>&1
LAUNCHER
chmod +x "$MACOS_DIR/ScreenFloat"
# 用实际版本目录替换占位符
sed -i '' "s|__PYDIR__|$PY_DIR|g" "$MACOS_DIR/ScreenFloat"

echo "==> 写入 Info.plist"
cat > "$CONTENTS/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>ScreenFloat</string>
    <key>CFBundleDisplayName</key>
    <string>ScreenFloat</string>
    <key>CFBundleExecutable</key>
    <string>ScreenFloat</string>
    <key>CFBundleIdentifier</key>
    <string>com.screenfloat.app</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>0.1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleIconFile</key>
    <string>icon</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <!-- 不在 Dock 显示，程序常驻菜单栏 + 控制面板 -->
    <key>LSUIElement</key>
    <true/>
    <!-- 屏幕录制权限用途说明 -->
    <key>NSScreenCaptureUsageDescription</key>
    <string>ScreenFloat 需要访问屏幕内容以实现截图功能。</string>
</dict>
</plist>
PLIST

echo "==> 生成图标"
# 用 Python 生成多尺寸图标，随后转成 icns
PYTHONPATH="$PROJECT_DIR" "$VENV/bin/python" <<'PYICON'
import sys
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

from screenfloat.floatwin import make_app_icon

icon = make_app_icon()
out = Path("/tmp/sf_icon")
out.mkdir(exist_ok=True)

for s in [16, 32, 64, 128, 256, 512, 1024]:
    pm = icon.pixmap(QSize(s, s))
    if not pm.isNull():
        pm.save(str(out / f"icon_{s}.png"), "PNG")

print("图标已生成")
PYICON

ICONSET_DIR="/tmp/ScreenFloat.iconset"
rm -rf "$ICONSET_DIR"
mkdir -p "$ICONSET_DIR"
cp /tmp/sf_icon/icon_16.png "$ICONSET_DIR/icon_16x16.png"
cp /tmp/sf_icon/icon_32.png "$ICONSET_DIR/icon_16x16@2x.png"
cp /tmp/sf_icon/icon_32.png "$ICONSET_DIR/icon_32x32.png"
cp /tmp/sf_icon/icon_64.png "$ICONSET_DIR/icon_32x32@2x.png"
cp /tmp/sf_icon/icon_128.png "$ICONSET_DIR/icon_128x128.png"
cp /tmp/sf_icon/icon_256.png "$ICONSET_DIR/icon_128x128@2x.png"
cp /tmp/sf_icon/icon_256.png "$ICONSET_DIR/icon_256x256.png"
cp /tmp/sf_icon/icon_512.png "$ICONSET_DIR/icon_256x256@2x.png"
cp /tmp/sf_icon/icon_512.png "$ICONSET_DIR/icon_512x512.png"
cp /tmp/sf_icon/icon_1024.png "$ICONSET_DIR/icon_512x512@2x.png"

if command -v iconutil >/dev/null 2>&1; then
  iconutil -c icns "$ICONSET_DIR" -o "$RES_DIR/icon.icns" 2>/dev/null && \
    echo "    icon.icns 生成成功" || \
    cp /tmp/sf_icon/icon_256.png "$RES_DIR/icon.icns"
else
  cp /tmp/sf_icon/icon_256.png "$RES_DIR/icon.icns"
fi

echo "==> 清理临时文件"
rm -rf /tmp/sf_icon "$ICONSET_DIR"

SIZE=$(du -sh "$APP" | cut -f1)
echo ""
echo "构建完成： $APP"
echo "体积：     $SIZE"
echo ""

if [ "$INSTALL_TO_APPS" -eq 1 ]; then
  echo "==> 安装到 /Applications"
  # 先移除旧版本，避免叠加出体积翻倍的残留
  rm -rf "/Applications/ScreenFloat.app" 2>/dev/null || true
  cp -R "$APP" /Applications/
  FINAL="/Applications/ScreenFloat.app"
  echo "    已安装：$FINAL"
else
  FINAL="$APP"
  echo "使用方式："
  echo "  双击 $APP 即可运行（不会出现终端窗口）"
  echo "  装入应用程序： ./build_app.sh --install"
fi

echo ""
# 在访达中定位，避免用户翻找
if command -v open >/dev/null 2>&1; then
  open -R "$FINAL" 2>/dev/null && echo "已在访达中为你选中该 app"
fi