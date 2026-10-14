#!/bin/bash
# 双击启动 ScreenFloat
# 保留窗口与输出，便于排查问题（关闭此窗口即退出程序）
cd "$(dirname "$0")" || exit 1
echo "=== ScreenFloat 启动中 ==="
echo "工作目录: $(pwd)"
echo "Python: $(.venv/bin/python -V 2>&1)"
echo ""
exec .venv/bin/python -u -m screenfloat 2>&1