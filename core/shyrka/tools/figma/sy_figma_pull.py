#!/usr/bin/env python3
"""
sy_figma_pull.py — Shyrka : rapatriement Figma → PNG + manifest.json (jobsite
#359 shyrka-figma-pull).

Pont Figma ↔ Claude Design SANS MCP. Le MCP Dev Mode de Figma tourne en
localhost (poste du designer) → inutilisable en autonome depuis la shyrka.
La REST API Figma (`api.figma.com`) est cloud, joignable avec un token → tourne
en cron shyrka, souverain, headless (cf
`${HOME}/`).

Ce que fait Shyrka :
  1. Lit la config source (tenant, file_key, frame_filter, page_filter) dans
     `sy_figma_source` (sy_hub, shyrka schema).
  2. Delta-gate sur `GET /files/:key` → `lastModified` vs `last_modified_seen`
     in DB. Unchanged + no --force → no-op (idempotent).
  3. Parcourt l'arbre document → pages (CANVAS) → frames (FRAME), retient les
     frames whose name starts with `frame_filter` (default `✓` = "ready"),
     filtered on `page_filter` if provided. Naming convention:
     `✓ /route Label libre` → le 1er token en `/…` = route de destination
     (e.g. `/shop`), the rest = label. Without `/…` → route None (frame flagged).
  4. `GET /images/:key?ids=…&format=png&scale=2` par lots (rate-limit friendly,
     retry+backoff on 429), downloads each PNG.
  5. Writes `automation/figma/<tenant>/<slug-frame>.png` + a
     `manifest.json` (index lu par Claude — frame_id/name/page/lastModified/
     hash sha256/png_path).
  6. UPDATE `sy_figma_source.last_modified_seen` (hors dry-run).

4 invariants (cf , applied here even
though this isn't an SEO engine — same robustness doctrine):
  HOMOGENEOUS (a single code path) · IDEMPOTENT (replace-not-append PNG+manifest,
  re-run with no change = same state) · MULTI-TENANT (config read from DB, zero
  hardcoded tenant — only the seed names <TENANT>) · deterministic (same inputs →
  same output, unless the Figma file actually changes).

Governance line: Shyrka STOPS at the pull. The PNG →
composant DS → classement (token / section DB / nouveau composant core) reste
a step driven by Claude, never automated.

Secret : le token vit dans `.env` (`FIGMA_CODEMYSHOP_TOKEN`), jamais en DB,
never committed, never logged in plaintext.

Usage :
    python3 synedre/sy_figma_pull.py --tenant <TENANT>
    python3 synedre/sy_figma_pull.py --all
    python3 synedre/sy_figma_pull.py --tenant <TENANT> --force
    python3 synedre/sy_figma_pull.py --tenant <TENANT> --dry-run

Cron (to be installed by the founder — see documentation/FIGMA_PULL_CRON.md):
    30 6 * * * cd ${SYNEDRE_ROOT} && python3 synedre/sy_figma_pull.py --all

"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from sy_entity_base import _run_sql_read, _run_sql_write, _esc, DB_NAME  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "automation" / "figma"
FIGMA_API = "https://api.figma.com/v1"
IMAGE_BATCH_SIZE = 50  # lots pour /images (rate-limit friendly)
MAX_RETRIES = 4
MAX_BACKOFF_S = 60  # hard ceiling: a Retry-After beyond this = signal of a block
                    # non-transitoire (paywall/quota), on ne sleepe jamais des heures


# ── Helpers ───────────────────────────────────────────────────────────────

def _slugify(s: str, max_len: int = 80) -> str:
    """ASCII kebab-case slug for the PNG filename (also strips the convention prefix)."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:max_len] or "frame"


def _parse_route(text: str) -> tuple[str | None, str]:
    """Splits the rest of the frame name (after the ✓ prefix) into (route, label).

    Convention: `✓ /route Label libre` → the first token starting with `/`
    est la route de destination (ex `/shop`), le reste est le label humain.
    No `/…` token → (None, cleaned text): frame "unrouted", to be flagged.
    """
    text = text.strip(" -_·—|")
    parts = text.split(None, 1)
    if parts and parts[0].startswith("/"):
        route = parts[0]
        label = parts[1].strip(" -_·—|") if len(parts) > 1 else route
        return route, (label or route)
    return None, text


def _log(msg: str) -> None:
    print(f"[figma-pull] {msg}", flush=True)


def _figma_token() -> str:
    """Reads the Figma token from .env — never logged, never stored in DB."""
    import os
    token = os.environ.get("FIGMA_CODEMYSHOP_TOKEN", "")
    if not token:
        raise SystemExit(
            "FIGMA_CODEMYSHOP_TOKEN missing from .env — add the Figma token "
            "(Settings > Personal access tokens) sous cette variable avant de relancer."
        )
    return token


