#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fi7135_native.py — Fujitsu fi-7135 原生扫描驱动助手
====================================================

用途：替代 VueScan 等第三方扫描软件，通过系统开源 SANE 后端直接驱动
fi-7135 扫描仪，提供命令行（CLI）与图形界面（GUI）两种使用方式。

工作原理（三层结构）：
  1. 硬件协议层：系统自带的开源 sane-fujitsu 后端（Linux 发行版仓库 /
     macOS Homebrew），负责与 fi-7135 的 USB（SCSI-over-USB）通信。
  2. 接口层：SANE API（scanimage 命令行）。
  3. 应用层：本脚本 —— 检测设备、配置参数、批量扫描、输出 PDF/图片。

依赖：
  - Python 3.8+
  - Pillow（可选，用于输出 PDF/JPEG/PNG；缺失时退化为 TIFF 输出）
  - Linux: 包 sane-utils（Ubuntu: sudo apt install sane-utils）
  - macOS: Homebrew 包 sane-backends（brew install sane-backends）

用法：
  python3 fi7135_native.py detect                # 检测已连接的扫描仪
  python3 fi7135_native.py usb                   # 查看 USB 设备信息（排障用）
  python3 fi7135_native.py options <设备名>       # 查看设备全部可调参数
  python3 fi7135_native.py scan --source "ADF Duplex" --resolution 300 --format pdf
  python3 fi7135_native.py scan --source "ADF Front" --format jpg
  python3 fi7135_native.py scan --no-blank-removal --no-enhance ...  # 关闭去空白页/增强
  python3 fi7135_native.py scan --blank-threshold 2 --resolution 600   # 调阈值/高清分辨率
  python3 fi7135_native.py gui                    # 图形界面

默认行为：
  · 输出目录：~/Documents（文稿）
  · 自动去除空白页（墨水占比低于 1% 判定为空白，可用 --blank-threshold 调整）
  · 高清增强：自动对比度 + 锐化（--no-enhance 关闭）

注意：Windows 系统官方驱动为 PaperStream IP (TWAIN)，本脚本的 SANE 路径
仅适用于 Linux / macOS；Windows 使用方式见 README.md。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

SCANIMAGE = shutil.which("scanimage") or "scanimage"
FUJITSU_VID = "0x04c5"  # Fujitsu / PFU USB 厂商 ID
VERSION = "1.0.0"       # 版本号（2026-10-30 固化）
DEFAULT_OUT_DIR = os.path.expanduser("~/Documents")  # 文稿
DEFAULT_BLANK_THRESHOLD = 1.0  # 墨水占比低于该百分比判定为空白页

SOURCE_CHOICES = ["Flatbed", "ADF Front", "ADF Back", "ADF Duplex"]
MODE_CHOICES = ["Color", "Gray", "Lineart"]
FORMAT_CHOICES = ["pdf", "jpg", "png", "tiff"]


# ---------------------------------------------------------------- 检测

def detect_scanners():
    """运行 scanimage -L，返回 (设备列表, 原始输出)。

    设备列表元素: (设备名, 描述)。scanimage 不可用或执行失败时
    返回 (None, 错误信息)。
    """
    try:
        proc = subprocess.run(
            [SCANIMAGE, "-L"], capture_output=True, text=True, timeout=30
        )
    except FileNotFoundError:
        return None, (
            "找不到 scanimage 命令。请先安装 SANE：\n"
            "  Ubuntu:  sudo apt install sane-utils\n"
            "  macOS:   brew install sane-backends\n"
            "  Windows: 本脚本的 SANE 路径不适用，请改用官方 PaperStream IP 驱动"
        )
    except subprocess.TimeoutExpired:
        return None, "scanimage -L 执行超时（30 秒），请检查 USB 连接后重试。"

    devices = []
    # scanimage 输出形如: device `fujitsu:libusb:002:003' is a FUJITSU fi-7135 scanner
    for line in (proc.stdout + proc.stderr).splitlines():
        m = re.match(r"device\s+`([^']+)'\s+is\s+a\s+(.+)", line.strip())
        if m:
            devices.append((m.group(1), m.group(2).strip()))
    return devices, proc.stdout + proc.stderr


