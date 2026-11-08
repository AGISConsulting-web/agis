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
        "WebSearch", "WebFetch", "Read", "Glob", "Grep", "Write", "Edit", "mcp__notion",
    ])
    disallowed_tools: list[str] = field(default_factory=lambda: ["Bash", "PowerShell"])


# Azioni che AGIS non fa mai da solo, su nessun connettore (le regole di divieto vincono
# sempre su quelle di permesso). Se il nome reale di uno strumento non corrisponde, lo
# strumento resta semplicemente non disponibile: il sistema sbaglia sempre dal lato sicuro.
ALWAYS_DENY = [
    "mcp__*trash*", "mcp__*delete*", "mcp__*share_file*", "mcp__*permission*",
    "mcp__*publish*", "mcp__*remove*", "mcp__*cancel*", "mcp__*spam*",
]
SEND_DENY = ["mcp__*send*", "mcp__*reply*", "mcp__*forward*"]
CALENDAR_EDIT_DENY = ["mcp__*create_event*", "mcp__*update_event*", "mcp__*respond_to_event*"]


@dataclass
class ConnectorsConfig:
    """I connettori del tuo account claude.ai (Gmail, Calendar, Drive…).

    Claude Code li vede da solo quando il login è con l'abbonamento: i loro strumenti
    si chiamano mcp__claude_ai_<Nome>__<strumento>. Qui decidi quali AGIS può usare.
    """
    enabled: bool = True
    servers: list[str] = field(default_factory=lambda: [
        "Gmail", "Google_Calendar", "Google_Drive", "Notion",
    ])
    allow_send: bool = False           # inviare/rispondere/inoltrare mail (di base: solo bozze)
    allow_calendar_edit: bool = False  # creare o modificare eventi (di base: solo lettura)

    def rules(self) -> tuple[list[str], list[str]]:
        if not self.enabled:
            return [], ["mcp__claude_ai_*"]
        allow = [f"mcp__claude_ai_{s}__*" for s in self.servers]
        deny = list(ALWAYS_DENY)
        if not self.allow_send:
            deny += SEND_DENY
        if not self.allow_calendar_edit:
            deny += CALENDAR_EDIT_DENY
        return allow, deny


@dataclass
class GoogleConfig:
    """Caselle Gmail di lavoro/scuola collegate direttamente (piano B).

    Ogni account va collegato una volta con `python scripts/collega_google.py <email>`.
    """
    accounts: list[str] = field(default_factory=list)
    client_secret: str = "data/google/client_secret.json"


@dataclass
class NotionConfig:
    """Il cervello condiviso: le stesse pagine che leggono i task automatici."""
    enabled: bool = True
    memoria_page: str = "https://app.notion.com/p/41246a25c90a81348e29ea2a09be3681"
    feedback_ds: str = "collection://5f202c26-9a32-47a3-8e0c-b3e171a40bf6"
    brief_ds: str = "collection://1d368942-cbad-4c2d-90a8-4e50eb016388"
    pull_every_min: int = 120


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
    notion: NotionConfig = field(default_factory=NotionConfig)
    connectors: ConnectorsConfig = field(default_factory=ConnectorsConfig)
    google: GoogleConfig = field(default_factory=GoogleConfig)


def load(path: Path | None = None) -> Config:
    path = path or ROOT / "config.toml"
    raw: dict = {}
    if path.exists():
        raw = tomllib.loads(path.read_text(encoding="utf-8-sig"))  # regge anche i file salvati con BOM
    brain = BrainConfig(**raw.get("brain", {}))
    voice = VoiceConfig(**raw.get("voice", {}))
    notion = NotionConfig(**raw.get("notion", {}))
    connectors = ConnectorsConfig(**raw.get("connectors", {}))
    google = GoogleConfig(**raw.get("google", {}))
    if not Path(google.client_secret).is_absolute():
        google.client_secret = str(ROOT / google.client_secret)
    general = raw.get("general", {})
    workspace = ROOT / general.get("workspace", "workspace")
    data_dir = ROOT / general.get("data_dir", "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    if not Path(voice.piper_model).is_absolute():
        voice.piper_model = str(ROOT / voice.piper_model)
    return Config(brain=brain, voice=voice, workspace=workspace, data_dir=data_dir,
                  notion=notion, connectors=connectors, google=google)
