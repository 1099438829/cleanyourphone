#!/usr/bin/env bash
# CleanYourPhone — 安装官方 adb(Android 平台工具)到用户目录或系统
# 用法: bash tools/install-adb.sh
set -euo pipefail

echo "== CleanYourPhone adb 安装助手 =="

case "$(uname -s)" in
  Darwin)
    if command -v brew >/dev/null 2>&1; then
      echo "检测到 Homebrew, 安装 android-platform-tools ..."
      brew install android-platform-tools
      echo "完成。验证: adb version"
    else
      DEST="$HOME/.cleanyourphone/platform-tools"
      echo "未检测到 Homebrew, 下载官方 platform-tools 到 $DEST ..."
      mkdir -p "$DEST"
      TMP_ZIP="$(mktemp -d)/platform-tools.zip"
      curl -fL -o "$TMP_ZIP" \
        "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip"
      unzip -o -q "$TMP_ZIP" -d "$HOME/.cleanyourphone"
      echo "完成。请把下面一行加入 ~/.zshrc:"
      echo "  export PATH=\"\$HOME/.cleanyourphone/platform-tools:\$PATH\""
    fi
    ;;
  Linux)
    if command -v apt-get >/dev/null 2>&1; then
      echo "检测到 apt, 安装 android-tools-adb ..."
      sudo apt-get update -y && sudo apt-get install -y android-tools-adb
      echo "完成。验证: adb version"
    else
      DEST="$HOME/.cleanyourphone/platform-tools"
      echo "下载官方 platform-tools 到 $DEST ..."
      mkdir -p "$DEST"
      TMP_ZIP="$(mktemp -d)/platform-tools.zip"
      curl -fL -o "$TMP_ZIP" \
        "https://dl.google.com/android/repository/platform-tools-latest-linux.zip"
      unzip -o -q "$TMP_ZIP" -d "$HOME/.cleanyourphone"
      echo "完成。请把下面一行加入 ~/.bashrc:"
      echo "  export PATH=\"\$HOME/.cleanyourphone/platform-tools:\$PATH\""
    fi
    ;;
  MINGW*|MSYS*|CYGWIN*|Windows_NT)
    echo "Windows 请手动安装:"
    echo "  1. 下载 https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
    echo "  2. 解压到不含中文的目录, 例如 C:\\platform-tools"
    echo "  3. 设置 → 系统 → 关于 → 高级系统设置 → 环境变量 → Path 中加入 C:\\platform-tools"
    echo "  4. 重开终端, 运行: adb version"
    echo "注意: 请把本仓库放在不含中文的路径下再运行 .bat/.ps1(如有)。"
    ;;
  *)
    echo "未识别的系统: $(uname -s), 请手动安装 Android 平台工具"
    ;;
esac
