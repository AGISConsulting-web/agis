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
class VoiceConfig:
    enabled: bool = True
    hotkey: str = "ctrl+alt+j"
    whisper_model: str = "small"  # tiny / base / small / medium
    language: str = "it"
    piper_model: str = "voices/it_IT-paola-medium.onnx"
    sample_rate: int = 16000


@dataclass
class NotionConfig:
    """Il cervello condiviso, ora su Google Drive (cartella AGIS).

    Si chiama ancora NotionConfig per compatibilità: dal 10/11/2026 memoria, feedback e
    brief stanno su Drive (Notion aveva finito lo spazio gratuito). Ogni elemento è un
    Google Doc e la cartella in cui si trova è il suo stato.
    """
    enabled: bool = True
    root_folder: str = "17_0WqKTm6hwwUbs0u_yGq-vwvqlEDPze"
    feedback_active: str = "1Q3P8q9Ppdia-ZVU8PPwVjxYp_ewnSae_"
    feedback_integrated: str = "1vcipfomk_H93xlLY7C2nt9GP77xoAfVv"
    brief_folder: str = "13PVQKRQUngTGqjWWtueKe1RHap_Hcxpa"
    requests_new: str = "1Ln5q6zf0GRi6NAMznH_ySEhEd3VyLUC1"
    requests_ready: str = "146fg9I3AYPO-cSC0IH5g5bEMDJaDRC8D"
    pull_every_min: int = 120


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
    known = set(NotionConfig.__dataclass_fields__)
    shared = {**raw.get("notion", {}), **raw.get("cervello", {})}
    notion = NotionConfig(**{k: v for k, v in shared.items() if k in known})
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
