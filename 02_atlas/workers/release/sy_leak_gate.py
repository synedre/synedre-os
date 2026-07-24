#!/usr/bin/env python3
"""
sy_leak_gate.py — leak gate over the staged OSS output (pure detector).

Runs after sy_extract has written the scrubbed files. It never transforms, only
reports. Fails (exit 1) on any residual leak; never silent. This is defense in
depth: the scrub (sy_scrub) and the gate are verified by separate camps in
test_scrub_mutation.py — a camp does not validate its own work.

Detection categories:
  secrets        emails, sk-* keys, Bearer tokens, conn-string passwords, inline
                 -p<secret>, high-entropy blobs. Reported as <SECRET> — the raw
                 value NEVER leaves this function (the gate must not itself leak).
  codename       tenant token from sy_codename_denylist.txt (substring, ci).
  header         @author / @copyright / @owner / @mort / @license Propriétaire.
  prefix         ac_ / ps_ac_ / ac- residuals (lookbehind protects mac_os).
  path           /home/ubuntu absolute path.
  schema         vaisseau_mere_ac / vaisseau_mere.
  private_ref    [[feedback_*]] brain links, CLAUDE.md (local-only here).
  lexicon        FR orchestration vocabulary (chantier/travail/tache/cicatrice/
                 conduite) — a wording defect, not a secret; the published tree
                 must be international (EN: jobsite/work_order/task/scar/
                 playbook). Off in the history audit.
  accents        any accented Latin letter — the mechanical backstop of the
                 prose-en.json overlay (sy_scrub transform 11): a FR comment
                 edited or added in the monolith stops matching its curated key,
                 survives the scrub in FR, and MUST fail here so curation is
                 forced, never skipped. Heuristic by design: accent-free FR
                 slips through (the lexicon category covers the 5 core words).
                 Off in the history audit — the pre-anglicization commits
                 legitimately carry FR prose.

Scope (the "what gets published" boundary) — scan_tracked_code, the CLI default:
  Scanned  — git-tracked CODE files only (core/, 02_atlas/hooks/,
             02_atlas/workers/sy_*.py, ...). Prose/config (.md / .txt / .gitignore)
             is NOT pattern-matched: a mention there is an EXPLANATION, not a leak
             (a README linking the public product Corbie; a CLA naming its legal
             beneficiary; a doc describing the ac_->sy_ rename) — review-validated.
  Excluded — gitignored files (git ls-files skips them); this pipeline's own source
             (02_atlas/workers/release/, which carries the detection strings by
             construction — 'vaisseau_mere_ac' lives in sy_scrub.py to be matched);
             test fixtures (00_ourobouros/tests/ — leaks by construction, validated
             by calling scan_text direct); live-state dirs (logs/tmp/backups/.chaos).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from sy_scrub import load_denylist, resolve_denylist_path  # noqa: E402


@dataclass
class Finding:
    category: str
    path: str
    line: int
    snippet: str


# Secret-shape patterns. Knowledge copied from the monolith's PII filter so the
# gate is self-contained (not coupled to the private monolith). The gate is a
# detector; it does not redact in place — a secret must FAIL and demand human
# action, never be silently rewritten into a publish.
_SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("api_key_anthropic", re.compile(r"sk-ant-[a-zA-Z0-9\-_]{20,}")),
    ("api_key_openai", re.compile(r"sk-(?:or-)?[a-zA-Z0-9\-_]{20,}", re.IGNORECASE)),
    ("bearer_token", re.compile(r"(?i)Bearer\s+[a-zA-Z0-9+/\-_]{20,}")),
    ("conn_string_password", re.compile(
        r"(?i)(postgresql|mysql|redis|mongodb|amqp)://[^:@\s]+:[^@\s]{6,}@")),
    # '-p<password>' is a STANDALONE flag (space/bol before), never a sub-token
    # of a long flag — so exclude a preceding '-' too, else '--porcelain' /
    # '--printf' leak through as a false db password.
    ("db_password_cli", re.compile(r"(?<![\w-])-p[^\s'\"\\,;]{8,}")),
    ("email", re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")),
    ("high_entropy_secret", re.compile(r'(?<=[="\'\s])([A-Za-z0-9+/]{40,}={0,2})(?=["\'\s]|$)')),
]

_HEADER_RE = re.compile(
    r"^[ \t]*[#\"']*[ \t]*@(?:author|copyright|owner|mort)\b", re.MULTILINE)
_LICENSE_PROP_RE = re.compile(
    r"^[ \t]*[#\"']*[ \t]*@license[ \t]+Propri", re.MULTILINE | re.IGNORECASE)
_PREFIX_RE = re.compile(r"(?<![A-Za-z0-9])(?:ps_)?ac[_-]")
# Override-able detection literals (mirror sy_scrub's override rationale: the
# defaults carry the monolith vocab, gate-excluded for the pipeline's own source,
# T3.4 moves to private config). Matched as plain substrings per scan so neutral
# fixtures can inject their own tokens without recompiling module regexes.
_DEFAULT_PATH_LITERALS = ("/home/ubuntu",)
# Mirror sy_scrub._DEFAULT_SCHEMA_TOKENS: the full mothership vocabulary, so the
# gate flags every variant even after a scrub regression (defense in depth).
_DEFAULT_SCHEMA_TOKENS = (
    "vaisseau_mere_ac", "vaisseau_mere", "mother_ship", "mothership",
)
_MEMORY_LINK_RE = re.compile(r"\[\[[a-zA-Z0-9_]+\]\]")
_CLAUDEMD_RE = re.compile(r"CLAUDE\.md", re.IGNORECASE)
# FR orchestration vocabulary (pre-rename, decided 2026-07-24: jobsite /
# work_order / task / scar / playbook). Not a secret — a WORDING defect: the
# published tree must be international. Boundaries mirror sy_scrub's lexicon
# pass (underscore is a boundary; letters incl. accented are not, so
# 'moustache' / 'detache' never fire). Disabled for the HISTORY audit
# (sy_publish_audit): the pre-rename vocabulary legitimately lives in the
# commits that performed the rename.
_LEXICON_RE = re.compile(
    r"(?<![A-Za-zÀ-ÿ0-9])(?:chantiers?|tra(?:vail|vaux)|t[aâ]ches?|"
    r"cicatrices?|conduites?)(?![A-Za-zÀ-ÿ0-9])",
    re.IGNORECASE,
)
# Accented Latin letters (Latin-1 letter ranges, × and ÷ excluded, + Œ/œ). The
# match widens to the whole word so the report reads 'sécurité', not 'é'. This
# is the fail-closed backstop of the prose-en.json overlay: unknown FR prose
# survives the scrub (inline prose cannot be dropped without dropping code) and
# must die HERE instead. Off in the history audit (accent_check=False).
_ACCENT_WORD_RE = re.compile(
    r"[A-Za-zÀ-ÖØ-öø-ÿŒœ]*[À-ÖØ-öø-ÿŒœ][A-Za-zÀ-ÖØ-öø-ÿŒœ]*"
)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def scan_text(
    text, denylist, *, path_literals=None, schema_tokens=None, lexicon_check=True,
    accent_check=True,
) -> list[Finding]:
    """Detect leaks in a single text blob. Secret matches are masked to
    <SECRET> in the snippet; the raw secret value never leaves this function.
    path_literals / schema_tokens override the monolith defaults (neutral fixtures
    inject their own so the test stays token-free in the public repo).
    lexicon_check=False drops the FR-vocabulary category — used by the history
    audit, where the pre-rename vocabulary legitimately appears.
    accent_check=False drops the accented-letter category likewise (the
    pre-anglicization commits legitimately carry FR prose)."""
    findings: list[Finding] = []

    def add(cat: str, m: re.Match, snippet: str) -> None:
        findings.append(Finding(cat, "", _line_of(text, m.start()), snippet))

    for cat, rx in _SECRET_PATTERNS:
        for m in rx.finditer(text):
            add(cat, m, "<SECRET>")  # never expose the value

    for tok in sorted(denylist, key=len, reverse=True):
        for m in re.finditer(re.escape(tok), text, re.IGNORECASE):
            add("codename", m, m.group(0))

    for m in _HEADER_RE.finditer(text):
        add("header", m, m.group(0).strip())
    for m in _LICENSE_PROP_RE.finditer(text):
        add("header", m, m.group(0).strip())
    for m in _PREFIX_RE.finditer(text):
        add("prefix", m, m.group(0))
    path_lits = path_literals if path_literals is not None else _DEFAULT_PATH_LITERALS
    for lit in path_lits:
        for m in re.finditer(re.escape(lit), text):
            add("path", m, m.group(0))
    schema_toks = schema_tokens if schema_tokens is not None else _DEFAULT_SCHEMA_TOKENS
    for tok in schema_toks:
        for m in re.finditer(re.escape(tok), text):
            add("schema", m, m.group(0))
    for m in _MEMORY_LINK_RE.finditer(text):
        add("private_ref", m, m.group(0))
    for m in _CLAUDEMD_RE.finditer(text):
        add("private_ref", m, m.group(0))
    if lexicon_check:
        for m in _LEXICON_RE.finditer(text):
            add("lexicon", m, m.group(0))
    if accent_check:
        for m in _ACCENT_WORD_RE.finditer(text):
            add("accents", m, m.group(0))

    return findings


# Dirs never scanned: VCS, this pipeline's own source (release/), test fixtures,
# and gitignored live state. See module docstring for the rationale.
_EXCLUDE_DIRS = {
    ".git", "node_modules", "release", "_run", "logs", "tmp", "backups", ".chaos",
}
_TESTS_DIR = ("00_ourobouros", "tests")
# File types the gate MATCHES: code only. Prose (.md / .txt) and config carry
# legitimate pattern mentions (a README referencing the public product Corbie,
# a doc describing the ac_->sy_ rename, a CLA naming the legal beneficiary) and
# are validated by human review, not pattern matching — see scan_tracked_code.
_CODE_EXTS = {
    ".py", ".sh", ".bash", ".sql", ".json", ".toml", ".yml", ".yaml",
    ".js", ".ts", ".vue", ".go", ".rs",
}


def scan_root(
    root: Path,
    denylist: list[str],
    exclude_tests: bool = True,
) -> list[Finding]:
    """Walk *root*, scanning every decodable text file. Non-text files are
    reported as a 'binary' finding — the gate fails on them, never skips silently."""
    findings: list[Finding] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(root).parts
        if any(part in _EXCLUDE_DIRS for part in rel_parts):
            continue
        if exclude_tests and _TESTS_DIR[0] in rel_parts and _TESTS_DIR[1] in rel_parts:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(Finding("binary", str(p), 0, "<non-text>"))
            continue
        for f in scan_text(text, denylist):
            f.path = str(p)
            findings.append(f)
    return findings


def scan_tracked_code(root, denylist, include_tests=False) -> list[Finding]:
    """Scan git-tracked CODE files only — the publish-relevant surface.

    Three filters, each closing a real false-positive class seen on this repo:
      git ls-files   — skips gitignored files (CLAUDE.md, .env*, .pytest_cache,
                       brain/) a filesystem walk would still read.
      _CODE_EXTS     — skips prose/config (.md, .txt, .gitignore) where a pattern
                       mention is an EXPLANATION, not a leak (a README linking the
                       public repo Corbie; a CLA naming its legal beneficiary; a
                       doc describing the ac_->sy_ rename). Code is where a
                       residual token is a real leak, so the gate matches there
                       and only there. Prose stays review-validated.
      _EXCLUDE_DIRS  — same boundary as scan_root (pipeline source, fixtures).

    Falls back to scan_root (filesystem walk) when *root* is not a git repo, so
    the integration test's tmp tree still works.
    """
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        capture_output=True, text=True,
    )
    if out.returncode != 0 or not out.stdout.strip():
        return scan_root(root, denylist, exclude_tests=not include_tests)
    findings: list[Finding] = []
    for rel in out.stdout.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        parts = tuple(Path(rel).parts)
        if any(part in _EXCLUDE_DIRS for part in parts):
            continue
        if not include_tests and _TESTS_DIR[0] in parts and _TESTS_DIR[1] in parts:
            continue
        if Path(rel).suffix.lower() not in _CODE_EXTS:
            continue
        p = root / rel
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(Finding("binary", str(p), 0, "<non-text>"))
            continue
        for f in scan_text(text, denylist):
            f.path = str(p)
            findings.append(f)
    return findings


def report(findings: list[Finding]) -> str:
    lines = [f"sy_leak_gate: {len(findings)} finding(s) — LEAK DETECTED"]
    for f in findings[:200]:
        lines.append(f"  [{f.category}] {f.path}:{f.line}  {f.snippet}")
    if len(findings) > 200:
        lines.append(f"  ... and {len(findings) - 200} more")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Leak gate over a staged OSS tree.")
    ap.add_argument("--root", required=True, help="OSS repo root to scan.")
    ap.add_argument("--denylist", default=str(_HERE / "sy_codename_denylist.txt"))
    ap.add_argument("--include-tests", action="store_true",
                    help="Also scan 00_ourobouros/tests/ (off by default).")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    deny = load_denylist(resolve_denylist_path(args.denylist))
    findings = scan_tracked_code(root, deny, include_tests=args.include_tests)

    if findings:
        print(report(findings), file=sys.stderr)
        sys.exit(1)
    print(f"sy_leak_gate: clean (scanned under {root})")
    sys.exit(0)


if __name__ == "__main__":
    main()
