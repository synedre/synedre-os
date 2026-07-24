#!/usr/bin/env python3
"""
sy_publish_audit.py — 0-leak audit after commit (the last gate before publish).

Runs over BOTH the working tree and the full git history. A leak that was
committed and then deleted still lives in `git log -p`; this audit catches it.
Publishing itself stays a human decision (never autonomous) — this audit is the
mechanical backstop that backs that decision.

Same detection as sy_leak_gate (shared via import), same exclusions: the
pipeline's own source (02_atlas/workers/release/) and the test fixtures
(00_ourobouros/tests/) carry detection strings / mutants by construction and are
validated separately; live-state dirs are gitignored. Secrets are masked to
<SECRET> in every report.

Exit 1 on any finding, 0 when clean.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from sy_leak_gate import (  # noqa: E402
    scan_root, scan_tracked_code, scan_text, report,
    load_denylist, _EXCLUDE_DIRS, _TESTS_DIR, _CODE_EXTS,
)
from sy_scrub import resolve_denylist_path  # noqa: E402


def _git(root: Path, *args: str) -> str:
    res = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res.stdout


def _excluded(rel_parts: tuple[str, ...]) -> bool:
    if any(part in _EXCLUDE_DIRS for part in rel_parts):
        return True
    if _TESTS_DIR[0] in rel_parts and _TESTS_DIR[1] in rel_parts:
        return True
    return False


def tracked_files_to_audit(root: Path) -> list[str]:
    """git-tracked files minus the excluded dirs (same boundary as the gate)."""
    out: list[str] = []
    for line in _git(root, "ls-files").splitlines():
        rel = line.strip()
        if not rel or _excluded(tuple(Path(rel).parts)):
            continue
        # prose/config (.md, .txt, .gitignore) carry legitimate pattern mentions
        # — audited by review, not pattern matching (see scan_tracked_code). The
        # history scan follows the same code-only surface as the working tree.
        if Path(rel).suffix.lower() not in _CODE_EXTS:
            continue
        out.append(rel)
    return out


def audit_history(root: Path, denylist: list[str]) -> list:
    """Scan the FILE-CONTENT diffs of every auditable tracked file across all
    history — never the commit metadata.

    Only +/- content lines are scanned; commit headers, the author email, and the
    commit message are dropped. Rationale: a committer's email is a public
    identity (immutable, like a CLA beneficiary — and this repo's author email
    carries a codename), and a commit message legitimately NAMES a token to
    explain a rename. Both are noise here. The real signal is a token that ever
    lived inside a FILE — a leak deleted from the working tree still survives in
    that file's diff history, and that is exactly what this audit catches.
    """
    files = tracked_files_to_audit(root)
    if not files:
        return []
    diff = _git(root, "log", "-p", "--all", "--no-color", "--", *files)
    # ln[1:] strips the +/- diff marker: it is diff SYNTAX, not content — kept,
    # a deleted line starting with 'process...' reads '-process...' and false-
    # positives the '-p<password>' secret pattern.
    content = "\n".join(
        ln[1:] for ln in diff.splitlines()
        if ln[:1] in "+-" and ln[:3] not in ("+++", "---")
    )
    findings = []
    # lexicon_check + accent_check off: the FR->EN vocabulary rename and the
    # prose anglicization live in history by construction (the commits that
    # performed them). The WORKING TREE must be lexicon- and accent-clean —
    # that is the tree scan's job, not history's.
    for f in scan_text(content, denylist, lexicon_check=False, accent_check=False):
        f.path = f"(git log content) {f.path or ':'}"
        findings.append(f)
    return findings


def main() -> None:
    ap = argparse.ArgumentParser(description="0-leak audit (tree + git history).")
    ap.add_argument("--root", required=True, help="OSS repo root to audit.")
    ap.add_argument("--denylist", default=str(_HERE / "sy_codename_denylist.txt"))
    ap.add_argument("--no-tree", action="store_true", help="Skip the working-tree scan.")
    ap.add_argument("--no-history", action="store_true", help="Skip the git-history scan.")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    deny = load_denylist(resolve_denylist_path(args.denylist))

    findings = []
    if not args.no_tree:
        findings += scan_tracked_code(root, deny)
    if not args.no_history:
        findings += audit_history(root, deny)

    if findings:
        print(report(findings), file=sys.stderr)
        sys.exit(1)
    print(f"sy_publish_audit: clean (tree + git history under {root})")
    sys.exit(0)


if __name__ == "__main__":
    main()
