"""Server MCP "agis-files": riordinare file e cartelle del PC in modo sicuro.

Strumenti: elencare, creare cartelle, spostare/rinominare e annullare l'ultimo
spostamento. Solo dentro le cartelle consentite (Download, Desktop, Documenti; mai la
cartella di AGIS). Non esiste nessuno strumento per cancellare o sovrascrivere: un file
con lo stesso nome viene salvato come "nome (2).ext". Ogni spostamento finisce in un
registro, così l'ultima operazione si può sempre annullare.

È il sostituto sicuro di Bash/PowerShell: AGIS legge mail e pagine web, e un comando
libero sul PC sarebbe troppo rischioso se qualcuno nascondesse istruzioni in un testo.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

SERVER_NAME = "agis-files"
MAX_LIST = 400
MAX_MOVES = 300
DEFAULT_ROOTS = ["~/Downloads", "~/Desktop", "~/Documents"]


def default_roots(home: Path | None = None) -> list[str]:
    """Cartelle standard, più le versioni OneDrive se Windows le ha spostate lì."""
    home = home or Path.home()
    roots = list(DEFAULT_ROOTS)
    for name in os.listdir(home) if home.exists() else []:
        if name.lower().startswith("onedrive"):
            for sub in ("Desktop", "Documents", "Documenti"):
                if (home / name / sub).is_dir():
                    roots.append(str(home / name / sub))
    return roots


class FileTools:
    def __init__(self, roots: list[str], forbidden: list[Path], log_path: Path):
        self.roots = []
        for r in roots:
            p = Path(os.path.expanduser(r)).resolve()
            if p.is_dir() and p not in self.roots:
                self.roots.append(p)
        self.forbidden = [Path(f).resolve() for f in forbidden]
        self.log_path = log_path

    # --- percorsi -----------------------------------------------------------------
    def resolve(self, path: str) -> Path:
        """Accetta un percorso assoluto o relativo a una cartella consentita ('Downloads/foto')."""
        raw = Path(os.path.expanduser(path.strip().strip('"')))
        if raw.is_absolute():
            candidates = [raw]
        else:
            first = raw.parts[0].lower() if raw.parts else ""
            named = [r.parent / raw for r in self.roots if r.name.lower() == first]
            candidates = named + [r / raw for r in self.roots]
        allowed = [c.resolve() for c in candidates if self._allowed(c.resolve())]
        for p in allowed:
            if p.exists():
                return p
        if allowed:
            return allowed[0]
        raise PermissionError(
            f"'{path}' è fuori dalle cartelle che posso toccare: "
            + ", ".join(str(r) for r in self.roots))

    def _allowed(self, p: Path) -> bool:
        if any(p == f or f in p.parents for f in self.forbidden):
            return False
        if any(part.startswith(".") for part in p.parts[-3:]):
            return False  # niente file/cartelle nascosti (.git, .ssh, ...)
        return any(p == r or r in p.parents for r in self.roots)

    @staticmethod
    def _free_name(dst: Path) -> Path:
        if not dst.exists():
            return dst
        stem, suf, n = dst.stem, dst.suffix, 2
        while (dst.parent / f"{stem} ({n}){suf}").exists():
            n += 1
        return dst.parent / f"{stem} ({n}){suf}"

    # --- strumenti ----------------------------------------------------------------
    def list_roots(self) -> str:
        return "Cartelle che posso riordinare:\n" + "\n".join(f"- {r}" for r in self.roots)

    def list_dir(self, path: str, recursive: bool = False) -> str:
        base = self.resolve(path)
        if not base.is_dir():
            raise NotADirectoryError(f"'{base}' non è una cartella")
        it = base.rglob("*") if recursive else base.iterdir()
        rows, total = [], 0
        for p in sorted(it, key=lambda x: (not x.is_dir(), str(x).lower())):
            if not self._allowed(p.resolve()):
                continue
            total += 1
            if len(rows) >= MAX_LIST:
                continue
            st = p.stat()
            when = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d")
            rel = p.relative_to(base)
            if p.is_dir():
                rows.append(f"📁 {rel}/")
            else:
                rows.append(f"📄 {rel} · {_size(st.st_size)} · {when}")
        head = f"{base} — {total} elementi"
        if total > MAX_LIST:
            head += f" (mostro i primi {MAX_LIST}: usa una sottocartella per vedere il resto)"
        return head + "\n" + "\n".join(rows)

    def mkdir(self, path: str) -> str:
        p = self.resolve(path)
        p.mkdir(parents=True, exist_ok=True)
        return f"Cartella pronta: {p}"

    def move(self, moves: list[dict]) -> str:
        if len(moves) > MAX_MOVES:
            raise ValueError(f"Massimo {MAX_MOVES} spostamenti per volta")
        done, errors = [], []
        for m in moves:
            try:
                src = self.resolve(str(m.get("from", "")))
                if not src.exists():
                    raise FileNotFoundError(f"non esiste: {src}")
                dst = self.resolve(str(m.get("to", "")))
                if dst.is_dir():
                    dst = dst / src.name
                if dst == src:
                    continue
                if src.is_dir() and (dst == src or src in dst.parents):
                    raise ValueError("non posso spostare una cartella dentro se stessa")
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst = self._free_name(dst)
                src.rename(dst)
                done.append({"from": str(src), "to": str(dst)})
            except Exception as e:  # noqa: BLE001
                errors.append(f"- {m.get('from')}: {e}")
        if done:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"t": time.time(), "moves": done}, ensure_ascii=False) + "\n")
        out = f"Spostati {len(done)} elementi."
        if errors:
            out += f"\nNon spostati ({len(errors)}):\n" + "\n".join(errors[:30])
        return out

    def undo_last(self) -> str:
        if not self.log_path.exists():
            return "Non c'è niente da annullare."
        lines = [ln for ln in self.log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if not lines:
            return "Non c'è niente da annullare."
        batch = json.loads(lines[-1])
        back, errors = 0, []
        for m in reversed(batch["moves"]):
            src, dst = Path(m["to"]), Path(m["from"])
            try:
                if not src.exists():
                    raise FileNotFoundError("non è più dove l'avevo messo")
                dst.parent.mkdir(parents=True, exist_ok=True)
                src.rename(self._free_name(dst))
                back += 1
            except Exception as e:  # noqa: BLE001
                errors.append(f"- {src.name}: {e}")
        self.log_path.write_text("\n".join(lines[:-1]) + ("\n" if lines[:-1] else ""),
                                 encoding="utf-8")
        out = f"Annullato: {back} elementi rimessi al loro posto."
        if errors:
            out += "\nNon riportati:\n" + "\n".join(errors[:30])
        return out


def _size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def build_server(tools: FileTools):
    from mcp.server.mcpserver import MCPServer

    from .google_mcp import _friendly

    server = MCPServer(
        SERVER_NAME,
        instructions=("Riordina file e cartelle del PC di Loffre (Download, Desktop, Documenti). "
                      "Puoi elencare, creare cartelle, spostare/rinominare e annullare l'ultimo "
                      "spostamento. Non puoi cancellare né sovrascrivere. Prima di spostare molti "
                      "file proponi il piano e aspetta l'ok."))

    @server.tool()
    @_friendly
    def pc_files_roots() -> str:
        """Elenca le cartelle del PC che puoi leggere e riordinare."""
        return tools.list_roots()

    @server.tool()
    @_friendly
    def pc_files_list(path: str, recursive: bool = False) -> str:
        """Elenca il contenuto di una cartella (nome, dimensione, data). `path` assoluto o
        relativo, es. 'Downloads' o 'Downloads/Fatture'."""
        return tools.list_dir(path, recursive)

    @server.tool()
    @_friendly
    def pc_files_mkdir(path: str) -> str:
        """Crea una cartella (anche annidata), es. 'Downloads/Fatture/2026'."""
        return tools.mkdir(path)

    @server.tool()
    @_friendly
    def pc_files_move(moves: list[dict]) -> str:
        """Sposta o rinomina file e cartelle. `moves` = [{"from": "...", "to": "..."}]; se
        "to" è una cartella esistente il file ci finisce dentro col suo nome. Mai sovrascrive:
        con un nome già usato salva "nome (2)". Massimo 300 per volta, annullabile."""
        return tools.move(moves)

    @server.tool()
    @_friendly
    def pc_files_undo_last() -> str:
        """Annulla l'ultimo gruppo di spostamenti, rimettendo i file dov'erano."""
        return tools.undo_last()

    return server


def make_tools(cfg) -> FileTools:
    from .config import ROOT
    roots = cfg.files.roots or default_roots()
    return FileTools(roots, forbidden=[ROOT], log_path=cfg.data_dir / "spostamenti_file.jsonl")


def main() -> None:
    from . import config as config_mod
    build_server(make_tools(config_mod.load())).run("stdio")


if __name__ == "__main__":
    main()
