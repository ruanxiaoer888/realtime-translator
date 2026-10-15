# -*- coding: utf-8 -*-
"""直播同传：抓系统声音(WASAPI 回环) -> Whisper 识别葡语 -> 翻译成中文。

不占用麦克风，不需要开“立体声混音”，直接录扬声器输出。
独立测试:
    python live_caption.py --loopback 12      # 录 12 秒并打印识别+翻译结果
    python live_caption.py --wav a.wav 12     # 录 12 秒保存 wav
"""
from __future__ import annotations

import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "libs"))

import numpy as np  # noqa: E402

SAMPLE_RATE = 16000
_whisper_model = None
_model_lock = threading.Lock()


def get_model(size: str = "small"):
    """加载识别模型（优先新的 faster-whisper/CT2 引擎）。"""
    import asr_engine
    return asr_engine.get_model(size)


def transcribe(audio: np.ndarray, language: str = "pt", model_size: str = "small") -> str:
    """识别一段音频中的葡语文本（faster-whisper，失败回退 openai-whisper）。"""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size < SAMPLE_RATE // 2:
        return ""
    try:
        import asr_engine
        text, _dt = asr_engine.transcribe(audio, language=language, size=model_size)
        return text
    except Exception:
        pass
    # 回退：老的 openai-whisper 路径
    import whisper
    model = _get_openai_model(model_size)
    peak = float(np.abs(audio).max())
    if peak > 0:
        audio = audio / max(peak, 0.05) * 0.9
    res = model.transcribe(
        audio,
        language=language,
        fp16=False,
        condition_on_previous_text=False,
        no_speech_threshold=0.6,
        logprob_threshold=-1.0,
    )
    return (res.get("text") or "").strip()


_openai_models: dict = {}


def _get_openai_model(size: str):
    global _openai_models
    if size not in _openai_models:
        import whisper
        _openai_models[size] = whisper.load_model(size)
    return _openai_models[size]


class LoopbackRecorder:
    """WASAPI 回环录音，float32 单声道 16kHz。"""

    def __init__(self, samplerate: int = SAMPLE_RATE):
        import soundcard as sc
        self.samplerate = samplerate
        self._sc = sc
        speaker = sc.default_speaker()
        self.device_name = speaker.name
        self._mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        # soundcard 走 WASAPI/COM，子线程必须先初始化 COM
        try:
            import ctypes
            ctypes.windll.ole32.CoInitializeEx(None, 0)
        except Exception:
            pass
        try:
            with self._mic.recorder(samplerate=self.samplerate, channels=2, blocksize=1600) as rec:
                while not self._stop.is_set():
                    data = rec.record(numframes=1600)
                    mono = data.mean(axis=1) if data.ndim > 1 else data
                    with self._lock:
                        self._chunks.append(mono.astype(np.float32))
        except Exception as e:  # 录音设备被占用/被禁用
            with self._lock:
                self._error = e

    def take(self) -> np.ndarray:
        """取走已录到的音频，清空缓冲。"""
        with self._lock:
            if not self._chunks:
                return np.zeros(0, dtype=np.float32)
            buf = np.concatenate(self._chunks)
            self._chunks = []
        return buf

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)


def rms(audio: np.ndarray) -> float:
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio))))


def record_seconds(seconds: float) -> tuple[np.ndarray, str]:
    rec = LoopbackRecorder()
    rec.start()
    time.sleep(seconds)
    rec.stop()
    return rec.take(), rec.device_name


if __name__ == "__main__":
    args = sys.argv[1:]
    lang = "pt"
    model_size = "small"
    if "--loopback" in args or "--wav" in args:
        key = "--loopback" if "--loopback" in args else "--wav"
        secs = float(args[args.index(key) + 1])
        audio, dev = record_seconds(secs)
        print(f"录音设备: {dev}  时长: {audio.size/SAMPLE_RATE:.1f}s  音量RMS: {rms(audio):.4f}")
        if key == "--wav":
            out = args[args.index(key) + 1].replace(".", "_") + ".wav"
            import wave
            with wave.open(os.path.join(ROOT, "tmp", "cap.wav"), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SAMPLE_RATE)
                w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
            print("已保存 tmp/cap.wav")
        else:
            t0 = time.time()
            text = transcribe(audio, lang, model_size)
            print(f"识别耗时 {time.time()-t0:.2f}s")
            print("葡语原文:", text)
            if text:
                from translate_core import translate
                print("中文翻译:", translate(text))
    else:
        print(__doc__)
