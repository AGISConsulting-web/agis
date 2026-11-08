"""Accesso alle caselle Gmail di lavoro e scuola (V Media, ITS) con OAuth di Google.

Ogni account ha il suo token in data/google/<email>.json, creato una volta con
`python scripts/collega_google.py <email>`. I token restano solo sul tuo PC.
"""
from __future__ import annotations

from pathlib import Path

# gmail.modify = leggere, etichettare, archiviare e creare bozze. L'invio e la
# cancellazione non sono esposti da AGIS (vedi google_mcp.py).
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def token_path(data_dir: Path, email: str) -> Path:
    return data_dir / "google" / f"{email.lower()}.json"


def load_credentials(data_dir: Path, email: str):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    path = token_path(data_dir, email)
    if not path.exists():
        raise RuntimeError(f"Account {email} non collegato: esegui "
                           f"python scripts\\collega_google.py {email}")
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(f"Il collegamento con {email} è scaduto: rifallo con "
                                   f"python scripts\\collega_google.py {email}") from e
            path.write_text(creds.to_json(), encoding="utf-8")
        else:
            raise RuntimeError(f"Collegamento con {email} non valido: rifallo con "
                               f"python scripts\\collega_google.py {email}")
    return creds


def gmail_service(data_dir: Path, email: str):
    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=load_credentials(data_dir, email),
                 cache_discovery=False)


def authorize(client_secret: Path, data_dir: Path, email: str) -> str:
    """Apre il browser per il consenso e salva il token. Restituisce l'email collegata."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    if not client_secret.exists():
        raise RuntimeError(f"Manca {client_secret}: scaricalo da Google Cloud (vedi README).")
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
    creds = flow.run_local_server(port=0, login_hint=email, prompt="consent",
                                  open_browser=True,
                                  authorization_prompt_message="Si apre il browser: accedi con {url}",
                                  success_message="Fatto! Puoi chiudere questa scheda e tornare ad AGIS.")
    profile = build("gmail", "v1", credentials=creds, cache_discovery=False) \
        .users().getProfile(userId="me").execute()
    actual = profile.get("emailAddress", "").lower()
    if actual != email.lower():
        raise RuntimeError(f"Hai fatto l'accesso con {actual} invece che con {email}. Riprova "
                           "scegliendo l'account giusto nel browser.")
    path = token_path(data_dir, email)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(creds.to_json(), encoding="utf-8")
    return actual
