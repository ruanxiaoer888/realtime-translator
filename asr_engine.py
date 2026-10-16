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
# CUDA 跑不跑得起来：None=还没试过，True=试过能用，False=试过不行（以后一律走 CPU，不再重试）
_cuda_usable: bool | None = None


def model_available(size: str) -> bool:
    d = os.path.join(MODEL_ROOT, f"ct2-{size}")
    return os.path.exists(os.path.join(d, "model.bin"))


def cuda_available() -> bool:
    """有没有**能真正用起来**的 NVIDIA CUDA。

    注意：这里回答的是「现在该不该用 GPU」，不是「机器上有没有 N 卡」。
    有的机器（实测某台公司电脑）装了显卡驱动、ctranslate2.get_cuda_device_count()
    返回 1，但缺 cuBLAS/cuDNN，一直到真正识别那一刻才报
    `Library cublas64_12.dll is not found or cannot be loaded`。
    所以一旦试过失败就记下来，后面全部老老实实走 CPU。
    """
    global _cuda_usable
    if _cuda_usable is False:
        return False
    try:
        import ctranslate2
        ok = ctranslate2.get_cuda_device_count() > 0
        if not ok:
            _cuda_usable = False
        return ok
    except Exception:
        _cuda_usable = False
        return False


def cuda_failed_reason() -> str:
    """GPU 试过但不可用时的原始报错（给界面/自检显示用）。"""
    return _device_info.get("cuda_error") or ""


def device_info() -> dict:
    """当前模型跑在什么设备上（给界面显示用）。"""
    return dict(_device_info)


def _load(path: str, dev: str, ct: str):
    """加载模型，并把 glibc 的 dlopen 错误翻译成人话。"""
    from faster_whisper import WhisperModel
    try:
        return WhisperModel(path, device=dev, compute_type=ct)
    except OSError as e:
        msg = str(e)
        if ("cublas" in msg.lower() or "cudnn" in msg.lower()
                or "cuda" in msg.lower()):
            raise RuntimeError(
                "GPU 加载失败（缺 CUDA 运行库）——会自动改用 CPU。"
                f"原始报错：{msg}"
            ) from e
        raise


def _fallback_to_cpu(size: str, err: Exception):
    """GPU 用不了：换 CPU 重载模型，并把原因记进 device_info。

    只在"已经加载过 GPU 模型"之后才可能被调用（首次用 GPU 时已经在
    get_model 的候选顺序里试过 CPU 了）。
    """
    global _model, _cuda_usable, _model_size
    with _model_lock:
        _cuda_usable = False
        _device_info["cuda_error"] = str(err)[:300]
        path = os.path.join(MODEL_ROOT, f"ct2-{size}")
        _model = _load(path, "cpu", "int8")
        _device_info.update(size=size, device="cpu", compute_type="int8")
        _model_size = size


def get_model(size: str = "small", device: str = "auto", compute_type: str = ""):
    """惰性加载本地 CT2 模型。

    device="auto"：有 CUDA 就用 GPU（float16），否则直接走 CPU（int8）。
    实测没有独显也够用：small 模型 CPU int8 实时率约 0.10x，
    即 3 秒音频约 0.32 秒识别完，直播同传完全跟得上。

    注意：GPU 有两个层次会失败 —— 加载时（缺 cudnn 之类）和推理时
    （缺 cublas64_12.dll，加载不报错、一识别就崩）。前者在这里按候选顺序
    回退，后者见 transcribe() 里的 _fallback_to_cpu。
    """
    global _model, _model_size, _cuda_usable
    with _model_lock:
        if _model is not None and _model_size == size:
            return _model
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
                _model = _load(path, dev, ct)
                # GPU 有个隐蔽的坑：加载不报错，缺 cublas64_12.dll 之类要等到真正
                # 编码那一刻才炸（某台公司电脑实测）。所以这里用 0.3 秒空白音频
                # 真跑一次，当场验明正身；验不过就换 CPU，别等用户第一次听译才崩。
                if dev == "cuda":
                    _warmup_ok(_model)
                    _device_info.pop("cuda_error", None)   # GPU 真能用，清掉历史告警
                _device_info.update(size=size, device=dev, compute_type=ct)
                break
            except Exception as e:      # 缺 CUDA 运行库 / 显存不够 -> 换下一个
                last_err = e
                _model = None
                if dev == "cuda":
                    # 把结论钉死：这台机器以后一律走 CPU，别再试、别在界面上
                    # 显示"CUDA 可用"（显示成可用但实际用不了最误导人）。
                    _cuda_usable = False
                    _device_info["cuda_error"] = f"GPU 试跑失败，已降级 CPU：{str(e)[:240]}"
        if _model is None:
            raise RuntimeError(f"模型加载失败：{last_err}")
        _model_size = size
        return _model


def _run(model, audio, language, beam_size, use_prompt):
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
    return " ".join(s.text.strip() for s in segments).strip()


def _warmup_ok(model):
    """用 0.3 秒静音真跑一次编码，验证 GPU 运行库是否真的齐全。

    VOICE 之外的坑：ctranslate2 加载 CUDA 模型时不校验 cublas/cudnn，
    真正的 dlopen 发生在第一次 encode。所以必须真跑，不能只看设备数。
    """
    audio = np.zeros(int(SAMPLE_RATE * 0.3), dtype=np.float32)
    segments, _info = model.transcribe(audio, language=None, beam_size=1,
                                       vad_filter=False, condition_on_previous_text=False)
    list(segments)          # 生成器要消费掉，否则编码根本没发生
    return True


def transcribe(audio: np.ndarray, language: str = "pt", size: str = "small",
               use_prompt: bool = True, beam_size: int = 1) -> tuple[str, float]:
    """识别一段音频，返回 (文本, 识别耗时秒)。language 由市场配置决定。

    GPU 在**推理时**才暴露的问题（典型：缺 cublas64_12.dll）在这里兜住：
    自动换回 CPU 重跑一次，而不是让整个听译线程挂掉。
    """
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size < SAMPLE_RATE * 0.3:
        return "", 0.0
    model = get_model(size)
    peak = float(np.abs(audio).max())
    if peak > 0:
        audio = audio / max(peak, 0.05) * 0.9
    t0 = time.time()
    try:
        text = _run(model, audio, language, beam_size, use_prompt)
    except (RuntimeError, OSError) as e:
        msg = str(e).lower()
        if _device_info.get("device") == "cuda" and (
                "cublas" in msg or "cudnn" in msg or "cuda" in msg):
            _fallback_to_cpu(size, e)
            text = _run(_model, audio, language, beam_size, use_prompt)
        else:
            raise
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
