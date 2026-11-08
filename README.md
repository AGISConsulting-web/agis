# AGIS

Assistente personale autonomo di Andrea "Loffre" Loffredo, evoluzione di Jarvis.
Ci parli con la voce o in chat, ti risponde con una voce sua, usa i tuoi strumenti
e impara dai tuoi feedback.

**Costo:** zero oltre al piano Claude Pro. Il cervello è **Claude Code** collegato al tuo
account; voce e trascrizione girano gratis sul tuo PC.

## Come è fatto

| Pezzo | Cosa usa | Dove gira |
|---|---|---|
| Cervello | Claude Code con il tuo login Pro, **sempre acceso** durante la chat (risposte in streaming) | PC + Anthropic |
| Orecchie | faster-whisper (italiano) | PC, gratis |
| Voce | Piper, voce italiana "Paola" (ripiego: voce di Windows) | PC, gratis |
| Memoria | **Cervello condiviso su Notion** + copia locale in `workspace/memoria/` | Notion + PC |
| Strumenti | i tuoi connettori claude.ai: Gmail, Google Calendar, Google Drive, Notion | — |
| App | finestra desktop (pywebview) + scorciatoia globale | PC |

La cartella `workspace/` è il "cervello" vero e proprio: `CLAUDE.md` (personalità e regole),
`.claude/skills/` (le cose che sa fare, che AGIS può ampliare da solo con la skill
`crea-skill`), `memoria/` (copia locale di memoria, feedback e brief).

## Velocità

- Il cervello resta acceso per tutta la conversazione: i connettori si collegano una volta sola
  e il testo compare mentre AGIS lo scrive. A voce legge ogni frase appena è pronta.
- Per risposte ancora più rapide in `config.toml` metti `model = "sonnet"` (più veloce di Opus
  e consuma meno del piano Pro).
- Spegni i connettori che AGIS non usa: `cd workspace`, `claude`, `/mcp`, e disattiva per
  questo progetto Canva, Figma, Higgsfield, Slack, Claude Docs. Meno strumenti = avvio più
  veloce e risposte più leggere.

## Gmail, calendari e Drive

AGIS usa **gli stessi connettori che hai su claude.ai** (Impostazioni → Connettori): Claude
Code li vede da solo quando il login è con l'abbonamento, senza chiavi Google. Per vederli:
`cd workspace`, `claude`, poi `/mcp`: devono comparire `claude.ai Gmail`,
`claude.ai Google Calendar`, `claude.ai Google Drive`.

Cosa può fare di base: leggere, cercare e riassumere le mail, organizzarle con etichette
`AGIS/…` e archiviarle, preparare bozze; leggere tutti i calendari; cercare, leggere e creare
file su Drive. Cosa **non** fa mai: cestinare, eliminare, condividere, segnare spam. Inviare
mail e creare eventi sono spenti: si accendono in `config.toml` con `allow_send = true` e
`allow_calendar_edit = true` nella sezione `[connectors]`.

## Caselle di lavoro e scuola (V Media, ITS)

Il connettore Gmail di claude.ai vede solo la Gmail personale. Per V Media e ITS AGIS ha un
collegamento suo (`agis/google_mcp.py`) che lavora direttamente in quelle caselle: cerca,
legge, etichetta/archivia e crea **bozze con il mittente giusto**. Non può inviare né
cancellare: quegli strumenti non esistono proprio.

Configurazione (una volta sola, gratuita):
1. **Progetto Google Cloud** — su console.cloud.google.com, con l'account personale, crea il
   progetto `AGIS`; in *API e servizi → Libreria* abilita **Gmail API**.
2. **Schermata di consenso** — *Google Auth Platform*: nome app `AGIS`, pubblico **Esterno**.
   In *Pubblico* premi **Pubblica app** (stato "In produzione": il collegamento non scade
   ogni 7 giorni; la verifica Google non serve per uso personale).
3. **Client** — *Client → Crea client → App desktop*, poi **Scarica JSON** e salvalo come
   `data\google\client_secret.json`.
4. In `config.toml` aggiungi la sezione `[google]` di `config.example.toml`, poi
   `pip install -r requirements.txt`.
5. Collega ogni account: `python scripts\collega_google.py a.loffredo@v-media.it` (e poi
   quello ITS). Nel browser scegli quell'account; alla schermata "Google non ha verificato
   questa app" → *Avanzate* → *Vai ad AGIS* → *Continua*. È la tua app: l'avviso è normale.
6. Riavvia AGIS e chiedi "che mail ho su V Media?".

Se compare "accesso bloccato dall'amministratore", quell'organizzazione blocca le app
esterne: l'amministratore può autorizzare l'ID client di AGIS dalla Console di amministrazione
(Sicurezza → Controlli API), altrimenti per quella casella resta l'inoltro.

## Il cervello condiviso

App e task automatici (brief delle 6:00, bozze social del lunedì, radar prospect del
giovedì) usano le stesse tre fonti su Notion, sotto la pagina **Jarvis**:

| Fonte | Cosa contiene | Chi scrive |
|---|---|---|
| **Memoria AGIS** | chi sei, clienti, account, preferenze, regole fisse | tu (e AGIS dopo il tuo ok) |
| **Feedback AGIS** | correzioni e regole, con Ambito (Brief, Bozze social…) e Stato | tu, i 👍/👎 dell'app, AGIS quando lo correggi in chat |
| **Brief giornalieri** | un brief per giorno | il task delle 6:00 |

L'app all'avvio, ogni 2 ore e quando premi **⟳** carica su Notion i 👍/👎 in sospeso e
riscarica memoria, feedback e brief di oggi in `workspace/memoria/notion.md`. Le risposte
restano veloci e AGIS sa sempre cosa c'era nel brief. Se Notion non risponde, usa l'ultima
copia buona. Per correggere AGIS ovunque basta una riga in Feedback AGIS.

Ogni **domenica alle 18:31** AGIS rilegge feedback e lavoro della settimana e propone in
**Revisioni AGIS** come cambiare le proprie istruzioni (prima → dopo). Metti Stato =
"Approvata" (o scrivi in Note quali approvi) e la sera alle 20:35 le applica da solo.

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
- [x] v0.2 — cervello condiviso su Notion con brief e task automatici
- [x] Auto-miglioramento: revisione ogni domenica (Revisioni AGIS) applicata dopo il tuo ok
- [x] Gmail, Calendar e Drive tramite i connettori claude.ai
- [x] v0.4 — cervello sempre acceso, risposte in streaming, voce frase per frase
- [x] v0.5 — caselle V Media e ITS collegate direttamente (bozze col mittente giusto)
- [ ] Icona nell'area di notifica e avvio automatico con Windows
- [ ] Brief del mattino letto ad alta voce alle 6:00
- [ ] Parola di attivazione ("Ehi AGIS") senza tasti
- [ ] Installer `.exe`

## Sviluppo

```powershell
pip install pytest
python -m pytest
```
