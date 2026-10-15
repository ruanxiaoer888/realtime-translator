# -*- coding: utf-8 -*-
"""对照实验：把 RapidOCR 的识别模型从中文 ch_PP-OCRv4 换成拉丁语系模型，看重音能否救回来。

只读实验脚本，不改动项目任何文件；只往 tmp/models/ocr-latin/ 下载模型。
运行（项目根目录）:
    python tmp\\audit_ocr_latin.py

基线（中文模型）由 tmp/audit_ocr.py 测出，本脚本用同一套渲染/指标再测一遍拉丁模型，
两边数字可直接对比。
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "libs"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

import numpy as np  # noqa: E402
import screen_translate as st  # noqa: E402

import audit_ocr as base  # noqa: E402  复用同一套渲染 + CER 指标

REPO = "monkt/paddleocr-onnx"
DEST = os.path.join(ROOT, "tmp", "models", "ocr-latin")
FILES = {
    "rec.onnx": "languages/latin/rec.onnx",
    "dict.txt": "languages/latin/dict.txt",
    "config.json": "languages/latin/config.json",
}
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
HOSTS = ["https://huggingface.co", "https://hf-mirror.com"]

ACCENTS = "ãçéêíóõúñáàâüö¿"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ocr-model-check/1.0"})
    with urllib.request.urlopen(req, context=CTX, timeout=300) as r:
        return r.read()


def download(rel: str, name: str) -> str:
    os.makedirs(DEST, exist_ok=True)
    dest = os.path.join(DEST, name)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f"  已存在 {name} ({os.path.getsize(dest)/1048576:.1f} MB)")
        return dest
    last = None
    for host in HOSTS:
        try:
            data = fetch(f"{host}/{REPO}/resolve/main/{rel}")
            if len(data) < 128:
                raise RuntimeError("内容异常")
            with open(dest, "wb") as f:
                f.write(data)
            print(f"  下载 {name} <- {host.split('//')[1]}  ({len(data)/1048576:.1f} MB)")
            return dest
        except Exception as e:
            last = e
            print(f"  {host.split('//')[1]} 失败: {str(e)[:70]}")
    raise RuntimeError(f"{name} 下载失败: {last}")


def main():
    print("#" * 78)
    print("对照实验：拉丁语系 rec 模型 vs 当前中文 rec 模型")
    print(f"来源仓库: {REPO}  ->  {DEST}")
    print("#" * 78)

    paths = {name: download(rel, name) for name, rel in FILES.items()}

    dict_chars = [ln.strip("\n") for ln in open(paths["dict.txt"], encoding="utf-8") if ln.strip("\n")]
    print(f"\n[字典] dict.txt 字符数 = {len(dict_chars)}")
    missing = [c for c in ACCENTS if c not in dict_chars]
    print(f"[字典] 重音字符检查（U+XXXX IN/MISSING）:")
    for c in ACCENTS:
        print(f"    U+{ord(c):04X}  {'IN' if c in dict_chars else 'MISSING'}")

    print("\n[构造引擎] RapidOCR(rec_model_path=latin, rec_keys_path=dict.txt)")
    from rapidocr_onnxruntime import RapidOCR
    engine = RapidOCR(rec_model_path=paths["rec.onnx"], rec_keys_path=paths["dict.txt"])

    sess = engine.text_rec.session
    try:
        in_shape = [(i.name, i.shape) for i in sess.get_inputs()]
        out_shape = [(o.name, o.shape) for o in sess.get_outputs()]
        print(f"    onnx 输入 : {in_shape}")
        print(f"    onnx 输出 : {out_shape}")
    except Exception as e:
        print(f"    (读 onnx 形状失败: {e})")

    chars = list(engine.text_rec.postprocess_op.character)
    print(f"    引擎实际字符表长度 = {len(chars)}（含 blank 与 space 两个特殊位）")
    for c in ACCENTS:
        if c not in chars:
            print(f"    !! 引擎字符表里仍然没有 U+{ord(c):04X}")

    st._ocr_engine = engine          # 让 screen_translate.recognize 用这个引擎
    print("\n" + "#" * 78)
    print("用 tmp/audit_ocr.py 的同一套图与指标重测")
    print("#" * 78 + "\n")

    base.run_case("PT size=18 [LATIN]", base.PT_LINES, 18)
    base.run_case("PT size=14 [LATIN]", base.PT_LINES, 14)
    base.run_case("ES size=18 [LATIN]", base.ES_LINES, 18)
    base.run_case("ES size=14 [LATIN]", base.ES_LINES, 14)

    img = base.render(base.PT_LINES, size=18)
    import time
    warm = []
    for _ in range(3):
        t0 = time.perf_counter()
        engine(img)
        warm.append((time.perf_counter() - t0) * 1000.0)
    print("=" * 78)
    print(f"拉丁模型热态耗时 (900x420 PT18): {', '.join(f'{w:.1f}' for w in warm)} ms")
    print(f"模型文件: {json.dumps(FILES, ensure_ascii=False)}")
    print("=" * 78)


if __name__ == "__main__":
    main()
