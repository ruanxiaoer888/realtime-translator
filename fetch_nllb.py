# -*- coding: utf-8 -*-
"""下载 NLLB-200-distilled-600M 的 CTranslate2 int8 量化版（约 620 MB）。

用法: python fetch_nllb.py
下载到 tmp/models/nllb-ct2-int8/

⚠️ 许可提醒：NLLB-200 系列是 **CC-BY-NC-4.0（禁止商用）**。
   本项目里它只做"在线接口全挂时"的离线兜底（界面「翻译引擎」可选）。
   商用场景请自行评估，或改用其它许可的模型。
"""
import os
import ssl
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(ROOT, "tmp", "models", "nllb-ct2-int8")
REPO = "JustFrederik/nllb-200-distilled-600M-ct2-int8"
HOSTS = ["https://huggingface.co", "https://hf-mirror.com"]

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "model-fetcher/1.0"}

FILES = [
    "model.bin",
    "config.json",
    "shared_vocabulary.txt",
    "special_tokens_map.json",
    "sentencepiece.bpe.model",
    "tokenizer.json",
    "tokenizer_config.json",
]


def download(fname):
    dest = os.path.join(DEST, fname)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f"   已存在 {fname} ({os.path.getsize(dest)/1048576:.1f} MB)")
        return True
    tmp = dest + ".part"
    for host in HOSTS:
        url = f"{host}/{REPO}/resolve/main/{urllib.parse.quote(fname)}"
        try:
            done = os.path.getsize(tmp) if os.path.exists(tmp) else 0
            headers = dict(UA)
            if done:
                headers["Range"] = f"bytes={done}-"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=CTX, timeout=3600) as r:
                if done and r.status != 206:
                    done = 0
                total = done
                mode = "ab" if done else "wb"
                with open(tmp, mode) as f:
                    while True:
                        c = r.read(1 << 20)
                        if not c:
                            break
                        f.write(c)
                        total += len(c)
                        if total % (50 << 20) < (1 << 20):
                            print(f"\r    {fname}: {total/1048576:7.1f} MB", end="", flush=True)
            if total < 1024:
                raise RuntimeError("内容为空")
            os.replace(tmp, dest)
            print(f"\r    {fname}: {total/1048576:6.1f} MB  完成")
            return True
        except Exception as e:
            have = os.path.getsize(tmp)/1048576 if os.path.exists(tmp) else 0
            print(f"\r    {fname}: {host.split('//')[1]} 中断（已下 {have:.0f} MB）：{str(e)[:60]}")
            continue
    return False


os.makedirs(DEST, exist_ok=True)
print(f"下载 NLLB CT2 int8 -> {DEST}")
ok = True
for f in FILES:
    if not download(f):
        ok = False
files = sorted(os.listdir(DEST))
total = sum(os.path.getsize(os.path.join(DEST, x)) for x in files)
print(f"\n结果: {len(files)} 个文件, 共 {total/1048576:.1f} MB, {'全部成功' if ok else '有文件缺失'}")
