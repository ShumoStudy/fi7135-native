#!/usr/bin/env bash
# install_ubuntu.sh — Ubuntu 22.04/24.04 一键安装 fi-7135 原生扫描环境
# 安装开源 SANE 后端（系统仓库自带，非商业软件），并给出排障指引。
set -e

echo "==> 1/3 安装 SANE 扫描后端（开源，Ubuntu 官方仓库）"
sudo apt-get update
sudo apt-get install -y sane-utils libsane-common

echo "==> 2/3 配置 USB 访问权限（scanner 组）"
sudo groupadd -f scanner 2>/dev/null || true
sudo usermod -aG scanner "$USER" 2>/dev/null || true

echo "==> 3/3 检测扫描仪"
scanimage -L || true
echo ""
echo "------------------------------------------------------------"
echo "如果上面列出了 Fujitsu/fi-7135：大功告成，直接用本软件包："
echo "  python3 fi7135_native.py detect"
echo "  python3 fi7135_native.py gui"
echo ""
echo "如果【没有】列出设备，按下面三步排查："
echo "  1) 确认 USB 已连接、扫描仪已开机，执行： lsusb | grep -i 04c5"
echo "  2) 记下输出里的 Product ID，例如 04c5:xxxx → 把 0x04c5 0xxxx 追加到驱动配置："
echo "     echo 'usb 0x04c5 0xXXXX' | sudo tee -a /etc/sane.d/fujitsu.conf"
echo "  3) 重新插拔 USB，再执行： scanimage -L"
echo "------------------------------------------------------------"
echo ""
echo "提示：重新登录会话后 scanner 组成员权限生效；也可用 sudo -v 后重启。"

echo "==> 可选：安装 Pillow（输出 PDF/JPEG/PNG 用）"
pip3 install --user pillow 2>/dev/null || echo "    （跳过，无 pip 时仍可用 --format tiff）"
echo "安装完成。"
