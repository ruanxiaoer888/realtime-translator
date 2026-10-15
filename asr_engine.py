# -*- coding: utf-8 -*-
"""低延迟流式识别引擎：faster-whisper(CTranslate2/GPU) + VAD 智能切句。

和旧版（固定 4 秒切一段）的区别：
  1. 用 VAD 检测说话停顿，**说完一句就出字幕**，不用死等 4 秒
  2. CTranslate2 推理，实测实时率 0.01x 量级（同模型比 openai-whisper 快数倍）
  3. 分段之间保留一小段音频重叠，避免切掉词头
  4. 给葡语电商场景注入提示词（工具类目词汇），提升专有名词识别率

单独测试:
    python asr_engine.py --selftest
"""
from __future__ import annotations

import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402

SAMPLE_RATE = 16000
MODEL_ROOT = os.path.join(ROOT, "tmp", "models")

# 术语表：按市场/品类动态设置（原来是写死的葡语五金词）
#   set_terminology(prompt=识别提示词, glossary={原文: 中文})
_asr_prompt: str = ""
_glossary: dict[str, str] = {}


def set_terminology(prompt: str = "", glossary: dict | None = None):
    """由界面按所选市场/品类注入识别提示词和术语表。"""
    global _asr_prompt, _glossary
    _asr_prompt = prompt or ""
    _glossary = dict(glossary or {})


def get_asr_prompt() -> str:
    return _asr_prompt


def get_glossary() -> dict[str, str]:
    return dict(_glossary)

_model = None
_model_size = None
_model_lock = threading.Lock()
_device_info: dict = {"size": None, "device": None, "compute_type": None}


def model_available(size: str) -> bool:
    d = os.path.join(MODEL_ROOT, f"ct2-{size}")
    return os.path.exists(os.path.join(d, "model.bin"))


def cuda_available() -> bool:
    """有没有能用的 NVIDIA CUDA（没装 CUDA 运行库的机器会返回 False）。"""
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def device_info() -> dict:
    """当前模型跑在什么设备上（给界面显示用）。"""
    return dict(_device_info)


def get_model(size: str = "small", device: str = "auto", compute_type: str = ""):
    """惰性加载本地 CT2 模型。

    device="auto"：有 CUDA 就用 GPU（float16），否则直接走 CPU（int8）。
    实测没有独显也够用：small 模型 CPU int8 实时率约 0.10x，
    即 3 秒音频约 0.32 秒识别完，直播同传完全跟得上。
    """
    global _model, _model_size
    with _model_lock:
        if _model is not None and _model_size == size:
            return _model
        from faster_whisper import WhisperModel
        path = os.path.join(MODEL_ROOT, f"ct2-{size}")
        if not model_available(size):
            raise FileNotFoundError(
                f"本地没有 {size} 模型，先运行：python fetch_model.py {size}"
            )

        if device == "auto":
            order = [("cuda", "float16"), ("cpu", "int8")] if cuda_available() \
                else [("cpu", "int8")]
        elif device == "cpu":
            order = [("cpu", compute_type or "int8")]
        else:
            order = [(device, compute_type or "float16"), ("cpu", "int8")]

        last_err = None
        for dev, ct in order:
            try:
                _model = WhisperModel(path, device=dev, compute_type=ct)
                _device_info.update(size=size, device=dev, compute_type=ct)
                break
            except Exception as e:      # 缺 CUDA 运行库 / 显存不够 -> 换下一个
                last_err = e
                _model = None
        if _model is None:
            raise RuntimeError(f"模型加载失败：{last_err}")
        _model_size = size
        return _model


def transcribe(audio: np.ndarray, language: str = "pt", size: str = "small",
               use_prompt: bool = True, beam_size: int = 1) -> tuple[str, float]:
    """识别一段音频，返回 (文本, 识别耗时秒)。language 由市场配置决定。"""
    model = get_model(size)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size < SAMPLE_RATE * 0.3:
        return "", 0.0
    peak = float(np.abs(audio).max())
    if peak > 0:
        audio = audio / max(peak, 0.05) * 0.9
    t0 = time.time()
    segments, _info = model.transcribe(
        audio,
        language=language or None,
        beam_size=beam_size,
        vad_filter=True,
        # speech_pad_ms 原来是 100（比 faster-whisper 默认 400 小得多），会在切句时
        # 削掉词头 —— 真实字幕里 parafusadeira 被听成 usadeira / paposeira、
        # "Hoje eu trouxe" 丢成 "hoje trouxe"、caixa 拼成 caja、标点全丢，
        # 都是同一段音频的对比实验里 100 -> 400 之后一起好转的（详见
        # tools\bench_asr_options.py）。耗时反而从 0.62s 降到 0.28s：留白够大时
        # 相邻语音块会合并，调用次数变少。
        vad_parameters={"min_silence_duration_ms": 300, "speech_pad_ms": 400},
        condition_on_previous_text=False,
        initial_prompt=(_asr_prompt or None) if use_prompt else None,
        no_speech_threshold=0.6,
    )
    text = " ".join(s.text.strip() for s in segments).strip()
    return text, time.time() - t0


