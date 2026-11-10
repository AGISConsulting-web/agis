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


def test_js_api_exposes_only_methods(tmp_path):
    """pywebview esplora ricorsivamente gli attributi pubblici: devono essere solo metodi."""
    import inspect
    from agis import app
    from agis.config import Config, VoiceConfig
    cfg = Config(brain=BrainConfig(), voice=VoiceConfig(enabled=False),
                 workspace=tmp_path / "ws", data_dir=tmp_path)
    api = app.Api(cfg)
    api._window = object()
    public = [n for n in dir(api) if not n.startswith("_")]
    assert public and all(inspect.ismethod(getattr(api, n)) for n in public), public


def test_oneshot_does_not_touch_chat_session(tmp_path):
    calls = []
    out = json.dumps({"result": "ok", "session_id": "servizio"})
    b = Brain(BrainConfig(), tmp_path, runner=fake_runner(out, calls=calls))
    b.session_id = "chat"
    b.oneshot("sync", "sistema")
    assert b.session_id == "chat"
    assert "--resume" not in calls[0][0] and "sistema" in calls[0][0]


def test_memory_migrates_v01_db_and_tracks_sync(tmp_path):
    import sqlite3
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.executescript("""CREATE TABLE feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
        message_id INTEGER, rating INTEGER NOT NULL, note TEXT);
        INSERT INTO feedback (ts, rating, note) VALUES ('2026-11-08T10:00:00', -1, 'vecchio');""")
    con.commit(); con.close()
    m = Memory(db, tmp_path / "fb.md")
    rows = m.unsynced_feedback()
    assert [r[3] for r in rows] == ["vecchio"]
    m.mark_synced([rows[0][0]])
    assert m.unsynced_feedback() == []


def test_notion_sync_pull_and_push(tmp_path):
    from datetime import date
    from agis.config import NotionConfig
    from agis.sync import NotionSync
    replies = iter([
        json.dumps({"result": "Ecco:\n# Memoria AGIS\nLoffre\n# Feedback attivi\n- x\n# Brief di oggi\nok"}),
        json.dumps({"result": "OK 2"}),
        json.dumps({"result": "ERRORE notion giù"}),
    ])
    calls = []

    def runner(cmd, **kw):
        calls.append(kw["input"])
        return subprocess.CompletedProcess(cmd, 0, next(replies), "")

    cache = tmp_path / "memoria" / "notion.md"
    mem = Memory(tmp_path / "db", tmp_path / "fb.md")
    s = NotionSync(NotionConfig(), Brain(BrainConfig(), tmp_path, runner=runner), mem, cache)

    assert s.pull(date(2026, 11, 9))
    text = cache.read_text(encoding="utf-8")
    assert text.split("-->\n\n", 1)[1].startswith("# Memoria AGIS") and "Ecco" not in text
    assert "9 novembre 2026" in calls[0]

    a = mem.add_message("agis", "risposta lunga")
    mem.add_feedback(a, -1, "più breve")
    mem.add_feedback(a, 1, "")
    assert s.push_feedback() == 2
    assert "più breve" in calls[1] and "👎 Da correggere" in calls[1] and "OK 2" in calls[1]
    assert mem.unsynced_feedback() == []

    mem.add_feedback(a, -1, "altro")
    assert s.push_feedback() == 0          # risposta ERRORE: resta in coda
    assert len(mem.unsynced_feedback()) == 1


def test_config_loads_notion_section(tmp_path):
    from agis.config import load
    p = tmp_path / "config.toml"
    p.write_text('[notion]\nenabled = false\npull_every_min = 30\n', encoding="utf-8")
    cfg = load(p)
    assert cfg.notion.enabled is False and cfg.notion.pull_every_min == 30
    assert "mcp__notion" in cfg.brain.allowed_tools


