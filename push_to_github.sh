#!/bin/bash
# 一键推送到 GitHub
#
# 用法：
#   ./push_to_github.sh              # 推送到默认仓库 screenfloat
#   ./push_to_github.sh my-repo      # 推送到指定仓库名
#
# 不依赖 gh CLI：直接用钥匙串里的 GitHub 凭据调 API 建仓库，
# 再用 git push 推送。装了 gh 也不影响。

set -uo pipefail

REPO_NAME="${1:-screenfloat}"
API="https://api.github.com"
REMOTE_URL="https://github.com/960668/${REPO_NAME}.git"

cd "$(dirname "$0")" || exit 1

echo "════════════════════════════════════════"
echo " ScreenFloat → GitHub"
echo "════════════════════════════════════════"
echo "仓库：${REMOTE_URL}"
echo ""

# 1) 取钥匙串凭据
TOKEN=$(printf "protocol=https\nhost=github.com\n\n" \
  | git credential-osxkeychain get 2>/dev/null | sed -n 's/^password=//p')

if [ -z "$TOKEN" ]; then
  echo "未找到 GitHub 凭据。"
  echo ""
  echo "请先在终端执行一次，登录后凭据会自动存入钥匙串："
  echo "  git push"
  echo "（输入 GitHub 用户名和 Personal Access Token）"
  echo ""
  echo "若还没有 Token，可在 https://github.com/settings/tokens 新建，"
  echo "勾选 repo 权限即可。"
  exit 1
fi

# 2) 确认凭据有效
LOGIN=$(curl -sS -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" "$API/user" 2>/dev/null \
  | sed -n 's/.*"login" *: *"\([^"]*\)".*/\1/p' | head -1)

if [ -z "$LOGIN" ]; then
  echo "GitHub 凭据无效或已过期，请检查 Token。"
  exit 1
fi
echo "已登录：${LOGIN}"

# 3) 提交待改动
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo ""
  echo "检测到未提交的改动："
  git status --short
  read -r -p "是否提交？(y/N) " ans
  if [ "$ans" = "y" ] || [ "$ans" = "Y" ]; then
    git add -A
    git commit -m "chore: 更新"
  fi
fi

# 4) 建仓库（已存在则跳过）
CODE=$(curl -sS -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
  "$API/repos/${LOGIN}/${REPO_NAME}" 2>/dev/null)

if [ "$CODE" = "200" ]; then
  echo ""
  echo "==> 远程仓库已存在，直接推送"
else
  echo ""
  echo "==> 创建公开仓库 ${REPO_NAME}"
  curl -sS -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/vnd.github+json" \
    -H "Content-Type: application/json" \
    "$API/user/repos" -d "{
      \"name\": \"${REPO_NAME}\",
      \"description\": \"macOS 截图悬浮缓存工具：快捷键框选即悬浮，30 分钟自动清除，可直接拖进聊天窗口\",
      \"private\": false,
      \"has_issues\": true,
      \"has_wiki\": false,
      \"topics\": [\"macos\", \"screenshot\", \"pyside6\", \"python\", \"utility\"]
    }" > /dev/null 2>&1
  echo "    已创建"
fi

# 5) 设置远程并推送
if git remote get-url origin > /dev/null 2>&1; then
  git remote set-url origin "$REMOTE_URL"
else
  git remote add origin "$REMOTE_URL"
fi

echo ""
echo "==> 推送代码"
GIT_TERMINAL_PROMPT=0 git push -u origin main

echo ""
echo "════════════════════════════════════════"
echo " 完成： https://github.com/${LOGIN}/${REPO_NAME}"
echo "════════════════════════════════════════"