def find_fi7135(devices):
    """从设备列表中优先挑选 fi-7135（其次是任意 Fujitsu）。"""
    if not devices:
        return None
    for name, desc in devices:
        if "fi-7135" in name.lower() or "fi-7135" in desc.lower():
            return name
    for name, desc in devices:
        if "fujitsu" in name.lower() or "fujitsu" in desc.lower():
            return name
    return devices[0][0]


def usb_info():
    """输出 USB 层设备信息，用于排障（找 VID/PID）。"""
    if sys.platform.startswith("linux"):
        try:
            out = subprocess.run(
                ["lsusb"], capture_output=True, text=True, timeout=15
            ).stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            out = ""
        lines = [l for l in out.splitlines() if FUJITSU_VID in l.lower()]
        if lines:
            return "\n".join(lines) + "\n（厂商 ID 0x04c5 = Fujitsu/PFU）"
        return (
            "lsusb 中未找到 0x04c5 设备。请确认：USB 已连接、扫描仪已开机、"
            "换一根数据线/换个 USB 口再试。"
        )
    if sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["system_profiler", "SPUSBDataType"],
                capture_output=True, text=True, timeout=60,
            ).stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            out = ""
        lines = []
        block = ""
        for line in out.splitlines():
            if "Fujitsu" in line or "PFU" in line or "RICOH" in line:
                block = ""
            block += line + "\n"
            if line.strip() == "" and block:
                lines.append(block.strip())
                block = ""
        if lines:
            return "\n\n".join(lines[:4])
        return (
            "system_profiler 中未找到 Fujitsu/PFU 设备。请确认 USB 已连接、"
            "扫描仪已开机。"
        )
    return "USB 排障信息仅支持 Linux / macOS。"


def device_options(device):
    """运行 scanimage -d <device> --help，返回设备全部可调参数。"""
    try:
        proc = subprocess.run(
            [SCANIMAGE, "-d", device, "--help"],
            capture_output=True, text=True, timeout=30,
        )
        return proc.stdout + proc.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return f"获取参数失败：{e}"


def get_sources(device):
    """解析设备 --help 中 --source 的合法取值（如 ADF Front|ADF Duplex）。

    不同机型后端暴露的来源不同（fi-7135 只有 ADF 三种，无 Flatbed）。
    解析失败返回空列表，由调用方回退到默认选项。
    """
    help_text = device_options(device)
    m = re.search(r"--source\s+([^[]+?)\s*\[", help_text)
    if not m:
        return []
    return [v.strip() for v in m.group(1).split("|") if v.strip()]


# ---------------------------------------------------------------- 扫描

def build_scan_cmd(device, *, source=None, resolution=None, mode=None,
                   brightness=None, page_width=None, page_height=None,
                   out_prefix=None):
    """构造 scanimage 命令。out_prefix 给出时启用 --batch（ADF 多页）。"""
    cmd = [SCANIMAGE, "-d", device, "--format=tiff"]
    if source:
        cmd += ["--source", source]
    if resolution:
        cmd += ["--resolution", str(int(resolution))]
    if mode:
        cmd += ["--mode", mode]
    if brightness is not None:
        cmd += ["--brightness", str(int(brightness))]
    if page_width:
        cmd += ["--page-width", str(page_width)]
    if page_height:
        cmd += ["--page-height", str(page_height)]
    if out_prefix:
        cmd += ["--batch=" + out_prefix]
    return cmd


def _with_pillow(func):
    """Pillow 缺失时给出友好提示。"""
    try:
        import PIL  # noqa: F401
        return func()
    except ImportError:
        return None, "未安装 Pillow，无法输出 PDF/JPEG/PNG。请先执行：pip3 install pillow（或使用 --format tiff）"


# -------------------------------------------------------- 图像处理

