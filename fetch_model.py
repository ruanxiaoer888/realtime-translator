# -*- coding: utf-8 -*-
"""把 faster-whisper 模型（CTranslate2 格式）从 HuggingFace 下载到本地目录。

用法: python fetch_model.py small medium
下载到 tmp/models/ct2-<size>/，之后 faster_whisper 直接从本地目录加载，不再联网。
"""
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DEST_ROOT = os.path.join(ROOT, "tmp", "models")

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "model-fetcher/1.0"}
# 官方源优先，失败或限速时自动切国内镜像
HOSTS = ["https://huggingface.co", "https://hf-mirror.com"]

# Systran 的 CT2 转换版本，与 faster-whisper 官方示例一致
REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
}
# 必需文件（tokenizer 相关的小文件 + 权重 + 配置）
NEEDED = [
    "config.json", "model.bin", "tokenizer.json", "vocabulary.txt",
    "preprocessor_config.json",
]


def api(path):
    url = "https://huggingface.co" + path
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, context=CTX, timeout=60).read()


def download(repo, fname, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return os.path.getsize(dest)
    tmp = dest + ".part"
    last_err = None
    for host in HOSTS:
        url = f"{host}/{repo}/resolve/main/{urllib.parse.quote(fname)}"
        try:
            done = os.path.getsize(tmp) if os.path.exists(tmp) else 0
            headers = dict(UA)
            if done:
                headers["Range"] = f"bytes={done}-"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=CTX, timeout=3600) as r:
                # 服务器不支持续传时从头开始
                if done and r.status != 206:
                    done = 0
                total = done
                mode = "ab" if done else "wb"
                with open(tmp, mode) as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        total += len(chunk)
                        if total % (50 << 20) < (1 << 20):
                            print(f"\r    {fname}: {total/1048576:7.1f} MB", end="", flush=True)
            if total < 1024:
                raise RuntimeError("下载内容为空")
            os.replace(tmp, dest)
            print(f"\r    {fname}: {total/1048576:6.1f} MB  完成（{host.split('//')[1]}）")
            return os.path.getsize(dest)
        except Exception as e:
            last_err = e
            have = os.path.getsize(tmp) / 1048576 if os.path.exists(tmp) else 0
            print(f"\r    {fname}: {host.split('//')[1]} 中断（已下 {have:.0f} MB），换源续传…")
            continue
    raise last_err if last_err else RuntimeError("下载失败")


def main():
    sizes = sys.argv[1:] or ["small"]
    for size in sizes:
        repo = REPOS.get(size)
        if not repo:
            print(f"未知模型: {size}")
            continue
        dest_dir = os.path.join(DEST_ROOT, f"ct2-{size}")
        os.makedirs(dest_dir, exist_ok=True)
        print(f"=== {size}  ({repo}) -> {dest_dir}")
        for f in NEEDED:
            try:
                download(repo, f, os.path.join(dest_dir, f))
            except Exception as e:
                print(f"    跳过 {f}: {type(e).__name__} {e}")
        files = sorted(os.listdir(dest_dir))
        total = sum(os.path.getsize(os.path.join(dest_dir, x)) for x in files)
        print(f"    共 {len(files)} 个文件, {total/1048576:.1f} MB\n")


if __name__ == "__main__":
    main()
