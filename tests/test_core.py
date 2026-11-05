import json
import subprocess
from pathlib import Path

import pytest

from agis.brain import Brain, BrainError, MODE_VOICE
from agis.config import BrainConfig
from agis.memory import Memory
from agis.voice.tts import clean_for_speech


def fake_runner(stdout, returncode=0, stderr="", calls=None):
    def run(cmd, **kw):
        if calls is not None:
            calls.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)
    return run


def test_brain_parses_and_keeps_session(tmp_path):
    calls = []
    out = json.dumps({"type": "result", "result": "Ciao Loffre", "session_id": "s1", "is_error": False})
    b = Brain(BrainConfig(), tmp_path, runner=fake_runner(out, calls=calls))
    r = b.ask("ciao", voice=True)
    assert r.text == "Ciao Loffre" and b.session_id == "s1" and not r.is_error
    cmd, kw = calls[0]
    assert kw["input"] == "ciao"            # il messaggio passa da stdin
    assert "--resume" not in cmd
    assert MODE_VOICE in cmd
    b.ask("e poi?")
    assert calls[1][0][calls[1][0].index("--resume") + 1] == "s1"


def test_brain_subscription_drops_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    calls = []
    b = Brain(BrainConfig(auth="abbonamento"), tmp_path,
              runner=fake_runner(json.dumps({"result": "ok"}), calls=calls))
    b.ask("x")
    assert "ANTHROPIC_API_KEY" not in calls[0][1]["env"]


def test_brain_api_key_mode(tmp_path):
    calls = []
    b = Brain(BrainConfig(auth="api_key", api_key="sk-abc"), tmp_path,
              runner=fake_runner(json.dumps({"result": "ok"}), calls=calls))
    b.ask("x")
    assert calls[0][1]["env"]["ANTHROPIC_API_KEY"] == "sk-abc"
    with pytest.raises(BrainError):
        Brain(BrainConfig(auth="api_key"), tmp_path).ask("x")


def test_brain_bad_output(tmp_path):
    b = Brain(BrainConfig(), tmp_path, runner=fake_runner("non json", 1, "login richiesto"))
    with pytest.raises(BrainError, match="login richiesto"):
        b.ask("x")


def test_memory_feedback_export(tmp_path):
    md = tmp_path / "memoria" / "feedback.md"
    m = Memory(tmp_path / "db.sqlite", md)
    assert "Nessun feedback" in md.read_text(encoding="utf-8")
    mid = m.add_message("agis", "Risposta troppo lunga e piena di dettagli")
    m.add_feedback(mid, -1, "più corto, massimo 3 frasi")
    text = md.read_text(encoding="utf-8")
    assert "👎 più corto, massimo 3 frasi" in text and "troppo lunga" in text
    with pytest.raises(ValueError):
        m.add_feedback(mid, 0)


def test_clean_for_speech():
    s = "**Ciao** ecco il [link](https://x.it) 🎯 e https://a.b/c"
    assert clean_for_speech(s) == "Ciao ecco il link e"
