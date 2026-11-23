"""Riconoscimento vocale locale e gratuito con faster-whisper."""
from __future__ import annotations

import numpy as np


# Nomi che Whisper altrimenti sbaglia: gli danno il contesto giusto.
VOCABOLARIO = ("AGIS, Loffre, V Media, Brianza Agency, Brianzasays, FMN15, DacDam, "
               "Grifoni Touch, Latina Telefonia, ITS Rizzoli, Seregno, Vimercate, Monza, "
               "Slack, Gmail, Google Drive, Notion, WordPress, landing page, brief.")


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
            audio, language=self.language, beam_size=5,
            initial_prompt=VOCABOLARIO,
            vad_filter=True,
            # meno aggressivo del predefinito: non taglia le parole a inizio e fine frase
            vad_parameters={"min_silence_duration_ms": 700, "speech_pad_ms": 500,
                            "threshold": 0.35})
        return " ".join(s.text.strip() for s in segments).strip()
