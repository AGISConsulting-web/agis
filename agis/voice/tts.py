"""Sintesi vocale locale e gratuita.

Prima scelta: Piper (voce neurale italiana, molto più naturale).
Ripiego: la voce di sistema di Windows (pyttsx3 / SAPI).
"""
from __future__ import annotations

import io
import re
import wave
from pathlib import Path


def clean_for_speech(text: str) -> str:
    """Toglie markdown, link ed emoji che non vanno letti ad alta voce."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#>`|]", "", text)
    text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿]", "", text)
    return re.sub(r"\s+", " ", text).strip()


class TextToSpeech:
    def __init__(self, piper_model: str):
        self._piper = None
        self._sapi = None
        if Path(piper_model).exists():
            try:
                from piper import PiperVoice
                self._piper = PiperVoice.load(piper_model)
            except Exception as e:  # noqa: BLE001
                print(f"[AGIS] Piper non disponibile ({e}), uso la voce di Windows")
        if self._piper is None:
            import pyttsx3
            self._sapi = pyttsx3.init()
            for v in self._sapi.getProperty("voices"):
                if "ital" in (v.name or "").lower() or "it" in str(v.languages).lower():
                    self._sapi.setProperty("voice", v.id)
                    break

    @property
    def engine(self) -> str:
        return "piper" if self._piper else "windows"

    def speak(self, text: str) -> None:
        text = clean_for_speech(text)
        if not text:
            return
        if self._piper:
            self._speak_piper(text)
        else:
            self._sapi.say(text)
            self._sapi.runAndWait()

    def _speak_piper(self, text: str) -> None:
        import numpy as np
        import sounddevice as sd
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            # piper-tts >= 1.3 usa synthesize_wav; le versioni precedenti synthesize
            if hasattr(self._piper, "synthesize_wav"):
                self._piper.synthesize_wav(text, wav)
            else:
                self._piper.synthesize(text, wav)
        buf.seek(0)
        with wave.open(buf, "rb") as wav:
            rate = wav.getframerate()
            audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
        sd.play(audio, rate)
        sd.wait()

    def stop(self) -> None:
        if self._piper:
            import sounddevice as sd
            sd.stop()
        elif self._sapi:
            self._sapi.stop()
