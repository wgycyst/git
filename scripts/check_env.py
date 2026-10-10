# -*- coding: utf-8 -*-
"""自检：Python 版本、依赖库、以及（Windows 上）AutoCAD 是否存在。

    python scripts/check_env.py
"""
import glob
import os
import sys

OK = "[ok] "
BAD = "[!!] "

def main():
    print("Python:", sys.version.split()[0], "@", sys.executable)
    if sys.version_info < (3, 9):
        print(BAD + "建议使用 Python 3.9 及以上版本")
    missing = []
    for name in ("numpy", "cv2", "skimage"):
        try:
            mod = __import__(name)
            ver = getattr(mod, "__version__", "?")
            print(OK + "%s %s" % (name, ver))
        except Exception as exc:
            missing.append(name)
            print(BAD + "%s 未安装 (%s)" % (name, exc))
    if missing:
        print("\n缺少依赖，请先安装：\n    %s -m pip install -r requirements.txt" % sys.executable)
    else:
        print("\n依赖齐全，可以运行 scripts/sketch2cad.py")

    if os.name == "nt":
        cands = sorted(glob.glob(r"C:\Program Files\Autodesk\AutoCAD *\acad.exe"))
        acad = os.environ.get("ACAD_EXE")
        found = acad if (acad and os.path.isfile(acad)) else (cands[-1] if cands else None)
        print((OK if found else "[--] ") + "AutoCAD: " + (found or "未检测到（可选，只有要直接在 CAD 里打开才需要）"))
    return 1 if missing else 0

if __name__ == "__main__":
    sys.exit(main())
