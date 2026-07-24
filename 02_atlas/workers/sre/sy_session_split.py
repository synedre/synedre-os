#!/usr/bin/env python3
#        sous 130k — les sessions ne franchiront plus le seuil ; OU migration du
#        handoff vers une table sy_session_handoff.
"""sy_session_split.py — Hook Stop : fractionnement de session à seuil de contexte.

Jobsite #508 (routage-coût) — coupe le coût quadratique des sessions longues
(historique + tool results renvoyés à chaque tour). Déclenché à chaque Stop :
  1. mesure le contexte RÉEL (message.usage du dernier assistant =
     input + cache_read + cache_creation) et le nombre de tours ;
  2. si seuil franchi ET pas déjà « armé » pour ce franchissement :
       - Passe 1 (stop_hook_active=false) → {"decision":"block","reason":…}
         force l'écriture d'un handoff persistant + signale le fractionnement.
       - Passe 2 (stop_hook_active=true)  → {"systemMessage":…} warn (anti-boucle).
  3. re-armé quand le contexte repasse sous le seuil bas (= compaction survenue).

Le backstop natif (CLAUDE_CODE_AUTO_COMPACT_WINDOW=150000 dans ./glm et ./codex)
garantit le reset mémoire via Haiku=glm-4.7 (gratuit) — même si ce hook rate ou
que personne ne /clear (cas autonome). Ce hook ajoute la couche de contrôle :
handoff persistant (reprise/crash) + métriques (runaway detector, dashboard cost).

Garde-fous :
  - Kill-switch SY_SESSION_SPLIT_DISABLED=1 → exit 0.
  - PAS de worker guard : on agit volontairement sur l'autonome (cœur de l'objectif).
  - Anti-boucle : marker « armed » session-level (1 block par franchissement,
    re-armé après compaction) + stop_hook_active (passe 2 même tour).
  - Dégradation gracieuse totale : toute exception → exit 0 (jamais de brick).

Tous les paths/seuils sont surchargeables par env (pour les tests unitaires).

"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ─── Bootstrap ─────────────────────────────────────────────────────────────────

_DIR = Path(__file__).resolve().parent
try:
    sys.path.insert(0, str(_DIR.parent))
    from sy_env import load_env  # type: ignore
    load_env()
except Exception:
    pass  # fail-open : seuils/défauts marchent sans env chargé

# ─── Config (surchargeable par env pour les tests) ─────────────────────────────

SEUIL_HAUT = int(os.environ.get("SY_SESSION_SPLIT_CTX_THRESHOLD", "130000"))
SEUIL_TOUR = int(os.environ.get("SY_SESSION_SPLIT_TURN_THRESHOLD", "150"))
SEUIL_BAS  = int(os.environ.get("SY_SESSION_SPLIT_CTX_REARM", "100000"))

LOG_PATH      = Path(os.environ.get(
    "SY_SESSION_SPLIT_LOG",
    str(_DIR / "logs" / "sy_session_split" / "split_log.jsonl")))
HANDOFF_DIR   = Path(os.environ.get(
    "SY_SESSION_SPLIT_HANDOFF_DIR",
    str(_DIR / "state" / "session-handoffs")))
MARKER_DIR    = Path(os.environ.get(
    "SY_SESSION_SPLIT_MARKER_DIR", "/tmp"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# ─── Mesure du transcript (1 passe, vrai usage) ────────────────────────────────

def _measure(transcript_path: str) -> tuple[int, int, int, int]:
    """Retourne (tours, ctx_total, input_tokens, cache_read).

    ctx_total = input + cache_read + cache_creation du DERNIER message assistant.
    C'est la fenêtre réellement renvoyée au modèle = coût quadratique réel.
    """
    turns = 0
    last_usage: dict | None = None
    try:
        with open(transcript_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") == "assistant":
                    turns += 1
                    msg = obj.get("message")
                    if isinstance(msg, dict):
                        u = msg.get("usage")
                        if isinstance(u, dict):
                            last_usage = u
    except OSError:
        return 0, 0, 0, 0

    u = last_usage or {}
    inp = int(u.get("input_tokens", 0) or 0)
    cache_read = int(u.get("cache_read_input_tokens", 0) or 0)
    cache_create = int(u.get("cache_creation_input_tokens", 0) or 0)
    return turns, inp + cache_read + cache_create, inp, cache_read


# ─── Effets : handoff persistant + log JSONL ───────────────────────────────────

def _write_handoff(session_id: str, turns: int, ctx: int, cwd: str = "") -> Path | None:
    """Crée un handoff stub versionné (jamais d'écrasement). L'agent le remplit.

    ``cwd`` est inscrit en entête et fait foi pour le SCOPE de reprise : tous les
    worktrees partagent ce dossier de handoffs (les hooks pointent en absolu vers
    ${SYNEDRE_ROOT}/synedre/), donc sans cette ligne un handoff de
    `wt/jobsite-X` remonterait dans une session ouverte ailleurs.
    Lu par sy_session_handoff_resume._cwd_of() — ne pas changer le format seul.
    """
    try:
        HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
        sid_safe = (session_id or "nosession").replace("/", "_").replace("\\", "_")
        path = HANDOFF_DIR / f"{sid_safe}-{_now_stamp()}.md"
        path.write_text(
            f"# Handoff de session — fractionnement (contexte ~{ctx // 1000}k, "
            f"{turns} tours)\n\n"
            f"> Session `{session_id}` — {_now_iso()}\n"
            f"> Répertoire de work_order : `{cwd or os.getcwd()}`\n"
            f"> Détecté par `sy_session_split.py` (jobsite #508). Le contexte a "
            f"franchi le seuil de fractionnement : coût quadratique.\n"
            f"> **Remplis les 4 sections ci-dessous** puis fractionne la session "
            f"(/clear en interactif ; la compaction native reset en autonome).\n\n"
            f"## 🎯 Objectif de la session\n"
            f"(en 1-3 phrases : ce que cette session devait accomplir)\n\n"
            f"## ✅ État actuel\n"
            f"(fait : fichiers modifiés, décisions, commits)\n\n"
            f"## ➡️ Prochain geste concret\n"
            f"(la prochaine action immédiate pour reprendre)\n\n"
            f"## ⚠️ Contexte critique à ne pas perdre\n"
            f"(invariants, contraintes, gotchas, fichiers clés)\n",
            encoding="utf-8",
        )
        return path
    except Exception as exc:
        print(f"[sy_session_split] handoff write failed: {exc}", file=sys.stderr)
        return None


def _log(**fields) -> None:
    """Append JSONL fail-open (patron _log_borne). Alimente runaway + cost."""
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": _now_iso(), **fields}
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"[sy_session_split] log failed: {exc}", file=sys.stderr)


def _armed_path(session_id: str) -> Path:
    sid_safe = (session_id or "nosession").replace("/", "_").replace("\\", "_")
    return MARKER_DIR / f"sy-session-split-armed-{sid_safe}"


# ─── Décision (séparée de l'IO pour la testabilité) ────────────────────────────

def _decide(
    *,
    stop_active: bool,
    session_id: str,
    turns: int,
    ctx: int,
    inp: int,
    cache_read: int,
    cwd: str = "",
) -> tuple[int, dict | None]:
    """Retourne (exit_code, output_json | None). Effectue les effets de bord."""
    seuil_franchi = ctx >= SEUIL_HAUT or turns >= SEUIL_TOUR
    armed = _armed_path(session_id)

    if seuil_franchi:
        if stop_active:
            # Passe 2 — anti-boucle même tour
            _log(session_id=session_id, turns=turns, input_tokens=inp,
                 cache_read=cache_read, ctx=ctx, action="warn")
            return 0, {"systemMessage":
                f"⚠️ Contexte session à ~{ctx // 1000}k tokens / {turns} tours — "
                f"handoff déjà demandé (anti-boucle). Fractionne la session "
                f"(/clear) pour reprendre depuis le handoff."}
        if armed.exists():
            # Déjà notifié pour ce franchissement — attendre la compaction native
            return 0, None
        # Passe 1 — 1er franchissement : block + handoff persistant
        handoff = _write_handoff(session_id, turns, ctx, cwd)
        try:
            MARKER_DIR.mkdir(parents=True, exist_ok=True)
            armed.touch()
        except OSError:
            pass
        _log(session_id=session_id, turns=turns, input_tokens=inp,
             cache_read=cache_read, ctx=ctx, action="block",
             handoff=(str(handoff) if handoff else None))
        reason = (
            f"🔄 FRACTIONNEMENT DE SESSION — contexte ~{ctx // 1000}k tokens / "
            f"{turns} tours (coût quadratique : l'historique est renvoyé à chaque "
            f"tour). Doctrine #508 : produis un handoff de reprise AVANT de "
            f"continuer.\n\n"
            f"👉 Remplis les 4 sections du handoff : {handoff}\n"
            f"   (Objectif / État actuel / Prochain geste / Contexte critique)\n\n"
            f"Puis fractionne : /clear en interactif (et reprends en collant le "
            f"handoff). En autonomie, la compaction native (backstop 150k) reset "
            f"le contexte — mais le handoff persistant reste ta garantie de "
            f"reprise / crash."
        )
        return 0, {"decision": "block", "reason": reason}

    # Sous le seuil : re-arm si une compaction native vient de survenir
    if ctx < SEUIL_BAS and armed.exists():
        try:
            armed.unlink()
        except OSError:
            pass
        _log(session_id=session_id, turns=turns, input_tokens=inp,
             cache_read=cache_read, ctx=ctx, action="rearmed")
    return 0, None


# ─── Point d'entrée ────────────────────────────────────────────────────────────

def main() -> int:
    """Fail-open absolu : toute exception → exit 0 (jamais de brick de session)."""
    try:
        return _run()
    except Exception as exc:
        print(f"[sy_session_split] UNEXPECTED ERROR (fail-open): {exc}",
              file=sys.stderr)
        return 0


def _run() -> int:
    if os.environ.get("SY_SESSION_SPLIT_DISABLED") == "1":
        return 0
    # PAS de worker guard : on agit volontairement sur l'autonome.

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    session_id = payload.get("session_id", "") or "nosession"
    transcript_path = payload.get("transcript_path", "") or ""
    stop_active = payload.get("stop_hook_active") is True

    if not transcript_path or not Path(transcript_path).is_file():
        return 0

    turns, ctx, inp, cache_read = _measure(transcript_path)
    exit_code, output = _decide(
        stop_active=stop_active, session_id=session_id,
        turns=turns, ctx=ctx, inp=inp, cache_read=cache_read,
        cwd=payload.get("cwd", "") or "",
    )
    if output is not None:
        sys.stdout.write(json.dumps(output, ensure_ascii=False))
        sys.stdout.write("\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
