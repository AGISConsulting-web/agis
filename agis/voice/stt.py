"""Riconoscimento vocale locale e gratuito con faster-whisper."""
from __future__ import annotations

import numpy as np


class SpeechToText:
    def __init__(self, model_size: str = "small", language: str = "it"):
        from faster_whisper import WhisperModel
        # int8 su CPU: va su qualsiasi PC Windows senza scheda video dedicata.
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        self.language = language

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size < 1600:  # meno di 0,1 s: niente da trascrivere
            return ""
        segments, _ = self.model.transcribe(
            audio, language=self.language, vad_filter=True, beam_size=5)
        return " ".join(s.text.strip() for s in segments).strip()
