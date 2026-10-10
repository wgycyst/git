# 手绘图转 CAD（sketch-to-cad）

把手绘草图（手机照片或扫描件）转成 CAD 能直接打开的 **DXF 线稿**，可选按实际尺寸 1:1 缩放，并输出预览图与结构校验图。

这是一个 **Codex 技能（skill）**：把本目录放进 `$CODEX_HOME/skills/`（默认 `~/.codex/skills/`）后，你在 Codex 里说“把这张手绘图转成 CAD”，它就会被自动调用；同时它也是一个独立的命令行工具，可以直接跑 `scripts/sketch2cad.py`。

## English

**sketch-to-cad** turns a photo or scan of a hand-drawn sketch into clean, editable **DXF line work** that any CAD can open (AutoCAD, ZWCAD, BricsCAD, LibreCAD, ...), and can scale the result to real-world size from a single known reference dimension.

It is packaged as a **Codex skill**, and also works as a plain command-line tool.

- Requirements: Python 3.9+, `numpy`, `opencv-python`, `scikit-image`
- Install as a Codex skill:

  ```bash
  git clone https://github.com/wgycyst/sketch-to-cad.git ~/.codex/skills/sketch-to-cad
  ```

- Quick start:

  ```bash
  pip install -r requirements.txt
  python scripts/check_env.py
  python scripts/sketch2cad.py sketch.jpg --auto-crop --grid
  python scripts/sketch2cad.py sketch.jpg --auto-crop --ref 120,112,1010,96 --ref-mm 4800 -o out.dxf
  python scripts/dxf_check.py out.dxf check.png
  ```

- Output: DXF (R12 / AC1009, `$INSUNITS = 4`, millimetres), a preview PNG, and a rebuild image for verification.
- Boundaries: this vectorises strokes. It does not OCR handwritten dimensions, and curves become dense polylines. For drawings that must be square, dimensioned and to scale, rebuild the geometry parametrically instead of tracing.
- License: MIT.

## 特性

- 手机斜拍也能用：自动识别纸张四角做透视校正（`--auto-crop`），也可手给四角（`--corners`）
- 抗光照：先做不均匀光照抑制，再二值化、去斑、骨架化、矢量化，抑制阴影与反光
- 建筑图友好：`--ortho` 把接近水平/垂直的线拉直；`--mode line` 每段输出 LINE，方便在 CAD 里编辑
- 可按真实尺寸：`--ref/--ref-mm` 或 `--width-mm` 标定，输出 1:1、单位为 mm 的 DXF
- 自带校验：`scripts/dxf_check.py` 把 DXF 读回来重新画，检查结构完整、有没有丢线
- 可选 CAD 集成：随附 AutoCAD LISP（`S2CINSERT` 插块、`S2CIMG` 照片底图、`S2CSTART` 描图捕捉）

## 环境要求

- Python 3.9+，依赖 `numpy`、`opencv-python`、`scikit-image`
- AutoCAD 2024 或任意能打开 DXF 的 CAD（仅“直接在 CAD 里打开 / 插块 / 描图”需要）

```bash
pip install -r requirements.txt
python scripts/check_env.py          # 自检：依赖是否齐全、Windows 上顺带探测 AutoCAD
```

## 快速开始

```bash
# 1) 探路转换 + 带坐标网格的预览图（用它确认描线质量）
python scripts/sketch2cad.py photo.jpg --auto-crop --grid

# 2) 按真实尺寸 1:1（两个参照点的像素坐标 + 实际长度 mm）
python scripts/sketch2cad.py photo.jpg --auto-crop --ref 120,112,1010,96 --ref-mm 4800 -o out.dxf

# 3) 结构校验 + 重建图
python scripts/dxf_check.py out.dxf check.png
```

完整参数说明见 [`references/troubleshooting.md`](references/troubleshooting.md)。

## 安装为 Codex 技能

```bash
git clone https://github.com/wgycyst/sketch-to-cad.git ~/.codex/skills/sketch-to-cad
```

或者直接把 `sketch-to-cad` 文件夹复制到 `~/.codex/skills/` 下即可（Windows 为 `%USERPROFILE%\.codex\skills\`）。

## AutoCAD 集成（可选，Windows）

把 `assets/autocad/sketch-to-cad.lsp` 复制到 AutoCAD 的 Support 目录：

```
%APPDATA%\Autodesk\AutoCAD 20xx\Rxx.x\<语言>\Support\
```

随图自动加载（改名/追加到 `acaddoc.lsp`），或在 CAD 里 `APPLOAD` 手动加载。命令清单见 LISP 文件头或 `S2CHELP`。

## 它不做什么

描线矢量化本质是“把笔迹变成线”：**不识别手写数字与文字**，圆弧会变成密集多段线，草图的绘制比例误差也会被照抄。要求“横平竖直、按实际尺寸、全部标注尺寸”的正式建筑图，应当按尺寸**参数化重画**而不是描线 —— 技能说明里写明了什么时候该切换到这种方式。

## 许可

MIT，见 [LICENSE](LICENSE)。
