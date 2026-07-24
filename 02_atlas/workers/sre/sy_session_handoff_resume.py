#!/usr/bin/env python3
#        abandon du fractionnement (sy_session_split.py retiré).
"""sy_session_handoff_resume.py — Hook SessionStart : auto-rappel du dernier handoff.

Au démarrage d'une nouvelle session (startup/clear/resume), réinjecte automatiquement
le handoff le plus récent produit par sy_session_split.py — pour reprendre sans rien
réexpliquer après un fractionnement. Ferme la boucle : split crée → resume réinjecte.

Filtres (anti-bruit + anti-boucle) :
  - < 24h (SY_HANDOFF_RESUME_MAX_AGE_H) — pas de handoff périmé.
  - session_id du handoff ≠ session_id courante — ne pas se réinjecter soi-même.
  - MÊME RÉPERTOIRE DE WORK_ORDER que la session courante. Tous les worktrees
    partagent ce dossier de handoffs (hooks câblés en absolu vers
    ${SYNEDRE_ROOT}/synedre/) : sans ce scope, le handoff de
    `wt/jobsite-X` remonte dans une session ouverte sur un autre tenant —
    reprise sur le mauvais sujet. Les handoffs antérieurs à ce scope n'ont pas
    la ligne « Répertoire de work_order » : acceptés (compat, ils périment en 24h)
    mais signalés comme tels dans la bannière.
  - handoff REMPLI (placeholders d'origine absents) — pas de stub vierge inutile.
  - kill-switch SY_HANDOFF_RESUME_DISABLED=1.
Fail-open absolu : moindre souci → print rien (exit 0).

Sortie = JSON à DEUX CANAUX (patron sy_scars_inject_agent.py / hook-stop-
uncommitted-warn.sh), parce qu'un stdout brut n'est visible que de l'agent :
  - ``systemMessage``                      → AFFICHÉ DANS LE TERMINAL D'ALEX.
    Carte d'identité du handoff repris : QUI (session courte + tenant) et QUOI
    (sujet + prochain geste + chemin du fichier). Sans ça, la reprise est
    invisible côté humain et prête à confusion (« de quoi me parle-t-il ? »).
  - ``hookSpecificOutput.additionalContext`` → injecté dans le contexte agent.
    Le corps complet du handoff, comme avant.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

_DIR = Path(__file__).resolve().parent
try:
    sys.path.insert(0, str(_DIR.parent))
    from sy_env import load_env  # type: ignore
    load_env()
except Exception:
    pass

HANDOFF_DIR = Path(os.environ.get(
    "SY_SESSION_SPLIT_HANDOFF_DIR",
    str(_DIR / "state" / "session-handoffs")))
MAX_AGE_S = int(os.environ.get("SY_HANDOFF_RESUME_MAX_AGE_H", "24")) * 3600

# Marqueurs des placeholders du stub vierge créé par sy_session_split.py.
_PLACEHOLDER_MARKERS = (
    "(en 1-3 phrases",
    "(fait :",
    "(la prochaine action",
    "(invariants, contraintes",
)


def _title(body: str) -> str:
    """Sujet du handoff = titre H1, débarrassé du préfixe « Handoff de session — »."""
    for line in body.splitlines():
        if line.startswith("# "):
            t = line[2:].strip()
            return t.split("—", 1)[1].strip() if "—" in t else t
    return "(sans titre)"


def _tenant(body: str) -> str:
    """Codename tenant s'il est nommé explicitement (``tenant `xxx``` )."""
    m = re.search(r"tenants?\s+`([a-z0-9][a-z0-9._-]*)`", body)
    return m.group(1) if m else ""


def _cwd_of(body: str) -> str:
    """Répertoire de work_order inscrit par sy_session_split._write_handoff().
    Chaîne vide = handoff legacy, écrit avant l'introduction du scope."""
    m = re.search(r"^>\s*R[ée]pertoire de work_order\s*:\s*`([^`]+)`", body, re.M)
    return m.group(1).strip() if m else ""


