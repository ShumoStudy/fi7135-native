# fi-7135 原生扫描驱动助手

替代 VueScan 等第三方扫描软件，让你在 Linux / macOS 上**原生**使用
Fujitsu fi-7135 文档扫描仪（ADF 自动进纸 + 双面）。

## 这套方案是什么

fi-7135 是一台 A4 双面文档扫描仪（600 dpi、50 页 ADF、USB 接口），它和电脑
通信用的是富士通（现理光 PFU）的私有协议。VueScan 之所以"装上就能扫"，
是因为它内置了一套私有协议的实现。

"从零写硬件驱动"需要逆向该私有协议，属于数月级工程，不现实；但**原生使用
的目标可以达成**——通过系统开源 SANE 后端 + 本控制程序三层结构：

```
┌───────────────────────────────────────────────────────┐
│ 应用层：fi7135_native.py（本包）                       │
│   GUI 界面 / 命令行 · 双面扫描 · 多页 PDF / JPEG / PNG │
├───────────────────────────────────────────────────────┤
│ 接口层：SANE API（scanimage / libsane）                │
├───────────────────────────────────────────────────────┤
│ 协议层：sane-fujitsu 后端（开源，Linux 仓库/macOS brew）│
│   USB VID 0x04c5（Fujitsu/PFU），SCSI-over-USB 协议    │
├───────────────────────────────────────────────────────┤
│ 硬件：Fujitsu fi-7135（ADF/平板/双面/600dpi）          │
└───────────────────────────────────────────────────────┘
```

**安装后需要一步实测**：`scanimage -L` 若能列出 fi-7135，即代表后端协议层
识别成功，此后完全不依赖任何第三方软件。

## 快速开始（GitHub 克隆后部署）

**仓库内容**（本目录共 5 个文件，全部需要上传）：

```
fi7135-native/
├── fi7135_native.py      # 主程序（CLI + GUI）
├── install_macos.sh      # macOS 安装脚本
├── install_ubuntu.sh     # Ubuntu 安装脚本
├── test_fi7135.py        # 单元测试（17 项，模拟 scanimage，无需真机）
└── README.md             # 本文档
```

> `.gitignore` 已排除 `test-output/`、`*.pdf`、`*.tif` 等本地扫描产物——
> 里面含个人证件扫描件，**不要上传到公开仓库**。

### 前置要求

- `git`、`python3`（≥3.8）
- Python 依赖：`pillow`（PDF/图片输出与增强必需）、`pypdf`（可选，验证用）
- macOS：Homebrew；Linux：`apt`（Ubuntu 22.04/24.04）

### macOS 部署（含 GitHub 克隆步骤）

```bash
# 1. 克隆仓库
git clone <你的仓库地址>
cd fi7135-native

# 2. 安装开源 SANE 后端（自动识别 fi-7135）
bash install_macos.sh

# 3. Homebrew 装在用户目录时，先加 PATH（写入 ~/.zshrc 永久生效）
export PATH="$HOME/homebrew/bin:$PATH"

# 4. 安装 Python 依赖
python3 -m pip install pillow pypdf

# 5. 验证识别
python3 fi7135_native.py detect
# 期望输出：device `fujitsu:fi-7135:409163' is a FUJITSU fi-7135 scanner

# 6. 开始扫描（默认：300dpi 双面批量 → 去空白页 + 高清增强 → 存到文稿）
python3 fi7135_native.py scan --source "ADF Duplex" --resolution 300 --format pdf
```

### Ubuntu 部署

```bash
git clone <你的仓库地址>
cd fi7135-native
bash install_ubuntu.sh              # 安装 sane-utils + 配置 scanner 组
python3 -m pip install pillow pypdf
python3 fi7135_native.py detect
python3 fi7135_native.py scan --source "ADF Duplex" --resolution 300 --format pdf
```

### 部署注意事项

1. 设备名 `fujitsu:fi-7135:409163` 中的序列号（409163）在 USB 重插/重开机后
   可能变化，程序会自动重新检测，无需手工改配置。
2. `scanimage -L` 若列不出设备，按「常见问题 → scanimage -L 没有设备」排查。
3. Windows 不需要本包，直接装 PFU 官方 PaperStream IP 驱动即可。

## 官方驱动支持现状（2026-10 核验）

| 系统 | 官方驱动 | 本方案 |
|---|---|---|
| Windows | ✅ PaperStream IP (TWAIN)，PFU 官网免费下载，系统原生 | 无需本包，装官方驱动即可（Windows 扫描/照片直接可用） |
| macOS | ❌ 官方多系统驱动机型表未收录 fi-7135 | ✅ 已在本机实测通过：sane-fujitsu 后端直接识别 fi-7135 |
| Linux (Ubuntu) | ❌ 官方 Linux 驱动机型表未收录 fi-7135 | 开源 sane-fujitsu 后端，实测 `scanimage -L` |

## 本机实测结果（macOS 26.6, arm64）

- 设备识别：`device fujitsu:fi-7135:409163 is a FUJITSU fi-7135 scanner` ✅
- 硬件链路：`scanimage` 能向扫描仪下达指令并收到真实状态响应 ✅
- 可用来源（sane-fujitsu 后端暴露）：`ADF Front | ADF Back | ADF Duplex`
  **注意：该后端下没有 Flatbed（平板）来源**，本包会自动按设备能力校正来源选项
- 分辨率 50–600 dpi，亮度范围 -127..127

## 安装

### Ubuntu 22.04 / 24.04

```bash
bash install_ubuntu.sh
```

脚本会安装 `sane-utils`（开源后端）、配置 `scanner` 组权限、检测设备。
装完执行：

```bash
python3 fi7135_native.py detect
```

### macOS

```bash
bash install_macos.sh
```

脚本用 Homebrew 安装 `sane-backends`，并打印 USB 设备信息。

> 注意：macOS 上 PFU 官方驱动不支持 fi-7135，本方案依赖开源后端识别。
> 若 brew 装在用户目录（如本机 `~/homebrew`），使用前先加 PATH：
> ```bash
> export PATH="$HOME/homebrew/bin:$PATH"   # 建议写入 ~/.zshrc 永久生效
> ```

### Windows

不用本包。去 PFU 官网下载页（fi-7135 → PaperStream IP (TWAIN)）安装官方驱动，
然后用系统自带的「Windows 扫描」或「照片」即可原生扫描。本脚本的 SANE 路径
只适用于 Linux / macOS。

## 使用

```bash
# 检测设备
python3 fi7135_native.py detect