def _figma_get(path: str, token: str, *, params: dict | None = None) -> dict:
    """GET REST Figma avec retry+backoff sur 429/5xx."""
    url = f"{FIGMA_API}{path}"
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, headers={"X-Figma-Token": token}, params=params, timeout=30)
        except requests.RequestException as e:  # noqa: BLE001
            last_err = e
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            wait = int(r.headers.get("Retry-After", 2 ** attempt))
            # Non-transient paywall / quota: Figma returns a 429 with a
            # Retry-After of several days + an upgrade link on free
            # accounts (plan-tier 'starter'). No point retrying/sleeping — fail
            # outright with an actionable message instead of freezing the process.
            if r.status_code == 429 and wait > MAX_BACKOFF_S:
                tier = r.headers.get("X-Figma-Plan-Tier", "?")
                upgrade = r.headers.get("X-Figma-Upgrade-Link", "")
                raise RuntimeError(
                    f"Figma API {path} → 429 paywall (plan '{tier}', Retry-After {wait}s). "
                    f"L'API REST /files+/images requiert un plan Figma payant. "
                    f"Upgrade: {upgrade}"
                )
            wait = min(wait, MAX_BACKOFF_S)
            _log(f"HTTP {r.status_code} sur {path} — retry dans {wait}s ({attempt}/{MAX_RETRIES})")
            time.sleep(wait)
            continue
        if r.status_code != 200:
            raise RuntimeError(f"Figma API {path} → HTTP {r.status_code}: {r.text[:300]}")
        return r.json()
    raise RuntimeError(f"Figma API {path} unreachable after {MAX_RETRIES} attempts ({last_err})")


# ── DB (sy_figma_source, sy_hub) ─────────────────────────────────────────

def load_sources(tenant: str | None) -> list[dict]:
    """Lit sy_figma_source (actives). Filtre sur tenant si fourni."""
    where = "active=1"
    if tenant:
        where += f" AND tenant={_esc(tenant)}"
    out = _run_sql_read(
        f"SELECT id, tenant, file_key, frame_filter, page_filter, last_modified_seen "
        f"FROM {DB_NAME}.sy_figma_source WHERE {where} ORDER BY tenant;"
    )
    sources = []
    for line in out.splitlines():
        if "\t" not in line:
            continue
        parts = line.split("\t")
        parts += [""] * (6 - len(parts))
        sid, ten, file_key, frame_filter, page_filter, last_seen = parts[:6]
        sources.append({
            "id": int(sid),
            "tenant": ten,
            "file_key": file_key,
            "frame_filter": frame_filter or "✓",
            "page_filter": page_filter or None,
            "last_modified_seen": last_seen or None,
        })
    return sources


def update_last_modified(source_id: int, last_modified: str) -> None:
    _run_sql_write(
        f"UPDATE {DB_NAME}.sy_figma_source "
        f"SET last_modified_seen={_esc(last_modified)}, date_upd=NOW() "
        f"WHERE id={source_id};"
    )


# ── Arbre Figma → frames retenues ────────────────────────────────────────

def collect_frames(node: dict, *, page_filter: str | None, frame_filter: str,
                    current_page: str | None = None) -> list[dict]:
    """Parcourt document → pages (CANVAS) → frames (FRAME). Retourne les frames
    whose name starts with `frame_filter`, filtered by `page_filter` if provided."""
    frames: list[dict] = []
    node_type = node.get("type")
    node_name = node.get("name", "")

    if node_type == "CANVAS":
        current_page = node_name
        if page_filter and current_page != page_filter:
            return frames  # page not targeted: ignore all its descendants

    if node_type == "FRAME" and node_name.startswith(frame_filter):
        route, label = _parse_route(node_name[len(frame_filter):])
        frames.append({
            "frame_id": node["id"],
            "name": label,
            "route": route,
            "page": current_page,
        })
        # une frame ne contient pas de sous-frame pertinente pour ce cas d'usage
        return frames

    for child in node.get("children", []) or []:
        frames.extend(collect_frames(
            child, page_filter=page_filter, frame_filter=frame_filter, current_page=current_page,
        ))
    return frames


# ── Image download (batched) ──────────────────────────────────────────────

def fetch_image_urls(file_key: str, token: str, node_ids: list[str]) -> dict[str, str]:
    """GET /images par lots de IMAGE_BATCH_SIZE ids. Retourne {node_id: url}."""
    url_map: dict[str, str] = {}
    for i in range(0, len(node_ids), IMAGE_BATCH_SIZE):
        batch = node_ids[i:i + IMAGE_BATCH_SIZE]
        data = _figma_get(
            f"/images/{file_key}", token,
            params={"ids": ",".join(batch), "format": "png", "scale": "2"},
        )
        if data.get("err"):
            raise RuntimeError(f"Figma /images erreur: {data['err']}")
        url_map.update(data.get("images") or {})
    return url_map


