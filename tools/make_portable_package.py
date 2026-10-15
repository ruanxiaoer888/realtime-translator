# -*- coding: utf-8 -*-
"""打便携包：把项目打成可以直接拷去另一台电脑的 zip。

    python tools\\make_portable_package.py

为什么不能用 `tar -a -c -f x.zip`：
    Windows 上的 bsdtar 会把**中文文件名按本地代码页(GBK)写成字节**，
    而且不置 zip 规范的 UTF-8 标志位（general purpose bit 11）。
    解压端按 CP437 解 -> 文件名乱码。
    实测：tar 打的包里 Python 一个中文名都读不出来（`启动翻译助手.bat`
    会变成 `�����������.bat`）。Windows 资源管理器可能"看起来正常"，
    但 7-Zip / Python / 跨语言环境全是乱码 —— 这种包不能发出去。

    本脚本用 Python 的 zipfile：对非 ASCII 名字一律写 UTF-8 并置标志位，
    而且**打完立刻自检标志位**，不合格直接报错退出。

打进包里的额外内容（项目里没有的）：
    · 安装Python\\python-3.12.9-amd64.exe   <- 来自 tmp/，没有就跳过并提示
    · 新电脑先读我.txt                       <- 项目根目录里的入口文档

排除：.git / __pycache__ / 记录 / tmp 下的音频日志缓存 / 旧 zip
"""
from __future__ import annotations

import os
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT = os.path.dirname(ROOT)
SRC_NAME = os.path.basename(ROOT)
OUT = os.path.join(PARENT, f"{SRC_NAME}-便携包-{time.strftime('%Y%m%d')}.zip")

PY_INSTALLER = os.path.join(ROOT, "tmp", "python-3.12.9-amd64.exe")
PY_ARCNAME = "安装Python/python-3.12.9-amd64.exe"

SKIP_DIRS = {".git", "__pycache__", "记录", "hub", ".idea", ".vscode", "venv", ".venv"}
SKIP_EXTS = {".pyc", ".pyo", ".wav", ".log", ".zip"}
SKIP_FILES = {"translate_cache.json", "诊断报告.txt", "自检结果.txt"}


def collect():
    items: list[tuple[str, str]] = []          # (磁盘路径, 包内路径)
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for f in sorted(filenames):
            if os.path.splitext(f)[1].lower() in SKIP_EXTS or f in SKIP_FILES:
                continue
            full = os.path.join(dirpath, f)
            arc = os.path.relpath(full, PARENT).replace(os.sep, "/")
            items.append((full, arc))
    return items


def main():
    if not os.path.isfile(os.path.join(ROOT, "新电脑先读我.txt")):
        print("警告：项目根目录缺 新电脑先读我.txt，包里会少掉入口文档")

    items = collect()
    extra = []
    if os.path.isfile(PY_INSTALLER):
        extra.append((PY_INSTALLER, PY_ARCNAME))
    else:
        print(f"提示：没找到 {PY_INSTALLER}")
        print("      包里将不含 Python 安装程序（大小差 25 MB）")
        print("      需要的话从 https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe 下到该路径")

    total = len(items) + len(extra)
    print(f"待打包 {total} 个文件（含额外 {len(extra)} 个）")
    print(f"输出: {OUT}")

    t0 = time.time()
    done = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for full, arc in items + extra:
            z.write(full, arc)
            done += 1
            if done % 1000 == 0:
                print(f"  {done}/{total}  {time.time()-t0:.0f}s  "
                      f"{os.path.getsize(OUT)/1024/1024:.0f} MB")

    size = os.path.getsize(OUT)
    print(f"\n打包完成: {done} 个文件, {size/1024/1024:.1f} MB, 用时 {time.time()-t0:.0f} 秒")

    # ---------------- 打完必须自检：中文名编码 ----------------
    print("\n自检中文名编码……")
    with zipfile.ZipFile(OUT) as z:
        infos = z.infolist()
        cjk = [i for i in infos if any("\u4e00" <= c <= "\u9fff" for c in i.filename)]
        bad = [i.filename for i in cjk if not (i.flag_bits & 0x800)]
        missing = [i.filename for i in cjk if not (i.flag_bits & 0x800)]
    print(f"  条目 {len(infos)} 个，含中文名 {len(cjk)} 个，未置 UTF-8 标志 {len(bad)} 个")
    for i in sorted(cjk, key=lambda x: x.filename)[:12]:
        print(f"    {i.filename}")

    if not cjk:
        print("\nFAIL: 一个中文名都没有 —— 打包方式有问题，别发出去")
        return 1
    if bad:
        print(f"\nFAIL: 这些中文名没置 UTF-8 标志，解压会乱码: {missing}")
        return 1

    # ---------------- 关键文件抽查 ----------------
    keys = ["新电脑先读我.txt", "启动翻译助手.bat", "start.ps1", "app.py",
            "check_deploy.py", "settings.json", "libs/numpy/__init__.py",
            "tools/collect_report.py", "部署到另一台电脑.md",
            "tmp/models/ct2-medium/model.bin", "tmp/models/ocr-latin/rec.onnx"]
    with zipfile.ZipFile(OUT) as z:
        names = set(z.namelist())
    print("\n关键文件抽查:")
    ok = True
    for k in keys:
        arc = f"{SRC_NAME}/{k}"
        hit = arc in names
        ok = ok and hit
        print(f"  [{'OK  ' if hit else 'FAIL'}] {k}")
    if extra:
        hit = PY_ARCNAME in names
        ok = ok and hit
        print(f"  [{'OK  ' if hit else 'FAIL'}] {PY_ARCNAME}")

    import hashlib
    h = hashlib.sha256()
    with open(OUT, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    print(f"\nSHA256: {h.hexdigest().upper()}")
    print("\n结果:", "OK —— 可以拷走了" if ok else "FAIL —— 有关键文件缺失")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
