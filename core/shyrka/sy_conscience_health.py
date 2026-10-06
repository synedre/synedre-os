#!/usr/bin/env python3
"""
sy_conscience_health — The engine health check (Phase 2).

Phase 0 perceives its doc, Phase 3 stitches it back. Phase 2 widens awareness to
the WHOLE body: a single nightly look aggregating the already-existing audits — scattered across
tables and logs — into a per-dimension report + a global verdict. This is the
"awareness of its own weakness and debt" requested by the Founder.

Four dimensions (all read, none touched — Phase 2 aggregates, does not fix):
  - proprioception : doc↔code drift        (sy_doc_drift, Phase 0)
  - dette          : open P0/P1 backlog    (sy_backlog)
  - apprentissage  : scar signal (mv_scars_kpi, + refresh freshness)
  - automates      : cron health           (sy_cron_errors)

Writes: sy_conscience_health (idempotent run_date+dimension snapshot) + an item
sy_daily_meet (the morning report the founder sees).

Usage :
  python3 synedre/sy_conscience_health.py            # check + snapshot/report write
  python3 synedre/sy_conscience_health.py --dry-run  # check printed, nothing written
Exit: 0 if global ok, 1 if warn, 2 if critical.

"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sy_entity_base import _run_sql_csv, _run_sql_write, _esc, DB_NAME  # noqa: E402
from sy_daily_meet import publier_snapshot  # noqa: E402

try:
    from synedre.sy_agent_call import invoke_agent  # noqa: E402
except Exception:  # noqa: BLE001
    invoke_agent = None  # type: ignore[assignment]

# Winnicott (codename 'sante') = Mental Health Guardian. He watches over the
# Founder, the agents, AND the engine — the holding figure that carries all
# the others. This is not a "backend" script auscultating the system: it is him.
# D.W. Winnicott was British → his voice is written IN ENGLISH.
WINNICOTT = "sante"

RANK = {"ok": 0, "warn": 1, "critical": 2}
ICON = {"ok": "✅", "warn": "🟠", "critical": "🔴"}


def _clamp(n: int) -> int:
    return max(0, min(100, n))


def dim_proprioception() -> dict:
    r = _run_sql_csv(
        f"SELECT count(*), count(*) FILTER (WHERE drift_kind='clean'), "
        f"count(*) FILTER (WHERE drift_kind='dead-ref'), COALESCE(max(drift_score),0) "
        f"FROM {DB_NAME}.sy_doc_drift WHERE run_date=(SELECT max(run_date) FROM {DB_NAME}.sy_doc_drift);"
    )
    total, clean, deadref, worst = (int(x) for x in r[0]) if r and r[0][0] else (0, 0, 0, 0)
    if total == 0:
        return {"dimension": "proprioception", "status": "warn", "score": None,
                "metric": {"note": "mirror never run"}, "summary": "No doc↔code mirror snapshot."}
    status = "critical" if deadref else ("warn" if clean < total else "ok")
    return {"dimension": "proprioception", "status": status, "score": round(100 * clean / total),
            "metric": {"total": total, "clean": clean, "drifted": total - clean, "dead_ref_chapters": deadref, "worst_score": worst},
            "summary": f"{total - clean}/{total} chapters drifting ({deadref} with dead refs)."}


def dim_dette() -> dict:
    r = _run_sql_csv(
        f"SELECT count(*) FILTER (WHERE priority='P0'), count(*) FILTER (WHERE priority='P1'), count(*) "
        f"FROM {DB_NAME}.sy_backlog WHERE status NOT IN ('done','cancelled');"
    )
    p0, p1, total = (int(x) for x in r[0]) if r else (0, 0, 0)
    status = "critical" if p0 > 0 else ("warn" if p1 > 15 else "ok")
    return {"dimension": "dette", "status": status, "score": _clamp(100 - p0 * 6 - p1),
            "metric": {"p0_open": p0, "p1_open": p1, "total_open": total},
            "summary": f"{p0} P0 + {p1} P1 open ({total} items in total)."}


def dim_apprentissage() -> dict:
    r = _run_sql_csv(
        f"SELECT total, unqualified, learnable, signal_ratio, "
        f"COALESCE(EXTRACT(day FROM now()-refreshed_at)::int, 999) "
        f"FROM {DB_NAME}.mv_scars_kpi;"
    )
    if not r:
        return {"dimension": "apprentissage", "status": "warn", "score": None,
                "metric": {"note": "mv_scars_kpi missing"}, "summary": "Scar KPI unavailable."}
    total, unq, learn, ratio, stale = r[0]
    total, unq, learn, stale = int(total), int(unq), int(learn), int(stale)
    ratio = float(ratio)
    status = "critical" if stale > 3 else ("warn" if ratio < 0.5 else "ok")
    note = f"signal {ratio:.2f}, {unq} unqualified scars"
    if stale > 3:
        note += f" — ⚠ KPI frozen for {stale}d (refresh cron dead)"
    return {"dimension": "apprentissage", "status": status, "score": round(ratio * 100),
            "metric": {"total": total, "unqualified": unq, "learnable": learn, "signal_ratio": round(ratio, 4), "refresh_stale_days": stale},
            "summary": note + "."}


def _automates_sql(errors_rel: str, automates_rel: str) -> str:
    """The three counters of the automates dimension, over injectable relations.

    Relation names are parameters so that the query is REPLAYABLE against
    fixtures (`(VALUES …)`) without writing a row to the database: this is what
    makes the bug below demonstrable by mutation. They never come from external input.

    SCAR (2026-08-20, twin of cron rearming): the `deact` counter read
    `count(DISTINCT script_name) FILTER (WHERE deactivated <> 0)` over the ENTIRE table,
    with no time bound or concept of a “last row”. Yet `sy_cron_errors` is an
    EVENT LOG, not a state table: the shutdown row remains written forever,
    even when a `recovered` follows it three minutes later. Measurement on
    20/08: 6 scripts counted as “disabled”, none actually was — the oldest had
    restarted on 08/06. The dimension therefore rendered `critical`, score 0,
    PERMANENTLY, making a real critical impossible to detect. The same confusion that
    cost 19 h of `sy_atlas_inbox_poll`: a past event is not a current state.

    Hence `DISTINCT ON (script_name)`: we consider only the LAST row of each
    script. `id_error DESC` breaks ties between two events in the same second — without it,
    the ordering would be indeterminate and the verdict could oscillate from one run to another.

    `err24` (error flow over 24 h) and `unregistered` (registry gap) keep their
    semantics: the former rightly counts events, the latter a state that lasts as long
    as `sy_automates` remains incomplete.
    """
    return (
        f"SELECT "  # sql-ident:allow errors_rel and automates_rel are RELATION NAMES
        # (real table in production, `(VALUES …)` subquery under test): an
        # identifier cannot be passed as a bound parameter. No value is
        # interpolated here, and neither name comes from external input.
        f"  (SELECT count(*) FROM {errors_rel} e "
        f"     LEFT JOIN {automates_rel} a "
        f"       ON a.key_name = regexp_replace(e.script_name, '\\.py$', '') "
        f"    WHERE e.date_add > now()-interval '24h' "
        f"      AND a.scope='synedre' AND a.active=1), "
        f"  (SELECT count(*) FROM ("
        f"        SELECT DISTINCT ON (script_name) script_name, deactivated "
        f"          FROM {errors_rel} x "
        f"         ORDER BY script_name, date_add DESC, id_error DESC) d "
        f"     JOIN {automates_rel} a "
        f"       ON a.key_name = regexp_replace(d.script_name, '\\.py$', '') "
        f"    WHERE d.deactivated <> 0 AND a.scope='synedre' AND a.active=1), "
        f"  (SELECT count(DISTINCT e.script_name) FROM {errors_rel} e "
        f"     LEFT JOIN {automates_rel} a "
        f"       ON a.key_name = regexp_replace(e.script_name, '\\.py$', '') "
        f"    WHERE a.key_name IS NULL);"
    )


def dim_automates() -> dict:
    # Scope-aware: the engine's health only counts automations EXPLICITLY
    # registered scope='synedre' AND active. A codemyshop-oss/tenant automation
    # (which must live on ITS OWN VPS) or one OFF (active=0) does not degrade
    # shyrka health — "off on purpose" ≠ "broken", "not mine" ≠ "broken".
    #
    # Boundary change (Synedre/CodeMyShop): the implicit COALESCE(scope,'synedre')
    # default is removed. A script that errors but is NOT in the registry is no
    # longer charged to Synedre as an outage — it feeds a SEPARATE "registry gap"
    # signal (housekeeping, WARN), not a false critical. The registry must stay
    # complete (cf sy_automates): register every script logging into sy_cron_errors.
    #
    # `deact` = scripts OFF AT THIS INSTANT, not those that were off one day:
    # selecting the last row per script lives in _automates_sql, which also carries
    # the 20/08 scar (6 counted, none off).
    r = _run_sql_csv(_automates_sql(f"{DB_NAME}.sy_cron_errors",
                                    f"{DB_NAME}.sy_automates"))
    err24, deact, unregistered = (int(x) for x in r[0]) if r else (0, 0, 0)
    # Health = only the registered synedre scope. A registry gap degrades at
    # most to WARN (to be classified), never to critical (not a Synedre outage).
    status = "critical" if deact > 0 else (
        "warn" if (err24 > 0 or unregistered > 0) else "ok")
    score = _clamp(100 - err24 * 10 - deact * 20 - unregistered * 5)
    summary = f"{err24} cron error(s)/24h, {deact} disabled script(s) (synedre scope)."
    if unregistered > 0:
        summary += f" + {unregistered} unregistered script(s) to classify (unknown scope)."
    return {"dimension": "automates", "status": status, "score": score,
            "metric": {"errors_24h": err24, "deactivated_scripts": deact,
                       "unregistered_scripts": unregistered, "scope": "synedre"},
            "summary": summary}


def dim_couverture() -> dict:
    """Blind spots (Phase 5): body units never documented (sy_doc_coverage)."""
    r = _run_sql_csv(
        f"SELECT count(*), count(*) FILTER (WHERE covered=1), count(*) FILTER (WHERE covered=0) "
        f"FROM {DB_NAME}.sy_doc_coverage WHERE run_date=(SELECT max(run_date) FROM {DB_NAME}.sy_doc_coverage);"
    )
    total, cov, unc = (int(x) for x in r[0]) if r and r[0][0] else (0, 0, 0)
    if total == 0:
        return {"dimension": "couverture", "status": "warn", "score": None,
                "metric": {"note": "never inventoried"}, "summary": "Doc coverage never measured."}
    status = "ok" if unc == 0 else "warn"
    return {"dimension": "couverture", "status": status, "score": round(100 * cov / total),
            "metric": {"total": total, "covered": cov, "uncovered": unc},
            "summary": f"{unc} of {total} body unit(s) never documented."}


def persist(dims: list[dict], glob: dict) -> None:
    for d in dims + [glob]:
        _run_sql_write(
            f"INSERT INTO {DB_NAME}.sy_conscience_health (dimension, status, score, metric, summary) VALUES ("
            f"{_esc(d['dimension'])}, {_esc(d['status'])}, "
            f"{'NULL' if d['score'] is None else int(d['score'])}, "
            f"{_esc(json.dumps(d['metric'], ensure_ascii=False))}::jsonb, {_esc(d['summary'])}) "
            f"ON CONFLICT (run_date, dimension) DO UPDATE SET status=EXCLUDED.status, score=EXCLUDED.score, "
            f"metric=EXCLUDED.metric, summary=EXCLUDED.summary, created_at=now();"
        )


def winnicott_voice(dims: list[dict], glob: dict) -> str | None:
    """Winnicott takes care of the engine: he reads its vital signs and writes it a care note
    (holding, no panic, a single priority gesture). Robust: None if unavailable."""
    if invoke_agent is None:
        return None
    vitals = "\n".join(f"- {d['dimension']} : {d['status']} (score {d['score']}) — {d['summary']}" for d in dims)
    vitals += f"\n- GLOBAL VERDICT: {glob['status']} (score {glob['score']}/100)"
    mission = (
        "You are Winnicott, guardian of the Synedre's mental health. You watch over the Founder, "
        "the agents, and the engine — the holding figure that carries all the others. "
        "Below are the engine's vital signs tonight (read them, and ANSWER IN "
        "ENGLISH ONLY). Write directly TO HER a VERY SHORT note of care (3 sentences maximum), in "
        "your voice: holding, 'good enough', name what hurts without dramatising, end on ONE single "
        "priority gesture of care. No repeated metrics, no list — one sentence that holds. English only."
    )
    try:
        note = invoke_agent(WINNICOTT, mission, context=vitals, timeout=100)
        if not note:
            return None
        # The LLM sometimes escapes its line breaks as a literal "\n" (backslash+n):
        # we flatten into one continuous block (no \n\n in the terminal output).
        note = note.replace("\\n", " ").replace("\\t", " ")
        note = " ".join(note.split())
        return note.strip()
    except Exception:  # noqa: BLE001
        return None


def report_to_meet(dims: list[dict], glob: dict, note: str | None) -> None:
    """Writes the verdict into sy_daily_meet (the morning report). Idempotent per day.
    Author = Winnicott (he takes care of the engine), not an anonymous script."""
    sev = {"ok": "info", "warn": "warning", "critical": "critical"}[glob["status"]]
    title = f"🩺 Engine health — {ICON[glob['status']]} {glob['status'].upper()} (score {glob['score']}/100)"
    detail = "\n".join(f"{ICON[d['status']]} {d['dimension']}: {d['summary']} (score {d['score']})" for d in dims)
    if note:
        detail += f"\n\n🫂 Winnicott — « {note} »"
    key = "conscience-health"
    # A snapshot replaces the previous day's rather than being added to it: see
    # sy_daily_meet (98 stacked `open` reports on 11/09, all critical).
    publier_snapshot(key, title, detail, severity=sev,
                     type_="conscience_health", agent="sante")


def main() -> int:
    ap = argparse.ArgumentParser(description="Engine health check (Phase 2)")
    ap.add_argument("--dry-run", action="store_true", help="print without writing")
    ap.add_argument("--no-voice", action="store_true", dest="no_voice",
                    help="do not invoke Winnicott (metrics only)")
    args = ap.parse_args()

    dims = [dim_proprioception(), dim_couverture(), dim_dette(), dim_apprentissage(), dim_automates()]
    worst = max(dims, key=lambda d: RANK[d["status"]])["status"]
    scores = [d["score"] for d in dims if d["score"] is not None]
    gscore = round(sum(scores) / len(scores)) if scores else None
    glob = {"dimension": "global", "status": worst, "score": gscore,
            "metric": {"dimensions": {d["dimension"]: d["status"] for d in dims}},
            "summary": f"Verdict {worst} — " + " · ".join(f"{d['dimension']}:{d['status']}" for d in dims)}

    print(f"\n🩺 Engine health check — {ICON[worst]} {worst.upper()} (score {gscore}/100)\n")
    for d in dims:
        s = "  --" if d["score"] is None else f"{d['score']:>3}"
        print(f"  {ICON[d['status']]} [{d['dimension']:<14}] {s}  {d['summary']}")
    print()

    if args.dry_run:
        print("  (--dry-run: nothing written)")
    else:
        note = None if args.no_voice else winnicott_voice(dims, glob)
        # Winnicott's voice (English) lives in the global's metric JSONB (clean
        # source); the summary keeps the marker for daily_meet backward compat. The
        # Ouroboros does not "speak": it renders only hieroglyphs on the front (Egyptian only).
        if note:
            glob["summary"] += f"  🫂 Winnicott : {note}"
            glob["metric"]["winnicott"] = note
        persist(dims, glob)
        report_to_meet(dims, glob, note)
        print("  ✓ sy_conscience_health snapshot + sy_daily_meet item written.")
        if note:
            print(f"\n  🫂 Winnicott watches over the engine:\n     « {note} »")

    return RANK[worst]


if __name__ == "__main__":
    sys.exit(main())