def _is_blank(img, blank_threshold_pct, ink_threshold=200):
    """判定页面是否为空白：灰度图中低于 ink_threshold 的像素占比 < 阈值。"""
    total = img.width * img.height
    if total == 0:
        return True
    dark = sum(img.convert("L").histogram()[:ink_threshold])
    return (dark / total * 100.0) < blank_threshold_pct


def _enhance_image(img):
    """高清化：自动对比度 + 锐化（文档扫描常用增强）。"""
    from PIL import Image, ImageFilter, ImageOps
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img = ImageOps.autocontrast(img, cutoff=1)
    return img.filter(ImageFilter.UnsharpMask(radius=2, percent=120, threshold=3))


def _process_pages(page_files, *, mode=None, blank_removal=True,
                   blank_threshold=DEFAULT_BLANK_THRESHOLD, enhance=True):
    """对扫描页做后处理：去空白页 + 高清增强。

    返回 (保留的页面文件列表, 被删除的空白页编号列表)。
    Pillow 缺失时降级：打印提示并按原样返回。
    """
    if not (blank_removal or enhance):
        return page_files, []
    try:
        from PIL import Image
    except ImportError:
        print("提示：未安装 Pillow，跳过去空白页/增强处理（可 pip3 install pillow 后重扫）。")
        return page_files, []

    kept, removed = [], []
    for i, f in enumerate(page_files, start=1):
        try:
            img = Image.open(f)
        except Exception as e:  # noqa: BLE001
            print(f"警告：无法读取页面 {i}（{e}），保留原页。")
            kept.append(f)
            continue
        if blank_removal and _is_blank(img, blank_threshold):
            removed.append(i)
            continue
        if enhance and mode in (None, "Color", "Gray"):
            img = _enhance_image(img)
            img.save(f, "TIFF")
        kept.append(f)

    if removed:
        print(f"提示：已自动去除 {len(removed)} 个空白页（页面编号 {removed}）。")
    return kept, removed


def convert_to_pdf(page_files, out_path):
    """多张 TIFF/图片 → 单个多页 PDF。"""
    def _run():
        from PIL import Image
        images = []
        for f in sorted(page_files):
            im = Image.open(f)
            if im.mode in ("RGBA", "P"):
                im = im.convert("RGB")
            images.append(im.convert("RGB"))
        if not images:
            return None, "没有扫描到任何页面（请检查 ADF 是否放纸）。"
        images[0].save(out_path, "PDF", save_all=True, append_images=images[1:],
                       resolution=100.0)
        return out_path, None
    return _with_pillow(_run)


def convert_to_images(page_files, fmt, out_dir, name_prefix):
    """每页转成 jpg/png，文件名 name_prefix_p01.jpg 等。"""
    def _run():
        from PIL import Image
        results = []
        for i, f in enumerate(sorted(page_files), start=1):
            out = os.path.join(out_dir, f"{name_prefix}_p{i:02d}.{fmt}")
            im = Image.open(f)
            if fmt == "jpg":
                im = im.convert("RGB")
                im.save(out, "JPEG", quality=90)
            else:
                im.save(out, "PNG")
            results.append(out)
        return results, None
    return _with_pillow(_run)


