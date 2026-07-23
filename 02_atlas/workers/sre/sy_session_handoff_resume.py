#!/usr/bin/env python3
#        abandon du fractionnement (sy_session_split.py retiré).
"""sy_session_handoff_resume.py — Hook SessionStart : auto-rappel du dernier handoff.

Au démarrage d'une nouvelle session (startup/clear/resume), réinjecte automatiquement
le handoff le plus récent produit par sy_session_split.py — pour reprendre sans rien
réexpliquer après un fractionnement. Ferme la boucle : split crée → resume réinjecte.

Filtres (anti-bruit + anti-boucle) :
  - < 24h (SY_HANDOFF_RESUME_MAX_AGE_H) — pas de handoff périmé.
  - session_id du handoff ≠ session_id courante — ne pas se réinjecter soi-même.
  - handoff REMPLI (placeholders d'origine absents) — pas de stub vierge inutile.
  - kill-switch SY_HANDOFF_RESUME_DISABLED=1.
Fail-open absolu : moindre souci → print rien (exit 0).

Injection = print sur stdout (Claude Code injecte stdout brut au SessionStart,
cf. patron sy_cicatrices_inject.py).
"""
from __future__ import annotations

import json
import os
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
        if best is None or mtime > best[0]:
            best = (mtime, p, body)

    if best is None:
        return 0

    _, p, body = best
    sys.stdout.write(
        "📤 HANDOFF DE SESSION PRÉCÉDENTE (auto-chargé par sy_session_handoff_resume.py)\n"
        "Reprends depuis l'état décrit ci-dessous — ne recommence pas depuis zéro.\n"
        f"(source : {p.name})\n\n{body}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
