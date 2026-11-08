"""Caricamento della configurazione di AGIS (config.toml)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class BrainConfig:
    # "abbonamento" = usa il login Claude Code (piano Pro/Max), nessun costo extra.
    # "api_key"     = usa una chiave API Anthropic (serve per installazioni in azienda).
    auth: str = "abbonamento"
    api_key: str = ""
    claude_cmd: str = "claude"
    model: str = ""  # vuoto = modello predefinito di Claude Code
    timeout_s: int = 300
    allowed_tools: list[str] = field(default_factory=lambda: [
        "WebSearch", "WebFetch", "Read", "Glob", "Grep", "Write", "Edit",
    ])
    disallowed_tools: list[str] = field(default_factory=lambda: ["Bash", "PowerShell"])


@dataclass
class VoiceConfig:
    enabled: bool = True
    hotkey: str = "ctrl+alt+j"
    whisper_model: str = "small"  # tiny / base / small / medium
    language: str = "it"
    piper_model: str = "voices/it_IT-paola-medium.onnx"
    sample_rate: int = 16000


@dataclass
class Config:
    brain: BrainConfig
    voice: VoiceConfig
    workspace: Path
    data_dir: Path


def load(path: Path | None = None) -> Config:
    path = path or ROOT / "config.toml"
    raw: dict = {}
    if path.exists():
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    brain = BrainConfig(**raw.get("brain", {}))
    voice = VoiceConfig(**raw.get("voice", {}))
    general = raw.get("general", {})
    workspace = ROOT / general.get("workspace", "workspace")
    data_dir = ROOT / general.get("data_dir", "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    if not Path(voice.piper_model).is_absolute():
        voice.piper_model = str(ROOT / voice.piper_model)
    return Config(brain=brain, voice=voice, workspace=workspace, data_dir=data_dir)
