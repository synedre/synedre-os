#!/usr/bin/env python3
"""
sy_extract.py — whitelist-driven release writer (the only copy path to OSS).

Reads publish-whitelist.txt (a `source -> dest` map), scrubs each source with
sy_scrub.scrub_text, and writes the dest into the OSS repo.

This is the ONLY entry point that copies monolith code into the public repo, and
it copies ONLY what the whitelist lists. scar #876 / #618: the whitelist is
read by the writer — never `cp -r` a directory then scrub it. Doctrine: scrub the
SOURCE, then write (ADR-0001).

Inputs (env vars):
  SY_SRC_ROOT   monolith root (private source of truth).
  SY_DEST_ROOT  OSS repo root (where scrubbed files land).
  SY_WHITELIST  optional, default <DEST_ROOT>/publish-whitelist.txt.
  SY_DENYLIST   optional, default <DEST_ROOT>/02_atlas/workers/release/sy_codename_denylist.txt.
  SY_PROSE      optional, default <DEST_ROOT>/02_atlas/workers/release/prose-en.json
                (curated FR->EN prose overlay; absent file = pass skipped).
  SY_PRIVATE_CONFIG  optional, default <DEST_ROOT>/02_atlas/workers/release/
                sy_private_config.json (YOUR monolith's path map / schema
                tokens / SQL messages; real file if present, else the shipped
                .example.json placeholder — same pattern as SY_DENYLIST).

Safety:
  - Every dest is resolved and asserted to live under DEST_ROOT (no path escape).
  - Missing source / non-text / parse error -> exit non-zero, never silent.
  - sy_leak_gate.py still checks the staged output afterwards (defense in depth).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from sy_scrub import (  # noqa: E402
    scrub_text, load_denylist, resolve_denylist_path, load_prose_pairs,
    load_private_config, resolve_private_config_path,
)


def parse_whitelist(text: str) -> list[tuple[str, str]]:
    """Parse `source -> dest` lines into a list of (src_rel, dst_rel).

    Lines starting with '#' and blank lines are ignored. Lines without '->' are
    treated as section headers and ignored. A malformed arrow raises ValueError.
    """
    pairs: list[tuple[str, str]] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "->" not in line:
            continue  # section header / prose comment without an arrow
        src_part, dst_part = line.split("->", 1)
        src, dst = src_part.strip(), dst_part.strip()
        if not src or not dst:
            raise ValueError(f"whitelist line {lineno}: malformed arrow -> {raw.strip()!r}")
        pairs.append((src, dst))
    return pairs


def write_release(
    src_root: Path,
    dest_root: Path,
    pairs: list[tuple[str, str]],
    denylist: list[str],
    prose_pairs: list | None = None,
    path_map: list | None = None,
    schema_tokens: list | None = None,
    sql_messages: list | None = None,
) -> list[tuple[str, str]]:
    """Scrub and write every whitelisted file. Returns the list of (src, dst)
    actually written. Raises on missing source, non-text, or dest escaping
    DEST_ROOT. *prose_pairs* is the curated FR->EN prose overlay
    (prose-en.json), applied as the last scrub transform. *path_map* /
    *schema_tokens* / *sql_messages* come from the private release config
    (T3.4) — None means scrub_text's own (empty, safe) defaults."""
    written: list[tuple[str, str]] = []
    dest_resolved = dest_root.resolve()
    for src_rel, dst_rel in pairs:
        src = (src_root / src_rel).resolve()
        if not src.is_file():
            raise FileNotFoundError(f"whitelist source missing: {src}")
        text = src.read_text(encoding="utf-8")  # non-text raises UnicodeDecodeError -> loud fail
        clean = scrub_text(
            text, denylist, prose_pairs=prose_pairs, path_map=path_map,
            schema_tokens=schema_tokens, sql_messages=sql_messages,
        )

        dst = (dest_root / dst_rel)
        dst_resolved = dst.resolve()
        try:
            dst_resolved.relative_to(dest_resolved)
        except ValueError as exc:
            raise ValueError(f"dest escapes DEST_ROOT: {dst}") from exc

        dst_resolved.parent.mkdir(parents=True, exist_ok=True)
        dst_resolved.write_text(clean, encoding="utf-8")
        written.append((src_rel, dst_rel))
    return written


def main() -> None:
    src_root = os.environ.get("SY_SRC_ROOT")
    dest_root = os.environ.get("SY_DEST_ROOT")
    if not src_root or not dest_root:
        print("SY_SRC_ROOT and SY_DEST_ROOT env vars are required", file=sys.stderr)
        sys.exit(2)

    src_root_p = Path(src_root).resolve()
    dest_root_p = Path(dest_root).resolve()
    wl_path = Path(os.environ.get("SY_WHITELIST", dest_root_p / "publish-whitelist.txt"))
    deny_path = Path(os.environ.get("SY_DENYLIST", _HERE / "sy_codename_denylist.txt"))

    if not wl_path.is_file():
        print(f"whitelist not found: {wl_path}", file=sys.stderr)
        sys.exit(2)

    pairs = parse_whitelist(wl_path.read_text(encoding="utf-8"))
    if not pairs:
        print(f"whitelist has no entries: {wl_path}", file=sys.stderr)
        sys.exit(2)

    deny = load_denylist(resolve_denylist_path(deny_path))
    prose_path = Path(os.environ.get("SY_PROSE", _HERE / "prose-en.json"))
    prose = load_prose_pairs(prose_path) if prose_path.is_file() else None

    private_path = Path(os.environ.get("SY_PRIVATE_CONFIG", _HERE / "sy_private_config.json"))
    private_cfg = load_private_config(resolve_private_config_path(private_path))

    try:
        written = write_release(
            src_root_p, dest_root_p, pairs, deny, prose,
            path_map=private_cfg["path_map"],
            schema_tokens=private_cfg["schema_tokens"],
            sql_messages=private_cfg["sql_messages"],
        )
    except (FileNotFoundError, UnicodeDecodeError, ValueError) as exc:
        print(f"sy_extract: ABORT — {exc}", file=sys.stderr)
        sys.exit(1)

    for src_rel, dst_rel in written:
        print(f"scrubbed  {src_rel}  ->  {dst_rel}")
    print(f"sy_extract: wrote {len(written)} file(s); run sy_leak_gate next.")


if __name__ == "__main__":
    main()
