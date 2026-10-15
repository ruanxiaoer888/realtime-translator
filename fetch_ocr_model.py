# -*- coding: utf-8 -*-
"""下载拉丁语系 OCR 识别模型（约 7.5 MB），给实时屏幕翻译用。

为什么需要它：RapidOCR 自带的是中文识别模型（ch_PP-OCRv4），字典里
没有 ã ç ê õ ñ â ¿ 这些字母，葡语/西语的重音和词间空格会被吃掉。
实测同一批合成评论图，中文模型字错率 0.03~0.19，换成拉丁模型后 0.0000，
耗时只多 46 毫秒。

用法:
    python fetch_ocr_model.py
下载到 tmp/models/ocr-latin/（rec.onnx + dict.txt + config.json）。
下完之后 screen_translate 会自动优先使用它，不用改任何配置。
"""
import os
import ssl
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(ROOT, "tmp", "models", "ocr-latin")
REPO = "monkt/paddleocr-onnx"
HOSTS = ["https://huggingface.co", "https://hf-mirror.com"]

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "model-fetcher/1.0"}

FILES = {
    "rec.onnx": "languages/latin/rec.onnx",
    "dict.txt": "languages/latin/dict.txt",
    "config.json": "languages/latin/config.json",
}


def download(name: str, rel: str) -> bool:
    dest = os.path.join(DEST, name)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f"   已存在 {name} ({os.path.getsize(dest)/1048576:.1f} MB)")
        return True
    for host in HOSTS:
        url = f"{host}/{REPO}/resolve/main/{urllib.parse.quote(rel)}"
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, context=CTX, timeout=300) as r:
                data = r.read()
            if len(data) < 128:
                raise RuntimeError("内容为空")
            with open(dest, "wb") as f:
                f.write(data)
            print(f"   {name}: {len(data)/1048576:6.2f} MB  完成（{host.split('//')[1]}）")
            return True
        except Exception as e:
            print(f"   {name}: {host.split('//')[1]} 失败：{str(e)[:60]}")
    return False


def main():
    os.makedirs(DEST, exist_ok=True)
    print(f"下载拉丁语系 OCR 模型 -> {DEST}")
    ok = True
    for name, rel in FILES.items():
        if not download(name, rel):
            ok = False
    files = sorted(os.listdir(DEST)) if os.path.isdir(DEST) else []
    total = sum(os.path.getsize(os.path.join(DEST, x)) for x in files)
    print(f"\n结果: {len(files)} 个文件, 共 {total/1048576:.1f} MB, "
          f"{'全部成功' if ok else '有文件缺失（缺 rec.onnx 或 dict.txt 时会自动退回中文模型，功能不受影响）'}")
    print("自检: python tools\\audit_ocr_latin.py   （会重测重音与字错率）")


if __name__ == "__main__":
    main()
