# -*- coding: utf-8 -*-
"""git-free 拉取：比对本地与 GitHub 的 blob SHA，只下载有变化的文件。

**为什么不用 git**：DSH 沙箱里这个 git 构建只编译了 schannel 后端，而沙箱
禁止它访问 Windows 凭据库，任何 HTTPS git 操作都会失败：
    schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS
而同一个沙箱里 Python 的网络是**完全正常**的（api/raw/codeload 实测 200）。
所以拉取这件事让 AI 自己用 Python 做，不要麻烦人。

用法（在项目根目录）:
    py -3.12 tools/dsh_pull.py                  # 只看差异，不写盘（默认）
    py -3.12 tools/dsh_pull.py --apply          # 真正写入
    py -3.12 tools/dsh_pull.py --apply --tools  # 连 tools/ 一起更新
    py -3.12 tools/dsh_pull.py --branch dev     # 换分支

默认**跳过 tools/**：各台机器上的辅助脚本常带本机路径，覆盖掉可能破坏现场。
新增文件（远程有、本地没有）会被创建；本地多出来的文件只报告、不删除。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request

OWNER = "ruanxiaoer888"
REPO = "realtime-translator"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_PREFIXES = (".git/",)


def api(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "dsh-agent"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def blob_sha(path: str) -> str:
    """Git blob SHA-1 = sha1("blob <len>\\0" + content)，与 git 完全一致。"""
    with open(path, "rb") as f:
        data = f.read()
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正写入（默认只报告）")
    ap.add_argument("--tools", action="store_true", help="连 tools/ 目录也更新")
    ap.add_argument("--branch", default="main")
    args = ap.parse_args()

    print("仓库: %s/%s   分支: %s" % (OWNER, REPO, args.branch))
    # 1) 远端 HEAD
    try:
        head = json.loads(api("https://api.github.com/repos/%s/%s/commits/%s"
                              % (OWNER, REPO, args.branch)))
    except Exception as e:
        print("!! 取远端 HEAD 失败: %r" % (e,))
        return 1
    print("远端 HEAD: %s" % head["sha"][:10])
    print("            %s" % head["commit"]["message"].splitlines()[0])

    # 2) 文件树
    tree = json.loads(api("https://api.github.com/repos/%s/%s/git/trees/%s?recursive=1"
                          % (OWNER, REPO, head["sha"])))
    blobs = [t for t in tree.get("tree", []) if t["type"] == "blob"]
    print("远端文件: %d 个" % len(blobs))

    changed, new, same, skipped = [], [], [], []
    for item in blobs:
        rel = item["path"]
        if any(rel.startswith(p) for p in SKIP_PREFIXES):
            continue
        if rel.startswith("tools/") and not args.tools:
            skipped.append(rel)
            continue
        local = os.path.join(ROOT, rel.replace("/", os.sep))
        if not os.path.exists(local):
            new.append(rel)
        elif blob_sha(local) != item["sha"]:
            changed.append(rel)
        else:
            same.append(rel)

    print("\n一致 %d 个 ｜ 有变化 %d 个 ｜ 本地缺 %d 个 ｜ 跳过(tools) %d 个"
          % (len(same), len(changed), len(new), len(skipped)))
    for rel in changed:
        print("  M  %s" % rel)
    for rel in new:
        print("  +  %s  (新增)" % rel)
    if not changed and not new:
        print("\n已经是最新，无需操作。")
        return 0

    if not args.apply:
        print("\n（这是预览。要真正写入，加 --apply）")
        return 0

    # 3) 下载并写入
    ok = fail = 0
    for rel in changed + new:
        url = "https://raw.githubusercontent.com/%s/%s/%s/%s" % (OWNER, REPO, head["sha"], rel)
        dst = os.path.join(ROOT, rel.replace("/", os.sep))
        try:
            data = api(url, timeout=30)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(data)
            print("  写入 %-40s %8d 字节" % (rel, len(data)))
            ok += 1
        except Exception as e:
            print("  失败 %-40s %r" % (rel, e))
            fail += 1
        time.sleep(0.2)

    print("\n完成：写入 %d 个，失败 %d 个" % (ok, fail))
    print("提示：libs/ tmp/ 记录/ settings.json 不在仓库里，本脚本不会碰它们。")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