def download_png(url: str) -> bytes:
    r = requests.get(url, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"download PNG → HTTP {r.status_code}")
    return r.content


# ── Pull principal (par source) ──────────────────────────────────────────

def pull_source(source: dict, token: str, *, force: bool, dry_run: bool) -> str:
    """Traite une source Figma. Retourne un statut court pour le bilan."""
    tenant = source["tenant"]
    file_key = source["file_key"]

    if file_key.startswith("REPLACE_WITH_"):
        _log(f"{tenant}: file_key placeholder ({file_key}) — seed not finalized, skip.")
        return "skip-placeholder"

    file_meta = _figma_get(f"/files/{file_key}", token, params={"depth": 1})
    last_modified = file_meta.get("lastModified", "")

    if not force and source["last_modified_seen"] and last_modified == source["last_modified_seen"]:
        _log(f"{tenant}: unchanged (lastModified={last_modified}), skip.")
        return "unchanged"

    # depth=1 ne descend pas assez pour les frames → refetch complet de l'arbre.
    document = _figma_get(f"/files/{file_key}", token)
    frames = collect_frames(
        document.get("document", {}),
        page_filter=source["page_filter"],
        frame_filter=source["frame_filter"],
    )
    if not frames:
        _log(f"{tenant}: 0 frame '{source['frame_filter']}*' found "
             f"(page_filter={source['page_filter'] or '*'}).")
        if not dry_run:
            update_last_modified(source["id"], last_modified)
        return "0-frame"

    _log(f"{tenant}: {len(frames)} ready frame(s) found.")
    if dry_run:
        for f in frames:
            route = f["route"] or "⚠ SANS ROUTE (ajoute '/chemin' dans le nom)"
            _log(f"  [dry-run] {f['page']} · {route} — {f['name']} ({f['frame_id']})")
        return f"dry-run({len(frames)})"

    node_ids = [f["frame_id"] for f in frames]
    url_map = fetch_image_urls(file_key, token, node_ids)

    out_dir = OUT_ROOT / tenant
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries = []
    seen_slugs: dict[str, int] = {}
    for f in frames:
        png_url = url_map.get(f["frame_id"])
        if not png_url:
            _log(f"  ⚠ pas d'URL de rendu pour {f['name']} ({f['frame_id']}) — skip.")
            continue
        content = download_png(png_url)
        slug = _slugify(f["name"])
        # anti-collision si deux frames retenues slugifient pareil
        if slug in seen_slugs:
            seen_slugs[slug] += 1
            slug = f"{slug}-{seen_slugs[slug]}"
        else:
            seen_slugs[slug] = 0
        png_path = out_dir / f"{slug}.png"
        png_path.write_bytes(content)  # replace-not-append (idempotent)
        if not f["route"]:
            _log(f"  ⚠ {f['name']} : frame SANS ROUTE — ajoute '/chemin' dans le nom Figma.")
        manifest_entries.append({
            "frame_id": f["frame_id"],
            "name": f["name"],
            "route": f["route"],
            "page": f["page"],
            "lastModified": last_modified,
            "hash": hashlib.sha256(content).hexdigest(),
            "png_path": str(png_path.relative_to(ROOT)),
        })
        _log(f"  ✓ {f['route'] or '(sans route)'} — {f['name']} → {png_path.relative_to(ROOT)}")

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_entries, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    update_last_modified(source["id"], last_modified)
    return f"pulled({len(manifest_entries)})"


# ── CLI ───────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Shyrka — pulls 'ready' Figma frames into PNG + manifest.json.",
    )
    ap.add_argument("--tenant", default=None, help="codename tenant (ex: <TENANT>)")
    ap.add_argument("--all", action="store_true", help="tous les tenants actifs (sy_figma_source)")
    ap.add_argument("--force", action="store_true", help="ignore the delta-gate (re-pull even if unchanged)")
    ap.add_argument("--dry-run", action="store_true", help="list the selected frames, no writes")
    args = ap.parse_args()

    if not args.tenant and not args.all:
        ap.error("--tenant <codename> ou --all requis")

    token = _figma_token()
    sources = load_sources(None if args.all else args.tenant)
    if not sources:
        _log(f"aucune source active pour tenant={args.tenant!r}.")
        return 1

    bilan: dict[str, int] = {}
    exit_code = 0
    for source in sources:
        try:
            status = pull_source(source, token, force=args.force, dry_run=args.dry_run)
        except Exception as e:  # noqa: BLE001
            _log(f"{source['tenant']}: ERREUR {e}")
            status = "erreur"
            exit_code = 1
        key = status.split("(")[0]
        bilan[key] = bilan.get(key, 0) + 1

    _log("bilan : " + ", ".join(f"{k}={v}" for k, v in sorted(bilan.items())))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
