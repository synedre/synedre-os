#!/usr/bin/env python3
"""GOLDEN contract of the entity-layer output format (docker psql -tA -F\\t).
Jobsite #488 task 1.

ANY alternative implementation of _run_sql_read (e.g. psycopg2 pool, task 2) MUST
produce BYTE-IDENTICAL output to these references on this battery of types. This is
the proof against silent corruption (scar _esc backslash #1027: an installed
safeguard is not a safeguard that bites).

Subtleties captured (2026-07-18, reference docker-psql path):
  - bool → 't'/'f' (not 'True'/'False')
  - numeric keeps its scale: 100.00::numeric(10,2) → '100.00', 5 → '5.00'
  - timestamptz → '…+02' (offset WITHOUT ':00') — DEPENDS on the session timezone:
    the psycopg2 pool MUST set the same TimeZone as the container, otherwise drift.
  - NULL → '' ; NULL in the last column → trailing '\\t' PRESERVED (rstrip('\\n') only)
  - a '\\t' INSIDE a text value is indistinguishable from the separator (accepted -tA limit)
  - jsonb rendered with spaces: '{"a": 1, "b": [2, 3]}'
  - array → '{1,2,3}' / '{x,y}'
"""
from __future__ import annotations

# (name, sql, expected) — expected = exact output of _run_sql_read (docker psql -tA -F\t).
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
    """Runs each contract query via `runner(sql)->str` and compares to the golden.
    Returns (ok, [(name, expected, got), ...]) — empty mismatches = perfect parity."""
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
        print(f"✅ golden contract verified — {len(CONTRACT)} byte-identical cases (docker-psql)")
    else:
        print(f"❌ {len(mism)} drift(s):")
        for name, exp, got in mism:
            print(f"  {name}: expected {exp!r} — got {got!r}")
    sys.exit(0 if ok else 1)
