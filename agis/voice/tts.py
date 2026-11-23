"""Sintesi vocale gratuita.

1ª scelta: voci neurali Microsoft Edge (edge-tts): gratis, molto naturali, serve internet.
2ª scelta: Piper (voce neurale italiana locale), usata da sola se la rete non c'è.
Ultimo ripiego: la voce di sistema di Windows (pyttsx3 / SAPI).

La sintesi (`synth`) è separata dalla riproduzione (`play`), così mentre AGIS dice una
frase la successiva è già pronta: niente pause tra una frase e l'altra.
"""
from __future__ import annotations

import io
import re
import wave
from pathlib import Path


def clean_for_speech(text: str) -> str:
    """Toglie markdown, link, percorsi ed emoji che non vanno letti ad alta voce."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[A-Za-z]:\\\S+", "", text)            # percorsi Windows
    text = re.sub(r"(?<!\w)(?:~|\.{0,2})/\S+/\S*", "", text)  # percorsi tipo /a/b
    text = re.sub(r"-{2,}", " ", text)
    text = re.sub(r"[*_#>`|]", "", text)
    text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", text)
    return re.sub(r"\s+", " ", text).strip()


class TextToSpeech:
    def __init__(self, piper_model: str, engine: str = "edge",
                 edge_voice: str = "it-IT-IsabellaNeural", edge_rate: str = "+8%"):
        self._piper = None
        self._sapi = None
        self._edge = None
        self._edge_voice, self._edge_rate = edge_voice, edge_rate
        if engine == "edge":
            try:
                import edge_tts  # noqa: F401
                import miniaudio  # noqa: F401
                self._edge = True
            except Exception as e:  # noqa: BLE001
                print(f"[AGIS] Voce Edge non disponibile ({e}), uso Piper")
        if engine in ("edge", "piper") and Path(piper_model).exists():
            try:
                from piper import PiperVoice
                self._piper = PiperVoice.load(piper_model)
            except Exception as e:  # noqa: BLE001
                print(f"[AGIS] Piper non disponibile ({e})")
        if not self._edge and not self._piper:
            import pyttsx3
            self._sapi = pyttsx3.init()
            for v in self._sapi.getProperty("voices"):
                if "ital" in (v.name or "").lower() or "it" in str(v.languages).lower():
                    self._sapi.setProperty("voice", v.id)
                    break

    @property
    def engine(self) -> str:
        return "edge" if self._edge else "piper" if self._piper else "windows"

    # --- sintesi --------------------------------------------------------------------
    def synth(self, text: str):
        """Restituisce (campioni int16, frequenza) oppure None (per SAPI parla `play`)."""
        text = clean_for_speech(text)
        if not text:
            return None
        if self._edge:
            try:
                return self._synth_edge(text)
            except Exception as e:  # noqa: BLE001
                print(f"[AGIS] Voce Edge non raggiungibile ({e}), uso la voce locale")
        if self._piper:
            return self._synth_piper(text)
        return ("sapi", text)

    def _synth_edge(self, text: str):
        import asyncio

        import edge_tts
        import miniaudio
        import numpy as np

        async def run() -> bytes:
            out = bytearray()
            comm = edge_tts.Communicate(text, self._edge_voice, rate=self._edge_rate)
            async for chunk in comm.stream():
                if chunk.get("type") == "audio":
                    out += chunk["data"]
            return bytes(out)

        mp3 = asyncio.run(run())
        if not mp3:
            raise RuntimeError("nessun audio ricevuto")
        dec = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16,
                               nchannels=1, sample_rate=24000)
        return np.frombuffer(dec.samples, dtype=np.int16), 24000

    def _synth_piper(self, text: str):
        import numpy as np
        buf = io.BytesIO()
        rate = int(getattr(getattr(self._piper, "config", None), "sample_rate", 22050))
        with wave.open(buf, "wb") as wav:
            # formato impostato prima: senza, una frase che non produce audio faceva
            # fallire la chiusura del file con "# channels not specified"
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            if hasattr(self._piper, "synthesize_wav"):  # piper-tts >= 1.3
                self._piper.synthesize_wav(text, wav, set_wav_format=False)
            else:
                self._piper.synthesize(text, wav)
        buf.seek(0)
        with wave.open(buf, "rb") as wav:
            rate = wav.getframerate()
            audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
        return (audio, rate) if audio.size else None

    # --- riproduzione ---------------------------------------------------------------
    def play(self, item) -> None:
        if item is None:
            return
        if item[0] == "sapi":
            self._sapi.say(item[1])
            self._sapi.runAndWait()
            return
        import sounddevice as sd
        audio, rate = item
        sd.play(audio, rate)
        sd.wait()

    def speak(self, text: str) -> None:
        self.play(self.synth(text))

    def stop(self) -> None:
        if self._sapi:
            self._sapi.stop()
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:  # noqa: BLE001
            pass
