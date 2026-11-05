"""Registrazione dal microfono (premi per iniziare, premi di nuovo per finire)."""
from __future__ import annotations

import threading

import numpy as np


class Recorder:
    def __init__(self, sample_rate: int = 16000):
        import sounddevice as sd  # import tardivo: serve solo con la voce attiva
        self._sd = sd
        self.sample_rate = sample_rate
        self._chunks: list[np.ndarray] = []
        self._stream = None
        self._lock = threading.Lock()

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def _callback(self, indata, frames, time, status):  # noqa: ARG002
        with self._lock:
            self._chunks.append(indata[:, 0].copy())

    def start(self) -> None:
        if self._stream:
            return
        self._chunks = []
        self._stream = self._sd.InputStream(
            samplerate=self.sample_rate, channels=1, dtype="float32",
            callback=self._callback)
        self._stream.start()

    def stop(self) -> np.ndarray:
        if not self._stream:
            return np.zeros(0, dtype=np.float32)
        self._stream.stop()
        self._stream.close()
        self._stream = None
        with self._lock:
            audio = np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)
        return audio