def scan(device, *, source="ADF Duplex", resolution=300, mode="Color",
         brightness=None, fmt="pdf", out_dir=None, name=None,
         page_width=None, page_height=None, blank_removal=True,
         blank_threshold=DEFAULT_BLANK_THRESHOLD, enhance=True):
    """执行一次完整扫描并输出文件。返回 (输出文件列表, 错误信息)。"""
    if not device:
        return None, "未指定扫描仪设备名，请先运行 detect 获取设备名。"
    if not os.path.isdir(out_dir or os.getcwd()):
        os.makedirs(out_dir, exist_ok=True)
    out_dir = out_dir or DEFAULT_OUT_DIR

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name_prefix = name or f"fi7135_{timestamp}"

    use_batch = source.startswith("ADF")

    with tempfile.TemporaryDirectory(prefix="fi7135_") as tmp:
        if use_batch:
            pattern = os.path.join(tmp, "page-%04d.tif")
            single_out = None
        else:
            pattern = None
            single_out = os.path.join(tmp, "page-0001.tif")

        cmd = build_scan_cmd(
            device, source=source, resolution=resolution, mode=mode,
            brightness=brightness, page_width=page_width,
            page_height=page_height, out_prefix=pattern,
        )
        if not use_batch:
            cmd.append(single_out)

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            return None, "扫描超时（300 秒）。请检查纸张/进纸器状态后重试。"

        if proc.returncode != 0:
            return None, (
                f"扫描失败（退出码 {proc.returncode}）：\n"
                f"{proc.stderr.strip() or proc.stdout.strip()}"
            )

        if use_batch:
            page_files = sorted(
                os.path.join(tmp, f) for f in os.listdir(tmp)
                if f.lower().endswith(".tif")
            )
        else:
            page_files = [single_out] if os.path.exists(single_out) else []

        if not page_files:
            return None, "未生成任何图像文件。请确认进纸器中有纸、且设备工作正常。"

        # 后处理：去空白页 + 高清增强
        page_files, removed = _process_pages(
            page_files, mode=mode, blank_removal=blank_removal,
            blank_threshold=blank_threshold, enhance=enhance,
        )
        if removed and not page_files:
            return None, "去除空白页后没有剩余页面，未生成输出文件。"

        # 输出转换
        if fmt == "pdf":
            out_path = os.path.join(out_dir, f"{name_prefix}.pdf")
            done, err = convert_to_pdf(page_files, out_path)
            if err:
                return None, err
            return [done], None

        if fmt in ("jpg", "png"):
            return convert_to_images(page_files, fmt, out_dir, name_prefix)

        # tiff：把临时页复制到输出目录
        tiff_dir = os.path.join(out_dir, name_prefix)
        os.makedirs(tiff_dir, exist_ok=True)
        results = []
        for f in page_files:
            dest = os.path.join(tiff_dir, os.path.basename(f))
            shutil.copyfile(f, dest)
            results.append(dest)
        return results, None


# ---------------------------------------------------------------- CLI

def cmd_detect(args):
    devices, raw = detect_scanners()
    if devices is None:
        print(raw)
        sys.exit(1)
    if not devices:
        print("未检测到任何扫描仪。")
        print("请确认 USB 已连接、扫描仪已开机；Linux 可执行 `lsusb`，macOS 可执行 `system_profiler SPUSBDataType` 查看设备。")
        sys.exit(1)
    print("检测到的扫描仪：")
    for name, desc in devices:
        flag = "  <-- fi-7135" if "fi-7135" in (name + desc).lower() else ""
        print(f"  {name}  ({desc}){flag}")
    pick = find_fi7135(devices)
    print(f"\n建议使用的设备名：{pick}")


def cmd_usb(args):
    print(usb_info())


def cmd_options(args):
    if not args.device:
        devices, _ = detect_scanners()
        args.device = find_fi7135(devices or [])
    if not args.device:
        print("未检测到设备，无法查看参数。")
        sys.exit(1)
    print(f"设备 {args.device} 的可调参数：\n")
    print(device_options(args.device))


def cmd_scan(args):
    if not args.device:
        devices, raw = detect_scanners()
        args.device = find_fi7135(devices or [])
        if args.device is None:
            print("未检测到扫描仪，无法扫描。")
            print(raw)
            sys.exit(1)
        print(f"自动选用设备：{args.device}")

    # 按设备实际能力校正来源选项（如 fi-7135 无 Flatbed）
    allowed = get_sources(args.device)
    if allowed and args.source not in allowed:
        print(
            f"注意：设备不支持 --source {args.source}，"
            f"可用值：{' | '.join(allowed)}，已改用 {allowed[0]}"
        )
        args.source = allowed[0]

    results, err = scan(
        args.device,
        source=args.source, resolution=args.resolution, mode=args.mode,
        brightness=args.brightness, fmt=args.format, out_dir=args.out_dir,
        name=args.name, page_width=args.page_width, page_height=args.page_height,
        blank_removal=args.blank_removal, blank_threshold=args.blank_threshold,
        enhance=args.enhance,
    )
    if err:
        print(f"错误：{err}")
        sys.exit(1)
    print("扫描完成，输出文件：")
    for r in results:
        print(f"  {r}")


