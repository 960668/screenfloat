#!/bin/bash
# 一键推送到 GitHub
#
# 用法：
#   ./push_to_github.sh              # 推送到默认仓库 screenfloat
#   ./push_to_github.sh my-repo      # 推送到指定仓库名
#
# 前提：本机已安装 gh CLI 并登录（gh auth login）

set -uo pipefail

REPO_NAME="${1:-screenfloat}"
REMOTE_URL="https://github.com/960668/${REPO_NAME}.git"

cd "$(dirname "$0")" || exit 1

echo "════════════════════════════════════════"
echo " ScreenFloat → GitHub"
echo "════════════════════════════════════════"
echo "仓库： ${REMOTE_URL}"
echo ""

# 1) 检查 gh
if ! command -v gh > /dev/null 2>&1; then
  echo "未安装 gh CLI。"
  echo ""
  echo "请先安装（二选一）："
  echo "  brew install gh"
  echo "  或访问 https://cli.github.com 下载"
  echo ""
  echo "安装后执行： gh auth login"
  exit 1
fi

# 2) 检查登录状态
if ! gh auth status > /dev/null 2>&1; then
  echo "尚未登录 GitHub，请先执行： gh auth login"
  exit 1
fi

echo "当前 GitHub 账号： $(gh api user --jq .login 2>/dev/null)"

# 3) 确保提交存在
if git diff --quiet && git diff --cached --quiet; then
  echo ""
  echo "没有待提交的改动。"
else
  echo ""
  echo "检测到未提交的改动："
  git status --short
  read -r -p "是否提交这些改动？(y/N) " ans
  if [ "$ans" = "y" ] || [ "$ans" = "Y" ]; then
    git add -A
    git commit -m "chore: 更新"
  fi
fi

# 4) 设置远程
if git remote get-url origin > /dev/null 2>&1; then
  git remote set-url origin "$REMOTE_URL"
else
  git remote add origin "$REMOTE_URL"
fi

# 5) 创建远程仓库并推送
echo ""
echo "==> 创建 GitHub 仓库"
if gh repo view "960668/${REPO_NAME}" > /dev/null 2>&1; then
  echo "远程仓库已存在，直接推送。"
else
  gh repo create "${REPO_NAME}" \
    --public \
    --description "macOS 截图悬浮缓存工具：快捷键框选即悬浮，30 分钟自动清除，可拖进聊天窗口" \
    --source=. \
    --remote=origin
fi

echo ""
echo "==> 推送代码"
git push -u origin main

echo ""
echo "════════════════════════════════════════"
echo " 完成： https://github.com/960668/${REPO_NAME}"
echo "════════════════════════════════════════"