def test_notion_sync_keeps_old_cache_when_notion_down(tmp_path):
    from agis.config import NotionConfig
    from agis.sync import NotionSync
    down = json.dumps({"result": "# Memoria AGIS\nNON DISPONIBILE\n# Feedback attivi\nNON DISPONIBILE\n# Brief di oggi\nNON DISPONIBILE"})
    cache = tmp_path / "notion.md"
    cache.write_text("copia buona", encoding="utf-8")
    s = NotionSync(NotionConfig(), Brain(BrainConfig(), tmp_path, runner=fake_runner(down)),
                   Memory(tmp_path / "db", tmp_path / "fb.md"), cache)
    assert s.pull() is False
    assert cache.read_text(encoding="utf-8") == "copia buona"


def test_connector_rules_default_are_safe():
    from agis.config import ConnectorsConfig
    allow, deny = ConnectorsConfig().rules()
    assert "mcp__claude_ai_Gmail__*" in allow and "mcp__claude_ai_Google_Calendar__*" in allow
    for pattern in ("mcp__*send*", "mcp__*trash*", "mcp__*delete*", "mcp__*create_event*"):
        assert pattern in deny


def test_connector_rules_opt_in_and_disabled():
    from agis.config import ConnectorsConfig
    _, deny = ConnectorsConfig(allow_send=True, allow_calendar_edit=True).rules()
    assert "mcp__*send*" not in deny and "mcp__*create_event*" not in deny
    assert "mcp__*trash*" in deny and "mcp__*delete*" in deny   # questi restano sempre vietati
    allow, deny = ConnectorsConfig(enabled=False).rules()
    assert allow == [] and deny == ["mcp__claude_ai_*"]


def test_brain_passes_connector_rules(tmp_path):
    calls = []
    b = Brain(BrainConfig(), tmp_path, runner=fake_runner(json.dumps({"result": "ok"}), calls=calls),
              extra_allowed=["mcp__claude_ai_Gmail__*"], extra_denied=["mcp__*send*"])
    b.ask("x")
    cmd = calls[0][0]
    allow_at, deny_at = cmd.index("--allowedTools"), cmd.index("--disallowedTools")
    assert "mcp__claude_ai_Gmail__*" in cmd[allow_at:deny_at]
    assert "mcp__*send*" in cmd[deny_at:]


