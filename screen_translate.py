# -*- coding: utf-8 -*-
"""实时屏幕翻译：框选一块屏幕区域 -> 持续 OCR 识别葡萄牙语 -> 实时显示中文。

和截图翻译的区别：框一次就一直在翻，画面里文字一变就更新，不用反复截图。
适用：直播评论、商品标题、后台字段、弹窗提示、其他 App 界面。

独立测试用:
    python screen_translate.py            # 启动界面
    python screen_translate.py --once 400,300,900,700   # 对指定区域识别一次并打印
"""
from __future__ import annotations

import os
import sys
import threading
import time
import warnings

warnings.filterwarnings("ignore", message="mss.mss is deprecated")

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "libs"))

import numpy as np  # noqa: E402

# 拉丁语系识别模型（tmp/models/ocr-latin/），由 fetch_ocr_model.py 下载。
# 自带的中文模型字典里没有 ã ç ê õ ñ â ¿，葡语/西语重音和词间空格会被吃掉，
# 实测字错率 0.03~0.19；换成拉丁模型后同样几张图字错率 0.0000。
OCR_LATIN_DIR = os.path.join(ROOT, "tmp", "models", "ocr-latin")

_ocr_engine = None
_ocr_engine_key = None
_ocr_lock = threading.Lock()


def latin_model_paths() -> tuple[str | None, str | None]:
    """拉丁识别模型的文件路径；缺文件时返回 (None, None)。"""
    rec = os.path.join(OCR_LATIN_DIR, "rec.onnx")
    keys = os.path.join(OCR_LATIN_DIR, "dict.txt")
    if os.path.exists(rec) and os.path.exists(keys):
        return rec, keys
    return None, None


def latin_available() -> bool:
    return latin_model_paths()[0] is not None


def get_ocr(engine: str = "auto"):
    """惰性加载 RapidOCR（首次加载约 2-5 秒）。

    engine:
        "auto"  优先用拉丁模型，缺文件时退回自带中文模型（默认）
        "latin" 只用拉丁模型（专治葡语/西语重音）
        "ch"    只用自带中文模型（框选区域里是中文界面时用）
    """
    global _ocr_engine, _ocr_engine_key
    rec, keys = latin_model_paths()
    if engine == "latin" and not rec:
        engine = "ch"
    if engine == "auto":
        engine = "latin" if rec else "ch"

    with _ocr_lock:
        if _ocr_engine is not None and _ocr_engine_key == engine:
            return _ocr_engine
        from rapidocr_onnxruntime import RapidOCR
        if engine == "latin":
            try:
                _ocr_engine = RapidOCR(rec_model_path=rec, rec_keys_path=keys)
                _ocr_engine_key = "latin"
                return _ocr_engine
            except Exception:
                engine = "ch"      # 拉丁模型坏了也不能让功能停掉
        _ocr_engine = RapidOCR()
        _ocr_engine_key = "ch"
    return _ocr_engine


def ocr_engine_name() -> str:
    """当前生效的识别模型名字（给自检和界面显示用）。"""
    return "拉丁语系模型 latin rec" if latin_available() else "内置中文模型 ch_PP-OCRv4"


# 画面指纹：32x16 个格子，每格取**块内所有像素的灰度均值**。
# 关键点：老版本每格只采 1 个像素，一行文字最多只能影响 1 个采样行 = 17/289 = 5.88%，
# 低于 6% 的阈值，所以"新来一条评论"这种单行变化永远触发不了重新识别。
#
# 阈值是实测定的（512 格，合成评论图）：
#   单行整条换新 -> 差异 >2 的有 7 格 = 1.37%      整屏滚动 -> 66 格 = 12.9%
#   ±3 灰度噪点  -> 差异 >2 的有 0 格（最大差 1）  完全相同 -> 0 格
# 所以 CELL_DIFF=2 就能把噪点挡在外面，阈值取 0.5%（约 2.6 格）。
GRID_COLS = 32
GRID_ROWS = 16
CELL_DIFF = 2.0        # 单格灰度均值差超过它才算这格变了
CHANGE_RATIO = 0.005   # 变化格占比超过它才算画面变了（512 格里约 2.6 格）


def frame_signature(rgb) -> tuple:
    """画面指纹：把区域压成 GRID_ROWS x GRID_COLS 的块均值小图，用于判断画面有没有变化。"""
    h, w = rgb.shape[:2]
    if h == 0 or w == 0:
        return ()
    gray = rgb.mean(axis=2).astype(np.float32)
    rows = max(1, min(GRID_ROWS, h))
    cols = max(1, min(GRID_COLS, w))
    bh = max(1, h // rows)
    bw = max(1, w // cols)
    gh, gw = max(1, h // bh), max(1, w // bw)
    g = gray[: gh * bh, : gw * bw]
    blocks = g.reshape(gh, bh, gw, bw).mean(axis=(1, 3))
    return tuple(np.rint(blocks).astype(np.int16).ravel().tolist())


def signature_changed(a: tuple, b: tuple, threshold: float = CHANGE_RATIO) -> bool:
    """指纹差异超过阈值才算画面变了。"""
    if not a or not b or len(a) != len(b):
        return True
    diff = sum(1 for x, y in zip(a, b) if abs(int(x) - int(y)) > CELL_DIFF)
    return diff / max(1, len(a)) > threshold


def grab(region):
    """抓取屏幕区域，返回 RGB numpy 数组。region=(left, top, width, height)。"""
    import mss
    left, top, width, height = region
    with mss.mss() as sct:
        shot = sct.grab({"left": int(left), "top": int(top), "width": int(width), "height": int(height)})
        img = np.asarray(shot)  # BGRA
    return img[:, :, [2, 1, 0]].copy()


def recognize(rgb) -> list[tuple[str, float]]:
    """对图像做 OCR，返回 [(文本, 置信度), ...]，按从上到下、从左到右排序。"""
    engine = get_ocr()
    result, _ = engine(rgb)
    if not result:
        return []
    items = []
    for box, text, score in result:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        items.append((min(ys), min(xs), str(text).strip(), float(score)))
    items.sort(key=lambda x: (round(x[0] / 12), x[1]))
    return [(t, s) for _, _, t, s in items if t]


def merge_lines(texts: list[tuple[str, float]], min_score: float = 0.5) -> str:
    """把 OCR 结果拼成一段可翻译的文本。"""
    picked = [t for t, s in texts if s >= min_score]
    if not picked:
        picked = [t for t, _ in texts]
    return " ".join(picked).strip()


def ocr_region(region, min_score: float = 0.5) -> tuple[str, list[tuple[str, float]]]:
    rgb = grab(region)
    items = recognize(rgb)
    return merge_lines(items, min_score), items


if __name__ == "__main__":
    if "--once" in sys.argv:
        arg = sys.argv[sys.argv.index("--once") + 1]
        box = tuple(int(x) for x in arg.split(","))
        t0 = time.time()
        text, items = ocr_region(box)
        print(f"识别耗时 {time.time()-t0:.2f}s")
        print("原文:", text)
        out = []
        for t, s in items:
            out.append(f"  {s:.2f}  {t}")
        print("\n".join(out))
    else:
        print("请通过 app.py 启动界面")