# 双面批量扫描 → 多页 PDF（默认输出到 文稿 ~/Documents；fi-7135 无 Flatbed，必须用 ADF 来源）
python3 fi7135_native.py scan --source "ADF Duplex" --resolution 300 --format pdf

# 单面批量扫描 → JPEG 逐页
python3 fi7135_native.py scan --source "ADF Front" --resolution 300 --format jpg

# 关闭自动去空白页 / 关闭高清增强（两者默认开启）
python3 fi7135_native.py scan --no-blank-removal --no-enhance

# 空白页判定更严格（墨水占比低于 2% 才判空白）；真高清请用 600 dpi
python3 fi7135_native.py scan --blank-threshold 2 --resolution 600

# 指定设备、目录、文件名前缀
python3 fi7135_native.py scan --device "fujitsu:fi-7135:409163" \
    --source "ADF Front" --format pdf --out-dir ~/发票 --name 发票_001

# 图形界面（含 去空白页 / 高清增强 勾选项）
python3 fi7135_native.py gui

# 排障：看 USB 是否被系统识别；看设备全部可调参数（含空白页跳过 swskip、
# 防双张 df-action、预取纸 prepick 等高级功能，用 options 输出后自行组合参数）
python3 fi7135_native.py usb
python3 fi7135_native.py options <设备名>
```

常用参数（scanimage 语义）：
- `--source`：`ADF Front` / `ADF Back` / `ADF Duplex`（fi-7135 无 Flatbed）
- `--resolution`：50–600 dpi（硬件上限 600；要高清用 600）
- `--mode`：`Color` / `Gray` / `Lineart`
- `--format`：`pdf`（多页合并）/ `jpg` / `png` / `tiff`（逐页文件）
- `--out-dir`：保存目录（默认 文稿 `~/Documents`）
- `--blank-threshold`：空白页判定阈值，墨水占比低于该百分比（默认 1.0）即丢弃；`--no-blank-removal` 关闭
- `--no-enhance`：关闭高清增强（默认开启：自动对比度 + 锐化）

## 常见问题

**`scanimage -L` 没有设备**
1. 确认 USB 已连接、扫描仪已开机（指示灯亮）。
2. Linux 执行 `lsusb | grep -i 04c5`，macOS 执行 `system_profiler SPUSBDataType`。
3. 把扫描仪的 Product ID 追加到驱动配置后重新插拔 USB：
   - Linux：`echo 'usb 0x04c5 0xXXXX' | sudo tee -a /etc/sane.d/fujitsu.conf`
   - macOS：`echo 'usb 0x04c5 0xXXXX' | sudo tee -a /opt/homebrew/etc/sane.d/fujitsu.conf`
4. 仍不行：说明开源后端尚未收录该机型的协议，fi-7135 目前只能靠
   VueScan（macOS）或官方驱动（Windows）。

**提示 "permission denied"**
用户不在 `scanner` 组，或重新登录会话使组权限生效；临时可 `sudo scanimage -L`。

**双面扫描顺序**
sane-fujitsu 对双面通常按"正面1、背面1、正面2、背面2…"输出页面；如果发现
顺序不符，可改用 `ADF Front` + 换纸扫第二遍，或参考设备参数（`options` 命令）。

**扫到一半报 multifeed（多页进纸）**
fi-7135 自带超声波双张检测，纸张粘连时会中断——这是防漏扫保护，整理纸张
（抖开、去静电）后重扫即可。

**自动去空白页 / 高清增强**
- 两者默认开启：空白页按"墨水像素占比"判定（默认阈值 1.0%，双面扫描的空白
  背面会自动剔除），增强为自动对比度 + 锐化（UnsharpMask）。
- 双面扫描时若某页正反面都有内容但背面过淡被误删，调低阈值：
  `--blank-threshold 0.3`；不想要增强用 `--no-enhance`。
- 600 dpi 下增强处理会稍慢（每页图像大），属正常。

## 版本记录

- **v1.0.0**（2026-10-30）：首个正式版。原生 SANE 驱动 fi-7135，ADF 双面批量扫描；
  默认输出到文稿（~/Documents）；自动去除空白页（墨水占比阈值 1.0% 可调）；
  高清增强（自动对比度 + 锐化）；CLI + GUI 双模式；含 17 项单元测试。
  对应存档：`fi7135-native-v1.0.zip`。

## 目录结构

```
fi7135-native/
├── fi7135_native.py      # 主程序（CLI + GUI）
├── install_ubuntu.sh     # Ubuntu 安装脚本
├── install_macos.sh      # macOS 安装脚本
├── test_fi7135.py        # 单元测试（模拟 scanimage，无需真机）
└── README.md
```

## 验证

- 单元测试：`python3 test_fi7135.py`（用模拟数据验证检测/命令构造/转换逻辑）。
- 真机验证：`python3 fi7135_native.py detect` 能看到设备名。
- 首次扫描建议：放 2 页纸 → `scan --source "ADF Front" --format pdf` → 打开 PDF 核对。