class StreamingSegmenter:
    """把连续音频流切成"说完一句就提交"的段。

    静音判定阈值会在开始时自动校准：先听一小会儿环境底噪，再据此设阈值，
    避免因为回环录音底噪偏高而永远等不到停顿（那样就会一直拖到 max_seconds）。
    """

    def __init__(self, max_seconds: float = 7.0, min_seconds: float = 1.5,
                 silence_seconds: float = 0.35, overlap_seconds: float = 0.25,
                 silence_rms: float | None = None, calibrate_seconds: float = 0.5):
        self.max_seconds = max_seconds
        self.min_seconds = min_seconds
        self.silence_seconds = silence_seconds
        self.overlap_seconds = overlap_seconds
        self.calibrate_seconds = calibrate_seconds
        self.buf: list[np.ndarray] = []
        self.silence_run = 0.0
        self.carry: np.ndarray | None = None
        # 未校准时先给一个宽松初值
        self.silence_rms = silence_rms if silence_rms is not None else 0.006
        self._fixed = silence_rms is not None
        self._noise_samples: list[float] = []
        self._calibrated = self._fixed
        self._calib_elapsed = 0.0
        # 动态底噪跟踪：取"近段最安静的水平"，底噪降低时阈值跟着降
        self._floor = 0.006

    def _calibrate(self, block: np.ndarray):
        """用开头的音频估计底噪，阈值取 底噪的 1.6 倍（夹在 0.0008~0.012 之间）。

        上限刻意压低：阈值过高会把主播轻声说话也当静音，字幕就不再按时出现，
        这比"偶尔多识别一次"糟糕得多。
        """
        if self._calibrated:
            return
        self._noise_samples.append(float(np.sqrt(np.mean(np.square(block)))))
        self._calib_elapsed += block.size / SAMPLE_RATE
        if self._calib_elapsed >= self.calibrate_seconds:
            base = float(np.percentile(self._noise_samples, 30))
            self._floor = base
            self.silence_rms = min(0.012, max(0.0008, base * 1.6))
            self._calibrated = True

    def _adapt_floor(self, rms: float):
        """动态底噪跟踪：安静时较快下调，嘈杂时极慢上调。

        升得慢是关键：主播有一段响声音乐/喊话时，不能把底噪估计拉高，
        否则之后轻声说话会被误判成静音、字幕就不出来了。
        """
        if rms < self._floor:
            self._floor = self._floor * 0.97 + rms * 0.03
        else:
            self._floor = self._floor * 0.99995 + rms * 0.00005
        self._floor = max(0.0003, min(0.02, self._floor))
        if self._calibrated:
            self.silence_rms = min(0.012, max(0.0008, self._floor * 1.6))

    def speech_level(self, audio: np.ndarray) -> float:
        """一段音频的语音电平（取较响部分的均值，比整体 RMS 更能反映人声）。"""
        if audio.size == 0:
            return 0.0
        frames = audio[: (audio.size // 1600) * 1600].reshape(-1, 1600)
        if frames.size == 0:
            return float(np.sqrt(np.mean(np.square(audio))))
        rms = np.sqrt(np.mean(frames ** 2, axis=1))
        return float(np.percentile(rms, 75))

    def trim(self, audio: np.ndarray, pad_ms: int = 120) -> np.ndarray:
        """裁掉首尾的静音，减少喂给模型的无效音频（更快也更准）。"""
        if audio.size < 1600:
            return audio
        frames = audio[: (audio.size // 1600) * 1600].reshape(-1, 1600)
        rms = np.sqrt(np.mean(frames ** 2, axis=1))
        voiced = np.where(rms >= self.silence_rms)[0]
        if voiced.size == 0:
            return audio
        pad = max(1, int(pad_ms / 100))
        lo = max(0, voiced[0] - pad) * 1600
        hi = min(len(frames), voiced[-1] + 1 + pad) * 1600
        return audio[lo:hi]

    def _audio(self) -> np.ndarray:
        parts = ([self.carry] if self.carry is not None and self.carry.size else []) + self.buf
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)

    def push(self, block: np.ndarray) -> np.ndarray | None:
        """喂一块音频；够一句了就返回该段音频，否则返回 None。"""
        block = np.asarray(block, dtype=np.float32)
        if block.size == 0:
            return None
        self._calibrate(block)
        self.buf.append(block)
        dur = block.size / SAMPLE_RATE
        rms = float(np.sqrt(np.mean(np.square(block)))) if block.size else 0.0
        self._adapt_floor(rms)
        if rms < self.silence_rms:
            self.silence_run += dur
        else:
            self.silence_run = 0.0

        total = sum(x.size for x in self.buf) / SAMPLE_RATE
        if self.carry is not None:
            total += self.carry.size / SAMPLE_RATE

        ready = False
        if total >= self.max_seconds:
            ready = True
        elif total >= self.min_seconds and self.silence_run >= self.silence_seconds:
            ready = True
        if not ready:
            return None

        audio = self._audio()
        keep = int(self.overlap_seconds * SAMPLE_RATE)
        self.carry = audio[-keep:] if keep and audio.size > keep else None
        self.buf = []
        self.silence_run = 0.0
        return audio

    def flush(self) -> np.ndarray | None:
        audio = self._audio()
        self.buf = []
        self.carry = None
        self.silence_run = 0.0
        return audio if audio.size > SAMPLE_RATE * 0.3 else None


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        import wave
        wav = os.path.join(ROOT, "tmp", "speech16k.wav")
        if not os.path.exists(wav):
            print("缺少 tmp/speech16k.wav")
            sys.exit(1)
        with wave.open(wav, "rb") as w:
            a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype("float32") / 32768.0
        for size in [s for s in ("small", "medium", "large-v3") if model_available(s)]:
            txt, dt = transcribe(a, language="en", size=size)
            print(f"[{size}] {dt:.2f}s  {txt!r}")
        print("\n已就绪的模型:", [s for s in ("small", "medium", "large-v3") if model_available(s)])
    else:
        print(__doc__)
