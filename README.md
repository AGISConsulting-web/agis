# AGIS

Assistente personale autonomo di Andrea "Loffre" Loffredo, evoluzione di Jarvis.
Ci parli con la voce o in chat, ti risponde con una voce sua, usa i tuoi strumenti
e impara dai tuoi feedback.

**Costo:** zero oltre al piano Claude Pro. Il cervello è **Claude Code** collegato al tuo
account; voce e trascrizione girano gratis sul tuo PC.

## Come è fatto

| Pezzo | Cosa usa | Dove gira |
|---|---|---|
| Cervello | Claude Code (`claude -p`) con il tuo login Pro | PC + Anthropic |
| Orecchie | faster-whisper (italiano) | PC, gratis |
| Voce | Piper, voce italiana "Paola" (ripiego: voce di Windows) | PC, gratis |
| Memoria | SQLite + `workspace/memoria/feedback.md` | PC |
| Strumenti | server MCP: Notion (subito), Google (prossimo passo) | — |
| App | finestra desktop (pywebview) + scorciatoia globale | PC |

La cartella `workspace/` è il "cervello" vero e proprio: `CLAUDE.md` (personalità e regole),
`.claude/skills/` (le cose che sa fare, che AGIS può ampliare da solo con la skill
`crea-skill`), `memoria/` (feedback e note).

## Installazione su Windows

Serve: **Python 3.11 o più recente** (python.org, spunta "Add python.exe to PATH") e
**Claude Code** a riga di comando (non basta l'app desktop di Claude). Se in PowerShell
`claude --version` non funziona, installalo con `irm https://claude.ai/install.ps1 | iex`,
riapri PowerShell e fai il login con il tuo account Pro.

Apri PowerShell nella cartella dove vuoi il progetto:

```powershell
git clone https://github.com/AGISConsulting-web/agis.git
cd agis
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts\scarica_voce.py
copy config.example.toml config.toml
```

### Collegare Notion (una volta sola)

```powershell
cd workspace
claude
```

Dentro Claude Code scrivi `/mcp`, scegli **notion**, autentica nel browser, poi esci con `/exit`.

### Avviare AGIS

```powershell
cd ..
python -m agis
```

- Scrivi nella chat, oppure premi **Ctrl+Alt+J**, parla, e premi di nuovo per finire.
- 👍 / 👎 sotto ogni risposta: il 👎 ti chiede cosa cambiare e AGIS lo applica da subito.
- **＋ Nuova** riparte da zero con la conversazione.

> La prima volta che usi la voce, Whisper scarica il modello (~500 MB per "small").
> Se è lento sul tuo PC, metti `whisper_model = "base"` in `config.toml`.

## Sicurezza

- AGIS legge, cerca e prepara bozze. **Non invia, non pubblica, non cancella e non paga**
  senza che tu glielo confermi in chat (regola in `workspace/CLAUDE.md`).
- Il terminale (`Bash` e `PowerShell`) è disattivato per il cervello.
- `config.toml`, i dati e la memoria personale non vanno mai su GitHub (`.gitignore`).

## Uso in azienda

Il login Pro vale solo per il tuo uso personale. Per installare AGIS per un cliente,
in `config.toml` metti `auth = "api_key"` e la chiave API Anthropic **del cliente**.

## Roadmap

- [x] v0.1 — chat + voce locale, memoria e feedback, Notion, skill che creano skill
- [ ] Google (Gmail, Calendar, Drive) come server MCP locale
- [ ] Icona nell'area di notifica e avvio automatico con Windows
- [ ] Brief del mattino letto ad alta voce alle 6:00
- [ ] Revisione settimanale automatica: AGIS rilegge i feedback e riscrive le proprie istruzioni
- [ ] Parola di attivazione ("Ehi AGIS") senza tasti
- [ ] Installer `.exe`

## Sviluppo

```powershell
pip install pytest
python -m pytest
```