def cmd_gui(args):
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("当前环境没有 tkinter，无法启动图形界面。请使用命令行模式，或安装 python3-tk。")
        sys.exit(1)
    _run_gui()


# ---------------------------------------------------------------- GUI

def _run_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk

    devices, _ = detect_scanners()
    pick = find_fi7135(devices or [])
    # 按设备能力填充来源（fi-7135 无 Flatbed）
    src_values = get_sources(pick) if pick else []
    if not src_values:
        src_values = list(SOURCE_CHOICES)
    src_default = src_values[0] if src_values else "ADF Duplex"

    root = tk.Tk()
    root.title("fi-7135 原生扫描助手")
    root.geometry("560x560")

    frame = ttk.Frame(root, padding=12)
    frame.pack(fill="both", expand=True)

    # 设备
    ttk.Label(frame, text="扫描仪设备").grid(row=0, column=0, sticky="w")
    dev_var = tk.StringVar(value=pick or "")
    dev_combo = ttk.Combobox(
        frame, textvariable=dev_var, width=52,
        values=[d[0] for d in devices] or [""],
    )
    dev_combo.grid(row=0, column=1, sticky="we", pady=4)

    # 来源
    ttk.Label(frame, text="扫描来源").grid(row=1, column=0, sticky="w")
    src_var = tk.StringVar(value=src_default)
    src_combo = ttk.Combobox(
        frame, textvariable=src_var, width=52, values=src_values,
    )
    src_combo.grid(row=1, column=1, sticky="we", pady=4)

    # 分辨率 / 模式
    ttk.Label(frame, text="分辨率 (dpi)").grid(row=2, column=0, sticky="w")
    res_var = tk.StringVar(value="300")
    ttk.Spinbox(frame, from_=50, to=600, increment=50,
                textvariable=res_var, width=50).grid(row=2, column=1, sticky="we", pady=4)

    ttk.Label(frame, text="色彩模式").grid(row=3, column=0, sticky="w")
    mode_var = tk.StringVar(value="Color")
    ttk.Combobox(frame, textvariable=mode_var, width=52,
                 values=MODE_CHOICES).grid(row=3, column=1, sticky="we", pady=4)

    # 输出格式 / 目录
    ttk.Label(frame, text="输出格式").grid(row=4, column=0, sticky="w")
    fmt_var = tk.StringVar(value="pdf")
    ttk.Combobox(frame, textvariable=fmt_var, width=52,
                 values=FORMAT_CHOICES).grid(row=4, column=1, sticky="we", pady=4)

    ttk.Label(frame, text="保存目录").grid(row=5, column=0, sticky="w")
    dir_var = tk.StringVar(value=DEFAULT_OUT_DIR)
    ttk.Entry(frame, textvariable=dir_var, width=40).grid(row=5, column=1, sticky="we", pady=4)
    ttk.Button(frame, text="选择…",
               command=lambda: dir_var.set(filedialog.askdirectory())).grid(
        row=5, column=2, padx=(6, 0))

    # 后处理选项
    blank_var = tk.BooleanVar(value=True)
    enhance_var = tk.BooleanVar(value=True)
    opt = ttk.Frame(frame)
    opt.grid(row=6, column=0, columnspan=3, sticky="w", pady=4)
    ttk.Checkbutton(opt, text="自动去除空白页", variable=blank_var).pack(side="left", padx=(0, 16))
    ttk.Checkbutton(opt, text="高清增强（对比度+锐化）", variable=enhance_var).pack(side="left")

    # 日志
    log = scrolledtext.ScrolledText(frame, height=11, state="disabled",
                                    font=("Menlo", 10))
    log.grid(row=7, column=0, columnspan=3, sticky="we", pady=8)

    def log_append(text):
        log.config(state="normal")
        log.insert("end", text + "\n")
        log.see("end")
        log.config(state="disabled")

    def do_scan():
        if not dev_var.get():
            messagebox.showerror("fi-7135", "未检测到扫描仪设备，请先运行 detect。")
            return
        scan_btn.config(state="disabled")
        log_append("开始扫描…（批量模式会一直扫到进纸器为空）")

        def worker():
            try:
                results, err = scan(
                    dev_var.get(),
                    source=src_var.get(), resolution=int(res_var.get() or 300),
                    mode=mode_var.get(), fmt=fmt_var.get(),
                    out_dir=dir_var.get(),
                    blank_removal=blank_var.get(), enhance=enhance_var.get(),
                )
                if err:
                    log_append(f"错误：{err}")
                else:
                    for r in results:
                        log_append(f"输出：{r}")
                    log_append("完成。")
            except Exception as e:  # noqa: BLE001
                log_append(f"异常：{e}")
            finally:
                root.after(0, lambda: scan_btn.config(state="normal"))

        import threading
        threading.Thread(target=worker, daemon=True).start()

    scan_btn = ttk.Button(frame, text="开始扫描", command=do_scan)
    scan_btn.grid(row=7, column=0, columnspan=3, sticky="we", pady=(0, 4))

    ttk.Button(frame, text="重新检测设备",
               command=lambda: log_append(usb_info())).grid(
        row=8, column=0, columnspan=3, sticky="we")

    root.columnconfigure(1, weight=1)
    root.mainloop()