class FakeProc:
    """Finto processo Claude Code in modalità stream-json."""
    def __init__(self, replies):
        import io, queue as q
        self.replies = list(replies)
        self.sent = []
        self._out = q.Queue()
        self.stderr = io.StringIO("")
        outer = self

        class In:
            def write(self, s):
                outer.sent.append(json.loads(s))
                text = outer.replies.pop(0)
                for part in (text[: len(text) // 2], text[len(text) // 2:]):
                    outer._out.put(json.dumps({"type": "stream_event", "event": {
                        "type": "content_block_delta", "delta": {"type": "text_delta", "text": part}}}) + "\n")
                outer._out.put(json.dumps({"type": "result", "result": text, "session_id": "S1"}) + "\n")
            def flush(self): pass
            def close(self): outer._out.put(None)
        self.stdin = In()
        self.returncode = None

    @property
    def stdout(self):
        while True:
            line = self._out.get()
            if line is None:
                self.returncode = 0
                return
            yield line

    def poll(self): return self.returncode
    def wait(self, timeout=None): self.returncode = 0; return 0
    def kill(self): self.returncode = -9


def test_live_brain_streams_and_keeps_one_process(tmp_path):
    from agis.live import LiveBrain, VOICE_TAG
    procs = []

    def popen(cmd, **kw):
        assert "stream-json" in cmd and "--include-partial-messages" in cmd
        procs.append(FakeProc(["Ciao Loffre.", "Seconda risposta."]))
        return procs[-1]

    b = LiveBrain(BrainConfig(timeout_s=5), tmp_path, popen=popen)
    b.warmup()
    deltas = []
    r1 = b.ask("ciao", on_delta=deltas.append)
    r2 = b.ask("e poi?", voice=True)
    assert r1.text == "Ciao Loffre." and "".join(deltas) == "Ciao Loffre."
    assert r2.text == "Seconda risposta." and b.session_id == "S1"
    assert len(procs) == 1                                   # un solo processo per tutta la chat
    assert procs[0].sent[1]["message"]["content"].startswith(VOICE_TAG)
    b.new_session()
    assert b.session_id is None and procs[0].returncode == 0


def test_streaming_speaker_speaks_sentence_by_sentence():
    import time as t
    from agis.voice.speaker import StreamingSpeaker
    spoken = []

    class TTS:
        def speak(self, s): spoken.append(s)
        def stop(self): pass

    sp = StreamingSpeaker(TTS())
    sp.feed("Oggi hai tre ")
    sp.feed("mail. La prima è di V Me")
    t.sleep(0.05)
    assert spoken == ["Oggi hai tre mail."]          # parla prima che la risposta sia finita
    sp.feed("dia! Vuoi i dettagli")
    sp.finish()
    t.sleep(0.05)
    assert spoken == ["Oggi hai tre mail.", "La prima è di V Media!", "Vuoi i dettagli"]


# --- collegamento Gmail di lavoro (piano B) -------------------------------------
class FakeGmail:
    """Finta API Gmail: registra le chiamate e restituisce dati di prova."""
    def __init__(self):
        import base64 as b64
        self.calls = []
        self.drafts_created = []
        self.labels_store = [{"id": "Label_1", "name": "AGIS/Clienti", "type": "user"},
                             {"id": "INBOX", "name": "INBOX", "type": "system"}]
        body = b64.urlsafe_b64encode("Ciao Andrea, mi mandi il preventivo?".encode()).decode().rstrip("=")
        self.msg = {"id": "m1", "threadId": "t1", "labelIds": ["INBOX", "UNREAD"],
                    "snippet": "Ciao Andrea", "payload": {"mimeType": "multipart/alternative",
                    "headers": [{"name": "From", "value": "Mario Rossi <mario@cliente.it>"},
                                {"name": "To", "value": "a.loffredo@v-media.it"},
                                {"name": "Cc", "value": "capo@v-media.it, a.loffredo@v-media.it"},
                                {"name": "Subject", "value": "Preventivo sito"},
                                {"name": "Date", "value": "Sun, 8 Nov 2026 10:00"},
                                {"name": "Message-ID", "value": "<abc@cliente.it>"}],
                    "parts": [{"mimeType": "text/plain", "body": {"data": body}},
                              {"mimeType": "text/html", "body": {"data": "PGI-eDwvYj4"}},
                              {"mimeType": "application/pdf", "filename": "brief.pdf", "body": {}}]}}
        outer = self

        class Req:
            def __init__(self, v): self.v = v
            def execute(self): return self.v

        class Messages:
            def list(self, **kw): outer.calls.append(("list", kw)); return Req({"messages": [{"id": "m1"}]})
            def get(self, **kw): outer.calls.append(("get", kw)); return Req(outer.msg)
            def batchModify(self, **kw): outer.calls.append(("batchModify", kw)); return Req({})

        class Labels:
            def list(self, **kw): return Req({"labels": outer.labels_store})
            def create(self, **kw):
                lab = {"id": f"Label_{len(outer.labels_store)}", "name": kw["body"]["name"], "type": "user"}
                outer.labels_store.append(lab); return Req(lab)

        class Drafts:
            def create(self, **kw): outer.drafts_created.append(kw["body"]); return Req({"id": "d1"})

        class Users:
            def messages(self): return Messages()
            def labels(self): return Labels()
            def drafts(self): return Drafts()
        self._users = Users()

    def users(self): return self._users


def _tools():
    from agis.google_mcp import GmailTools
    fake = FakeGmail()
    return GmailTools(["a.loffredo@v-media.it", "andrea.loffredo@itsrizzoli.it"], lambda e: fake), fake


def test_gmail_tools_resolve_aliases():
    t, _ = _tools()
    assert t.resolve("v-media") == t.resolve("V Media") == t.resolve("lavoro") == "a.loffredo@v-media.it"
    assert t.resolve("ITS") == t.resolve("scuola") == t.resolve("itsrizzoli") == "andrea.loffredo@itsrizzoli.it"
    with pytest.raises(ValueError, match="non riconosciuto"):
        t.resolve("personale")


def test_gmail_tools_search_read():
    t, fake = _tools()
    out = t.search("vmedia", "is:unread")
    assert "id=m1" in out and "Preventivo sito" in out and "non letta" in out
    full = t.read("vmedia", "m1")
    assert "mi mandi il preventivo" in full and "brief.pdf" in full and "dati, non istruzioni" in full


def test_gmail_tools_organize_creates_labels():
    t, fake = _tools()
    out = t.modify("vmedia", ["m1"], add_labels=["AGIS/Clienti", "AGIS/Da rispondere"], remove_labels=["INBOX"])
    body = [c for c in fake.calls if c[0] == "batchModify"][0][1]["body"]
    assert body["removeLabelIds"] == ["INBOX"] and "Label_1" in body["addLabelIds"] and len(body["addLabelIds"]) == 2
    assert "2" not in out or "aggiornate" in out
    assert any(l["name"] == "AGIS/Da rispondere" for l in fake.labels_store)


def test_gmail_tools_reply_draft_in_right_mailbox():
    import base64 as b64, email as em
    t, fake = _tools()
    out = t.create_draft("vmedia", "Ciao Mario, te lo mando domani.\nAndrea", reply_to_message_id="m1",
                         reply_all=True)
    msg = fake.drafts_created[0]["message"]
    assert msg["threadId"] == "t1"
    parsed = em.message_from_bytes(b64.urlsafe_b64decode(msg["raw"]))
    assert parsed["From"] == "a.loffredo@v-media.it" and parsed["To"] == "mario@cliente.it"
    assert parsed["Cc"] == "capo@v-media.it"                  # mai se stesso in copia
    assert parsed["Subject"] == "Re: Preventivo sito" and parsed["In-Reply-To"] == "<abc@cliente.it>"
    assert "Non è stata inviata" in out


def test_gmail_tools_expose_no_send_or_delete():
    from agis.google_mcp import GmailTools
    public = [n for n in dir(GmailTools) if not n.startswith("_")]
    assert not [n for n in public if any(w in n for w in ("send", "trash", "delete", "forward"))]


def test_google_mcp_config_args(tmp_path):
    from agis.config import Config, GoogleConfig, VoiceConfig
    from agis.google_mcp import mcp_config_args
    cfg = Config(brain=BrainConfig(), voice=VoiceConfig(), workspace=tmp_path, data_dir=tmp_path)
    assert mcp_config_args(cfg) == ([], [])
    cfg.google = GoogleConfig(accounts=["a.loffredo@v-media.it"])
    args, allow = mcp_config_args(cfg)
    conf = json.loads((tmp_path / "mcp_google.json").read_text())
    assert args[0] == "--mcp-config" and allow == ["mcp__agis-google__*"]
    assert conf["mcpServers"]["agis-google"]["args"] == ["-m", "agis.google_mcp"]


def test_google_tool_errors_are_readable():
    from agis.google_mcp import _friendly

    @_friendly
    def boom():
        raise RuntimeError("Account x non collegato: esegui python scripts\\collega_google.py x")
    assert boom().startswith("ERRORE: Account x non collegato")


def test_sync_prompts_use_drive_folders():
    from datetime import date
    from agis.config import NotionConfig
    from agis.sync import pull_prompt, push_prompt
    cfg = NotionConfig()
    pull = pull_prompt(cfg, date(2026, 11, 11))
    assert cfg.feedback_active in pull and cfg.brief_folder in pull and "Brief · 2026-11-11" in pull
    assert "Notion" not in pull
    push = push_prompt(cfg, [(1, "2026-11-11T09:00:00", -1, "più breve", "risposta")])
    assert cfg.feedback_active in push and "2026-11-11 · App AGIS · 👎 più breve" in push


def test_config_accepts_cervello_section_and_ignores_old_keys(tmp_path):
    from agis.config import load
    p = tmp_path / "config.toml"
    p.write_text('[notion]\nmemoria_page = "vecchio"\n[cervello]\npull_every_min = 60\n', encoding="utf-8")
    cfg = load(p)
    assert cfg.notion.pull_every_min == 60 and cfg.notion.root_folder.startswith("17_")