def _same_dir(a: str, b: str) -> bool:
    """Comparaison de répertoires tolérante aux symlinks et au slash final."""
    try:
        return os.path.realpath(a) == os.path.realpath(b)
    except OSError:
        return a.rstrip("/") == b.rstrip("/")


def _plain(s: str) -> str:
    """Markdown → texte nu : gras/code/puces/numérotation retirés (lisible en terminal)."""
    s = re.sub(r"\*\*|`|__", "", s)
    s = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", s)
    return s.strip(" :—-")


def _next_step(body: str) -> str:
    """Prochain geste : le titre de section « Prochain geste » (après son tiret),
    à défaut la 1re ligne de prose de cette section. Vide si la section manque."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("#") or "prochain geste" not in line.lower():
            continue
        head = line.lstrip("# ").strip()
        if "—" in head:
            return _plain(head.split("—", 1)[1])[:140]
        for nxt in lines[i + 1:]:
            s = nxt.strip()
            if s.startswith("#"):
                break
            if s and not s.startswith(("```", ">", "|")):
                return _plain(s)[:140]
        return _plain(head)[:140]
    return ""


def _emit(path: Path, body: str, age_h: float) -> None:
    """Écrit les deux canaux : carte d'identité pour Alex, corps pour l'agent."""
    sid = path.stem.rsplit("-", 1)[0] if "-" in path.stem else path.stem
    age = f"il y a {age_h:.0f} h" if age_h >= 1 else "il y a moins d'1 h"
    who = f"session {sid[:8]} · {age}"
    if tenant := _tenant(body):
        who += f" · tenant {tenant}"
    if not _cwd_of(body):
        who += " · ⚠ répertoire inconnu (handoff legacy)"

    banner = [f"📤 Handoff repris — {who}", f"   Sujet   : {_title(body)}"]
    if step := _next_step(body):
        banner.append(f"   Reste   : {step}")
    banner.append(f"   Fichier : {path}")

    print(json.dumps({
        "systemMessage": "\n".join(banner),
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                "📤 HANDOFF DE SESSION PRÉCÉDENTE "
                "(auto-chargé par sy_session_handoff_resume.py)\n"
                "Reprends depuis l'état décrit ci-dessous — "
                "ne recommence pas depuis zéro.\n"
                f"(source : {path.name})\n\n{body}\n"
            ),
        },
    }, ensure_ascii=False))


def main() -> int:
    try:
        return _run()
    except Exception as exc:
        print(f"[sy_session_handoff_resume] fail-open: {exc}", file=sys.stderr)
        return 0


def _run() -> int:
    if os.environ.get("SY_HANDOFF_RESUME_DISABLED") == "1":
        return 0
    if not HANDOFF_DIR.is_dir():
        return 0

    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    current_sid = (payload.get("session_id") or "").strip()
    current_cwd = (payload.get("cwd") or "").strip() or os.getcwd()

    now = time.time()
    best: tuple[float, Path, str] | None = None
    for p in HANDOFF_DIR.glob("*.md"):
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if now - mtime > MAX_AGE_S:
            continue
        # session_id = nom sans le suffixe timestamp (le stamp n'a pas de '-')
        sid_in_name = p.stem.rsplit("-", 1)[0] if "-" in p.stem else p.stem
        if current_sid and sid_in_name == current_sid:
            continue  # ne pas réinjecter la session courante
        try:
            body = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if any(mk in body for mk in _PLACEHOLDER_MARKERS):
            continue  # stub vierge, pas encore rempli
        h_cwd = _cwd_of(body)
        if h_cwd and current_cwd and not _same_dir(h_cwd, current_cwd):
            continue  # autre worktree / autre jobsite — pas notre reprise
        if best is None or mtime > best[0]:
            best = (mtime, p, body)

    if best is None:
        return 0

    mtime, p, body = best
    _emit(p, body, (now - mtime) / 3600)
    return 0


if __name__ == "__main__":
    sys.exit(main())