# ---------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(
        prog="fi7135_native",
        description="Fujitsu fi-7135 原生扫描驱动助手（SANE 后端 + 本控制程序）",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("detect", help="检测已连接的扫描仪").set_defaults(func=cmd_detect)

    p_usb = sub.add_parser("usb", help="查看 USB 设备信息（排障）")
    p_usb.set_defaults(func=cmd_usb)

    p_opt = sub.add_parser("options", help="查看设备全部可调参数")
    p_opt.add_argument("device", nargs="?", help="设备名（缺省时自动选择 fi-7135）")
    p_opt.set_defaults(func=cmd_options)

    p_scan = sub.add_parser("scan", help="执行扫描")
    p_scan.add_argument("--device", help="设备名（缺省时自动选择）")
    p_scan.add_argument("--source", choices=SOURCE_CHOICES, default="ADF Duplex")
    p_scan.add_argument("--resolution", type=int, default=300)
    p_scan.add_argument("--mode", choices=MODE_CHOICES, default="Color")
    p_scan.add_argument("--brightness", type=int, help="亮度（设备范围 -127..127）")
    p_scan.add_argument("--format", choices=FORMAT_CHOICES, default="pdf")
    p_scan.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                        help="保存目录（默认：文稿 ~/Documents）")
    p_scan.add_argument("--name", help="输出文件名前缀（默认 fi7135_时间戳）")
    p_scan.add_argument("--no-blank-removal", action="store_false",
                        dest="blank_removal", help="关闭自动去空白页")
    p_scan.add_argument("--blank-threshold", type=float,
                        default=DEFAULT_BLANK_THRESHOLD,
                        help="空白页判定阈值（墨水占比百分比，默认 1.0）")
    p_scan.add_argument("--no-enhance", action="store_false", dest="enhance",
                        help="关闭高清增强（自动对比度+锐化）")
    p_scan.add_argument("--page-width", help="纸张宽度（mm，如 210）")
    p_scan.add_argument("--page-height", help="纸张高度（mm，如 297）")
    p_scan.set_defaults(blank_removal=True, enhance=True)
    p_scan.set_defaults(func=cmd_scan)

    p_gui = sub.add_parser("gui", help="启动图形界面")
    p_gui.set_defaults(func=cmd_gui)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
