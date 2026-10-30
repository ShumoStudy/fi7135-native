#!/usr/bin/env bash
# install_macos.sh — macOS 安装 fi-7135 原生扫描环境
# 通过 Homebrew 安装开源 SANE 后端。注意：
#   · PFU 官方 macOS 驱动【不支持】fi-7135（官方多系统驱动机型表未收录该型号），
#   · 本方案依赖开源 sane-fujitsu 后端能否识别该机型，需实测。
set -e

if ! command -v brew >/dev/null 2>&1; then
  # Homebrew 可能装在 /opt/homebrew 但未进 PATH
  if [ -x /opt/homebrew/bin/brew ]; then
    export PATH="/opt/homebrew/bin:$PATH"
  else
    echo "未找到 Homebrew，请先安装： https://brew.sh"
    exit 1
  fi
fi

echo "==> 1/2 安装 sane-backends（开源扫描后端）"
brew install sane-backends

if [ -d /opt/homebrew/etc/sane.d ]; then
  CONF=/opt/homebrew/etc/sane.d
elif [ -d /usr/local/etc/sane.d ]; then
  CONF=/usr/local/etc/sane.d
else
  CONF="$(brew --prefix)/etc/sane.d"
fi
echo "SANE 配置目录：$CONF"

echo "==> 2/2 检测 USB 设备与扫描仪"
echo "--- USB 列表（找 Fujitsu/PFU 项） ---"
system_profiler SPUSBDataType 2>/dev/null | grep -B2 -A6 -iE "fujitsu|pfu" || \
  echo "（USB 列表未找到 Fujitsu 设备：请确认 USB 已连接、扫描仪已开机、换口换线再试）"

echo ""
scanimage -L || true
echo ""
echo "------------------------------------------------------------"
echo "如果列出了 Fujitsu/fi-7135：直接用本软件包："
echo "  python3 fi7135_native.py detect"
echo "  python3 fi7135_native.py gui"
echo ""
echo "如果【没有】列出设备："
echo "  1) 在 system_profiler SPUSBDataType 输出中找到扫描仪，记下 Vendor ID / Product ID"
echo "  2) 把 usb 0x04c5 0xXXXX 追加到 $CONF/fujitsu.conf："
echo "     echo 'usb 0x04c5 0xXXXX' | sudo tee -a $CONF/fujitsu.conf"
echo "  3) 重新插拔 USB，再执行： scanimage -L"
echo "  若仍识别不到：该机型协议可能未被开源后端收录，只能继续用 VueScan"
echo "  或换 Windows 电脑用官方 PaperStream IP 驱动。"
echo "------------------------------------------------------------"

echo "==> 可选：安装 Pillow（输出 PDF/JPEG/PNG 用）"
pip3 install --user pillow 2>/dev/null || echo "    （跳过）"
echo "安装完成。"
