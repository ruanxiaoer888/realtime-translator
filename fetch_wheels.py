# -*- coding: utf-8 -*-
"""下载并解包 Python 依赖到本地 libs/ 目录，绕开 pip 在沙箱下的临时目录权限问题。

用法:
    python fetch_wheels.py mss rapidocr_onnxruntime deep-translator

每个包会从 PyPI 官方 JSON 接口解析出与当前解释器兼容的 wheel，
下载到 tmp/wheels/ 后解压到 libs/。
"""
import json
import os
import re
import ssl
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
WHEEL_DIR = os.path.join(ROOT, "tmp", "wheels")
LIB_DIR = os.path.join(ROOT, "libs")

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# 已随系统 Python 或 DSH 运行时提供、无需重复下载的包
SKIP = {
    "numpy", "pillow", "six", "requests", "urllib3", "certifi", "charset-normalizer",
    "idna", "typing-extensions", "typing_extensions", "setuptools", "wheel", "pip",
    "packaging", "python-dateutil", "colorama", "flatbuffers", "protobuf",
}

# 某些包的最新版依赖不存在的 httpx2，或与其他包版本冲突，锁定到稳定版
PINNED = {
    "huggingface-hub": "0.36.0",
    "transformers": "4.46.3",
    "tokenizers": "0.20.3",
    # numpy 别用最新版：2.5 会让 numba 直接报错（Numba needs NumPy 2.1 or less），
    # 连带把 openai-whisper 那条老回退路径弄坏。2.1.3 是本项目全程实测验证过的版本。
    "numpy": "2.1.3",
}

# 某些包在 PyPI 上的规范名与 import 名不同
EXTRA_DEPS = {
    "rapidocr_onnxruntime": ["onnxruntime", "opencv-python", "pyclipper", "shapely", "pyyaml"],
    "deep-translator": ["beautifulsoup4", "requests"],
    "faster-whisper": ["ctranslate2", "tokenizers", "huggingface-hub", "av"],
    "requests": ["charset-normalizer", "idna", "urllib3", "certifi"],
    "cffi": ["pycparser"],
}

# 核心包：这些天然存在于开发机的 site-packages 里，但**换一台电脑就没有**。
# 跑 `python fetch_wheels.py --core` 会把它们也装进 libs/，让整个目录可以整体拷贝。
# 之前只有 libs/ 是不够的：numpy / cffi / requests 缺失会导致程序直接起不来。
CORE = [
    "numpy",          # 全部模块都用（app/asr/屏幕翻译）
    "cffi",           # soundcard 依赖（系统声音回环录音）
    "requests",       # huggingface_hub / transformers 依赖（NLLB 离线翻译）
    "filelock",       # \
    "fsspec",         #  |
    "tqdm",           #  | huggingface_hub 的依赖
    "packaging",      #  |
    "typing-extensions",  # /
    "pillow",         # check_env 自检用
]


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "wheel-fetcher/1.0"})
    with urllib.request.urlopen(req, context=CTX, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def tag_ok(filename):
    """判断 wheel 文件名是否与当前解释器兼容。"""
    if not filename.endswith(".whl"):
        return False
    parts = filename[:-4].split("-")
    if len(parts) < 3:
        return False
    pytags, abitags, platform = parts[-3], parts[-2], parts[-1]
    ver = f"cp{sys.version_info.major}{sys.version_info.minor}"
    # abi3 轮子是向前兼容的: cp37-abi3 可用于 cp312
    abi3 = "abi3" in abitags
    if abi3:
        m = re.search(r"cp(\d)(\d+)", pytags)
        py_ok = bool(m) and (int(m.group(1)), int(m.group(2))) <= sys.version_info[:2]
    else:
        py_ok = "py3" in pytags or ver in pytags or "py2.py3" in pytags
    abi_ok = "none" in abitags or abi3 or ver in abitags
    if platform == "any":
        plat_ok = True
    else:
        plat_ok = "win_amd64" in platform
    return py_ok and abi_ok and plat_ok


def pick_wheel(pkg):
    url = f"https://pypi.org/pypi/{pkg}/json"
    data = fetch_json(url)
    version = PINNED.get(pkg) or data["info"]["version"]
    files = data["releases"].get(version, [])
    cands = [f for f in files if tag_ok(f["filename"])]
    if not cands:
        raise RuntimeError(f"{pkg}: 没有找到兼容 win_amd64/cp3x 的 wheel（版本 {version}）")
    # 优先纯 Python 包，其次体积最小的二进制包
    cands.sort(key=lambda f: (f["filename"].split("-")[-1] != "any", f["size"]))
    return version, cands[0]


def download(url, dest):
    if os.path.exists(dest):
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "wheel-fetcher/1.0"})
    with urllib.request.urlopen(req, context=CTX, timeout=300) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
    return dest


def extract(wheel_path, lib_dir):
    os.makedirs(lib_dir, exist_ok=True)
    with zipfile.ZipFile(wheel_path) as z:
        z.extractall(lib_dir)


def main():
    args = [a for a in sys.argv[1:] if a != "--core"]
    force = "--core" in sys.argv[1:] or not args
    wanted = args or list(CORE)
    if force and not args:
        print("模式: 核心包（--core）—— 把换电脑后缺失的 numpy/cffi/requests 等也装进 libs/")
    todo = list(wanted)
    for p in list(wanted):
        todo.extend(EXTRA_DEPS.get(p, []))
    explicit = {re.sub(r"[-_.]+", "-", a).lower() for a in wanted}
    seen = set()
    done = []
    for pkg in todo:
        key = re.sub(r"[-_.]+", "-", pkg).lower()
        if key in seen:
            continue
        # SKIP 里的包默认不装（假定系统/运行时已提供），但你显式点名要装就照办
        if key in SKIP and key not in explicit:
            continue
        seen.add(key)
        try:
            version, wheel = pick_wheel(pkg)
        except Exception as e:
            print(f"[SKIP] {pkg}: {e}")
            continue
        path = download(wheel["url"], os.path.join(WHEEL_DIR, wheel["filename"]))
        extract(path, LIB_DIR)
        print(f"[OK] {pkg} {version} -> {wheel['filename']} ({wheel['size']/1048576:.1f} MB)")
        done.append(pkg)
    print("\n已解包到:", LIB_DIR)
    print("共", len(done), "个包:", ", ".join(done))


if __name__ == "__main__":
    main()
