"""Il cervello di AGIS: Claude Code eseguito in modalità non interattiva.

Con auth = "abbonamento" usa il login Claude Code dell'utente (piano Pro),
quindi nessun costo API. Con auth = "api_key" usa una chiave Anthropic:
è la modalità da usare quando AGIS verrà installato per altri (aziende, clienti).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import BrainConfig


@dataclass
class Reply:
    text: str
    session_id: str | None
    is_error: bool = False


class BrainError(RuntimeError):
    pass


# Testi semplici, senza virgolette né simboli speciali: passano intatti anche
# attraverso il lanciatore claude.cmd di Windows.
MODE_VOICE = (
    "Modalita voce: la risposta verra letta ad alta voce. Usa frasi brevi e naturali, "
    "niente elenchi, tabelle, markdown, emoji o link. Al massimo 4 o 5 frasi, "
    "poi chiedi se vuole i dettagli."
)
MODE_TEXT = "Modalita chat: la risposta viene mostrata in una finestra di chat, puoi usare markdown leggero."


class Brain:
    def __init__(self, cfg: BrainConfig, workspace: Path,
                 runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                 extra_allowed: list[str] | None = None,
                 extra_denied: list[str] | None = None,
                 extra_args: list[str] | None = None):
        self.cfg = cfg
        self.workspace = workspace
        self.runner = runner
        self.session_id: str | None = None
        # Regole dei connettori claude.ai (Gmail, Calendar, Drive…), vedi ConnectorsConfig.
        self.extra_allowed = list(extra_allowed or [])
        self.extra_denied = list(extra_denied or [])
        # Argomenti in più per Claude Code, es. --mcp-config del collegamento Gmail di lavoro.
        self.extra_args = list(extra_args or [])

    def new_session(self) -> None:
        self.session_id = None

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.cfg.auth == "api_key":
            if not self.cfg.api_key:
                raise BrainError("auth = 'api_key' ma api_key è vuota in config.toml")
            env["ANTHROPIC_API_KEY"] = self.cfg.api_key
        else:
            # Forza l'uso dell'abbonamento: una chiave nell'ambiente avrebbe la precedenza.
            env.pop("ANTHROPIC_API_KEY", None)
        return env

    def build_command(self, voice: bool, resume: bool = True,
                      system: str | None = None) -> list[str]:
        exe = shutil.which(self.cfg.claude_cmd) or self.cfg.claude_cmd
        cmd = [exe, "-p", "--output-format", "json"]
        if resume and self.session_id:
            cmd += ["--resume", self.session_id]
        if self.cfg.model:
            cmd += ["--model", self.cfg.model]
        cmd += self.extra_args
        allowed = [*self.cfg.allowed_tools, *self.extra_allowed]
        denied = [*self.cfg.disallowed_tools, *self.extra_denied]
        if allowed:
            cmd += ["--allowedTools", *allowed]
        if denied:
            cmd += ["--disallowedTools", *denied]
        cmd += ["--append-system-prompt", system or (MODE_VOICE if voice else MODE_TEXT)]
        return cmd

    def ask(self, prompt: str, voice: bool = False) -> Reply:
        """Messaggio della conversazione: continua la sessione in corso."""
        return self._run(self.build_command(voice), prompt, keep_session=True)

    def oneshot(self, prompt: str, system: str) -> Reply:
        """Lavoro di servizio (es. sincronizzare Notion): sessione a parte, non tocca la chat."""
        return self._run(self.build_command(False, resume=False, system=system),
                         prompt, keep_session=False)

    def _run(self, cmd: list[str], prompt: str, keep_session: bool) -> Reply:
        # Il messaggio passa da stdin: niente problemi di virgolette o caratteri
        # speciali con il lanciatore claude.cmd di Windows.
        try:
            proc = self.runner(
                cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                cwd=str(self.workspace), env=self._env(), timeout=self.cfg.timeout_s,
            )
        except FileNotFoundError as e:
            raise BrainError(
                "Claude Code non trovato. Installalo e fai il login, oppure imposta "
                "claude_cmd in config.toml.") from e
        except subprocess.TimeoutExpired as e:
            raise BrainError("Claude Code non ha risposto in tempo.") from e
        return self.parse(proc, keep_session=keep_session)

    def parse(self, proc: subprocess.CompletedProcess, keep_session: bool = True) -> Reply:
        out = (proc.stdout or "").strip()
        try:
            data = json.loads(out.splitlines()[-1] if out else "")
        except (json.JSONDecodeError, IndexError):
            err = (proc.stderr or out or "nessun output").strip()
            raise BrainError(f"Risposta non valida da Claude Code: {err[:500]}")
        if isinstance(data, list):  # alcune versioni restituiscono la lista dei messaggi
            data = next((d for d in reversed(data) if d.get("type") == "result"), {})
        sid = data.get("session_id")
        if sid and keep_session:
            self.session_id = sid
        text = data.get("result") or ""
        is_error = bool(data.get("is_error")) or proc.returncode != 0
        if is_error and not text:
            text = (proc.stderr or "Errore sconosciuto").strip()
        return Reply(text=text, session_id=sid, is_error=is_error)
