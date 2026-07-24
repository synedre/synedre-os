#!/usr/bin/env python3
"""Contrat GOLDEN du format de sortie de la couche entité (docker psql -tA -F\\t).
Jobsite #488 task 1.

TOUTE implémentation alternative de _run_sql_read (ex pool psycopg2, task 2) DOIT
produire un output BYTE-IDENTIQUE à ces références sur cette batterie de types. C'est
la preuve contre la corruption silencieuse (scar _esc antislash #1027 : un
garde-fou installé n'est pas un garde-fou qui mord).

Subtilités capturées (2026-07-18, chemin docker-psql de référence) :
  - bool → 't'/'f' (pas 'True'/'False')
  - numeric garde l'échelle : 100.00::numeric(10,2) → '100.00', 5 → '5.00'
  - timestamptz → '…+02' (offset SANS ':00') — DÉPEND du timezone de session :
    le pool psycopg2 DOIT poser le même TimeZone que le container, sinon drift.
  - NULL → '' ; NULL en dernière colonne → '\\t' trailing PRÉSERVÉ (rstrip('\\n') only)
  - un '\\t' DANS une valeur texte est indistinct du séparateur (limite -tA assumée)
  - jsonb rendu avec espaces : '{"a": 1, "b": [2, 3]}'
  - array → '{1,2,3}' / '{x,y}'
"""
from __future__ import annotations

# (name, sql, expected) — expected = sortie exacte de _run_sql_read (docker psql -tA -F\t).
CONTRACT: list[tuple[str, str, str]] = [
    ("bool",        "SELECT true, false",                                   "t\tf"),
    ("int",         "SELECT 42, -7",                                        "42\t-7"),
    ("numeric",     "SELECT 3.14::numeric, 100.00::numeric(10,2), 5::numeric(10,2)",
                                                                            "3.14\t100.00\t5.00"),
    ("float",       "SELECT 3.5::float8, 0.1::float8",                      "3.5\t0.1"),
    ("timestamptz", "SELECT '2026-07-18 14:30:00.123456+02'::timestamptz",  "2026-07-18 14:30:00.123456+02"),
    ("timestamp",   "SELECT '2026-07-18 14:30:00'::timestamp",              "2026-07-18 14:30:00"),
    ("date",        "SELECT '2026-07-18'::date",                            "2026-07-18"),
    ("null_last",   "SELECT 1, NULL::text",                                 "1\t"),
    ("null_mid",    "SELECT 1, NULL::text, 3",                              "1\t\t3"),
    ("text_tab",    "SELECT E'a\\tb'",                                      "a\tb"),
    ("empty_str",   "SELECT ''::text, 'x'",                                 "\tx"),
    ("jsonb",       'SELECT \'{"a":1,"b":[2,3]}\'::jsonb',                  '{"a": 1, "b": [2, 3]}'),
    ("array_int",   "SELECT ARRAY[1,2,3]",                                  "{1,2,3}"),
    ("array_txt",   "SELECT ARRAY['x','y']",                                "{x,y}"),
]


def verify_parity(runner) -> tuple[bool, list[tuple[str, str, str]]]:
    """Exécute chaque requête du contrat via `runner(sql)->str` et compare au golden.
    Retourne (ok, [(name, expected, got), ...]) — mismatches vides = parité parfaite."""
    mismatches: list[tuple[str, str, str]] = []
    for name, sql, expected in CONTRACT:
        try:
            got = runner(sql)
        except Exception as e:  # noqa: BLE001
            mismatches.append((name, expected, f"ERR {e}"))
            continue
        if got != expected:
            mismatches.append((name, expected, got))
    return (not mismatches, mismatches)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))
    from synedre.sy_entities.base import _run_sql_read
    ok, mism = verify_parity(_run_sql_read)
    if ok:
        print(f"✅ contrat golden vérifié — {len(CONTRACT)} cas byte-identiques (docker-psql)")
    else:
        print(f"❌ {len(mism)} drift(s) :")
        for name, exp, got in mism:
            print(f"  {name}: attendu {exp!r} — obtenu {got!r}")
    sys.exit(0 if ok else 1)
