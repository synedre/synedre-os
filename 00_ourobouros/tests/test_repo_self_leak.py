"""The repo must not leak the codenames its own pipeline exists to scrub.

Scar (2026-08-20): `publish-whitelist.txt` and `sy_scrub.py` named real tenant
codenames and a real customer domain — in their *explanatory comments*. The
class of bug: `sy_leak_gate.py` inspects the STAGED OUTPUT of an extraction,
so it never looks at the OSS repo's own hand-written files. Doctrine, prose and
examples written by hand are outside every existing gate. This test closes that
side: every git-tracked file of this repository is scanned against the real
(gitignored) denylist.

Public marks are exempt: this repository is published under the name Synedre and
links to CodeMyShop and Corbie on purpose. Anything else in the denylist is a
customer name, and a customer name in a public repo is a leak — comment or not.

Skips when only the `.example` denylist is available (external contributors):
there is nothing real to check for, and a false green is better than a false red
on a machine that cannot know the answer.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import sy_scrub

# Marks this repository publishes deliberately (README, CLA.md, TRADEMARK.md).
# Everything else in the denylist is a third party.
PUBLIC_MARKS = {"synedre", "codemyshop", "corbie", "alexandrecarette"}

# Binary-ish extensions: nothing to read, and decoding noise yields false hits.
_SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".woff",
                  ".woff2", ".zip", ".gz", ".tgz"}


def _tracked_files(repo_root: Path) -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-z"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [repo_root / p for p in out.split("\0") if p]


def test_no_third_party_codename_in_tracked_files(repo_root, release_dir, real_denylist):
    resolved = sy_scrub.resolve_denylist_path(release_dir / "sy_codename_denylist.txt")
    if resolved.suffix == ".example":
        pytest.skip("only the .example denylist is present — nothing real to check")

    tokens = [t for t in real_denylist if t and t.lower() not in PUBLIC_MARKS]
    assert tokens, "denylist holds nothing but public marks — check the file"

    this_file = Path(__file__).resolve()
    hits: list[str] = []
    for path in _tracked_files(repo_root):
        if path.suffix.lower() in _SKIP_SUFFIXES or path.resolve() == this_file:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict").lower()
        except (UnicodeDecodeError, FileNotFoundError, OSError):
            continue
        for token in tokens:
            if token.lower() in text:
                # Report the file and the token LENGTH, never the token itself:
                # a pytest failure lands in logs and transcripts.
                hits.append(
                    f"{path.relative_to(repo_root)} contains a denylisted "
                    f"token ({len(token)} chars)"
                )

    assert not hits, "third-party codename(s) in tracked files:\n  " + "\n  ".join(hits)
