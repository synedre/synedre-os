"""
sy_agent_runner — agentic execution abstraction.


ONE `AgentRunner`, N backends, routed per task, all normalized by a common
layer: events → `sy_agent_event` (cockpit), cost → `sy_cost_run` × `sy_llm_pricing`,
hooks. This stage lays down the CONTRACT + a first `ClaudeCliRunner` backend that wraps
the existing node-pty spawn (`bin/atlas-spawn-claude.mjs`) WITHOUT changing the behavior
of `sy_task_worker` (the worker is not edited; a parallel extension point is added).

Upcoming backends: `SynedreRunner` (in-house loop, direct API, multi-brand),
`ClaudeApiRunner` (Claude Agent SDK).

Usage :
    from sy_agent_runner import get_runner, record_cost
    r = get_runner("claude-cli")
    res = r.run("Reply: OK", id_jobsite=203, agent_codename="backend")
    record_cost(res, id_task_run)   # → sy_cost_run (provider=anthropic)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE_BIN = "/usr/bin/node"
SPAWNER = str(ROOT / "bin" / "atlas-spawn-claude.mjs")


# ───────────────────────── Normalized DTO ─────────────────────────

@dataclass
class RunResult:
    """Normalized result of an agentic run, whatever the backend/brand."""
    output: str = ""
    provider: str = ""
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_cached: int = 0
    cost_usd: float | None = None     # authoritative if provided by the backend (Anthropic CLI)
    events_count: int = 0
    exit_code: int = 0
    success: bool = False
    stream_log: str | None = None
    # ── Continuity (failover routing) ──
    limit_hit: bool = False           # Claude plan exhausted / rate-limit detected
    ran_on_fallback: bool = False     # this result comes from a fallback brand
    fallback_reason: str = ""         # e.g. 'claude-forfait', detected signal


# ───────────────────────── Contrat ─────────────────────────

class AgentRunner(ABC):
    """Common interface. Every backend returns a RunResult and goes through the
    common layer (events sy_agent_event + cost sy_cost_run)."""

    name: str = "abstract"
    provider: str = ""

    @abstractmethod
    def run(self, prompt: str, *, system: str | None = None, model: str | None = None,
            perimeter: list[str] | None = None, id_jobsite: int | None = None,
            agent_codename: str = "orchestrator", allowed_tools: str | None = None,
            timeout_sec: int = 900) -> RunResult:
        ...


# ───────────────────────── Helpers communs ─────────────────────────

def _max_event_seq(id_jobsite: int) -> int:
    """MAX(event_seq) of the jobsite (0 if none/error) — monotonic seq (cf. cockpit)."""
    try:
        r = subprocess.run(
            ["docker", "exec", "-i", "sy_postgres", "psql", "-U", "claude_pg",
             "-d", "sy_hub", "-tA", "-c",
             "SELECT COALESCE(MAX(event_seq),0) FROM shyrka.sy_agent_event "
             f"WHERE source_type='jobsite' AND source_id={int(id_jobsite)};"],
            capture_output=True, text=True, timeout=10,
        )
        return int((r.stdout or "0").strip() or 0) if r.returncode == 0 else 0
    except Exception:
        return 0


import re  # noqa: E402

# Claude limit signals (subscription plan OR API rate-limit). Detected
# ONLY in an error context (see _is_limit_signal) to avoid false positives
# on normal text that merely mentions "rate limit".
_LIMIT_PATTERNS = re.compile(
    r"usage limit|rate.?limit|limit reached|too many requests|forfait|"
    r"quota|overloaded|insufficient.?quota|429|capacity",
    re.IGNORECASE,
)


def _is_limit_signal(ev: dict) -> str | None:
    """If the event signals a Claude cap/plan/rate-limit, returns a
    short reason; otherwise None. An ERROR CONTEXT is required (type=error, or
    result with is_error / an error subtype) so it does not trigger on
    texte assistant ordinaire."""
    typ = ev.get("type")
    in_error = (
        typ == "error"
        or bool(ev.get("is_error"))
        or (typ == "result" and str(ev.get("subtype") or "").startswith("error"))
    )
    if not in_error:
        return None
    blob = " ".join(str(ev.get(k) or "") for k in ("error", "result", "subtype", "message"))
    m = _LIMIT_PATTERNS.search(blob)
    return m.group(0).lower() if m else None


def _extract_text(ev: dict) -> str | None:
    if ev.get("type") != "assistant":
        return None
    out = []
    for c in (ev.get("message", {}).get("content") or []):
        if isinstance(c, dict) and c.get("type") == "text" and c.get("text"):
            out.append(c["text"])
    return "".join(out) if out else None


def _esc(s: str) -> str:
    return str(s).replace("'", "''")


def _sql(sql: str, read: bool = False) -> str | None:
    """Runs a SQL statement on sy_hub via docker. read=True → returns stdout (-tA),
    otherwise None. Non-blocking (returns None on error)."""
    # SQL via STDIN, never via argv: `-c <sql>` makes the command line carry the
    # whole payload and blows past ARG_MAX on large content (GLM events were once
    # silently lost this way). stdin has no such limit.
    args = ["docker", "exec", "-i", "sy_postgres", "psql", "-U", "claude_pg", "-d", "sy_hub"]
    args += (["-tA", "-F", "|"] if read else ["-v", "ON_ERROR_STOP=1"])
    try:
        r = subprocess.run(args, input=sql, capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            print(f"⚠️  _sql: {r.stderr.strip()}", file=sys.stderr)
            return None
        return r.stdout.strip() if read else ""
    except Exception as e:  # noqa: BLE001
        print(f"⚠️  _sql no-op: {e}", file=sys.stderr)
        return None


def _flag_replay_if_high_altitude(id_task_run: int, reason: str) -> bool:
    """Altitude policy: if the task behind this run is HIGH-ALTITUDE (tier
    heavy OR priority P0/P1), flag it replay_on_reset=1. It fell back to a
    fallback brand; it will be replayed on Claude (premium) at plan reset
    (sy_runner_replay automation). Low-altitude → keep the fallback result
    (good enough quality). Returns True if flagged."""
    row = _sql(
        "SELECT t.id_task, COALESCE(t.priority,''), COALESCE(t.estimated_tokens,0) "
        "FROM shyrka.sy_task_run r "
        "JOIN shyrka.sy_jobsite_task t "
        "  ON r.codename LIKE 'jobsite-task-' || t.id_task || '-%' "
        f"WHERE r.id_task_run = {int(id_task_run)} LIMIT 1",
        read=True,
    )
    if not row:
        return False
    id_task_s, prio, est_s = row.split("|")
    from synedre.sy_entities.jobsite import TacheEntity
    tier = TacheEntity.recommend_tier_for(int(est_s or 0) or None, prio or None)
    if tier != "heavy" and prio not in ("P0", "P1"):
        return False
    _sql(
        "UPDATE shyrka.sy_jobsite_task "
        f"SET replay_on_reset=1, last_fallback_reason='{_esc(reason)}' "
        f"WHERE id_task={int(id_task_s)} AND replayed_at IS NULL"
    )
    print(f"🔖 task {id_task_s} flagged replay_on_reset (altitude {tier}/{prio})",
          file=sys.stderr)
    return True


def record_cost(result: RunResult, id_task_run: int) -> bool:
    """Persists the cost of a run into sy_cost_run (provider dimension).

    Cost = authoritative `result.cost_usd` when provided (Anthropic CLI = total_cost_usd),
    otherwise computed via sy_llm_cost.compute_cost (tokens × sy_llm_pricing) — a
    bridge that makes API/OpenAI-style backends costable. Non-blocking.
    """
    try:
        cost = result.cost_usd
        if cost is None:
            from synedre.sy_llm_cost import compute_cost
            cost = compute_cost(result.provider, result.model,
                                result.tokens_in, result.tokens_out, result.tokens_cached)
        cost = float(cost or 0.0)
        rof = 1 if result.ran_on_fallback else 0
        fbr = f"'{_esc(result.fallback_reason)}'" if result.fallback_reason else "NULL"
        # Cache tokens are PERSISTED: omitting them under-counted real
        # consumption by a factor of ~20 on GLM — on Z.ai, cache_read tokens
        # count against the quota, unlike the Anthropic plan where the gap
        # goes unnoticed.
        cached = int(getattr(result, "tokens_cached", 0) or 0)
        sql = (
            "INSERT INTO shyrka.sy_cost_run "
            "(id_task_run, provider, model, input_tokens, output_tokens, cost_usd, "
            "ran_on_fallback, fallback_reason, cache_read_tokens) "
            f"VALUES ({int(id_task_run)}, '{_esc(result.provider)}', '{_esc(result.model)}', "
            f"{int(result.tokens_in)}, {int(result.tokens_out)}, {cost}, {rof}, {fbr}, "
            f"{cached});"
        )
        r = subprocess.run(
            ["docker", "exec", "-i", "sy_postgres", "psql", "-U", "claude_pg",
             "-d", "sy_hub", "-v", "ON_ERROR_STOP=1"],
            input=sql, capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            print(f"⚠️  record_cost failed: {r.stderr.strip()}", file=sys.stderr)
            return False
        # Altitude policy: high-altitude task that fell back → flag premium replay.
        if result.ran_on_fallback:
            _flag_replay_if_high_altitude(id_task_run, result.fallback_reason or "claude-forfait")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"⚠️  record_cost no-op: {e}", file=sys.stderr)
        return False


# ───────────────────────── Backend 1 : Claude CLI (node-pty) ─────────────────────────

class ClaudeCliRunner(AgentRunner):
    """Wraps `bin/atlas-spawn-claude.mjs` (node-pty, stream-json) — the ONLY spawner
    headless allowed. Mirror of
    `sy_task_worker._build_wrapper_argv` + drain, SANS toucher au worker.
    """

    name = "claude-cli"
    provider = "anthropic"

    def run(self, prompt: str, *, system: str | None = None, model: str | None = None,
            perimeter: list[str] | None = None, id_jobsite: int | None = None,
            agent_codename: str = "orchestrator", allowed_tools: str | None = None,
            timeout_sec: int = 900) -> RunResult:
        model = model or "sonnet"
        res = RunResult(provider=self.provider, model=model)

        # Prompt/system files (reuses the worker convention).
        tag = f"runner-{abs(hash((prompt, id_jobsite or 0))) % 10_000_000}"
        prompt_file = Path(f"/tmp/{tag}-prompt.txt")
        system_file = Path(f"/tmp/{tag}-system.txt")
        stream_log = Path(f"/tmp/{tag}-stream.jsonl")
        res.stream_log = str(stream_log)
        try:
            prompt_file.write_text(prompt, encoding="utf-8")
            system_file.write_text(system or "", encoding="utf-8")
        except Exception as e:
            print(f"⚠️  runner prep: {e}", file=sys.stderr)
            return res

        add_dir = str(ROOT)
        if perimeter and isinstance(perimeter, list) and perimeter:
            add_dir = str(ROOT / perimeter[0])

        argv = [
            NODE_BIN, SPAWNER,
            "--id", "0",
            "--prompt-file", str(prompt_file),
            "--system-prompt-file", str(system_file),
            "--model", model,
            "--stream-log", str(stream_log),
            "--add-dir", add_dir,
            "--timeout-sec", str(int(timeout_sec)),
        ]
        # ReAct turn cap (mirror of sy_task_worker._task_max_turns, knob
        # SY_TASK_MAX_TURNS default 80). Inlined to avoid a circular dependency
        # (sy_task_worker imports sy_agent_runner via _run_via_router). 0 = unlimited.
        try:
            _mt = max(0, int(os.environ.get("SY_TASK_MAX_TURNS", "80")))
        except (TypeError, ValueError):
            _mt = 80
        if _mt > 0:
            argv += ["--max-turns", str(_mt)]
        # Context scoping key — mirror of sy_task_worker._build_wrapper_argv:
        # this runner is the other spawn path, it must set the same key or the
        # scoping would be inconsistent depending on the caller. Empty ⇒ no
        # flag ⇒ full context.
        if (agent_codename or "").strip():
            argv += ["--agent-codename", agent_codename.strip()]

        if allowed_tools:
            argv += ["--allowed-tools", allowed_tools]

        # Cockpit persistence (reuses persist_agent_event when a jobsite is set).
        persist_fn = None
        if id_jobsite is not None:
            try:
                from synedre.sy_event_persistor import persist_agent_event as persist_fn  # noqa: E402
            except Exception:
                persist_fn = None
        seq = _max_event_seq(id_jobsite) if (persist_fn and id_jobsite is not None) else 0

        text_parts: list[str] = []
        try:
            proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True, cwd=str(ROOT))
            assert proc.stdout is not None
            for line in proc.stdout:
                stripped = line.rstrip("\n")
                if not stripped:
                    continue
                try:
                    ev = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                res.events_count += 1
                # Claude plan/rate-limit ceiling detection → mark for failover.
                if not res.limit_hit:
                    sig = _is_limit_signal(ev)
                    if sig:
                        res.limit_hit = True
                        res.fallback_reason = f"claude-forfait:{sig}"
                if persist_fn is not None and id_jobsite is not None:
                    try:
                        seq += 1
                        persist_fn(source_type="jobsite", source_id=int(id_jobsite),
                                   agent_codename=agent_codename, seq=seq, event=ev)
                    except Exception as e:
                        print(f"⚠️  persist seq={seq}: {e}", file=sys.stderr)
                # final result event: authoritative cost + tokens
                if ev.get("type") == "result":
                    cost = ev.get("total_cost_usd")
                    if cost is not None:
                        res.cost_usd = float(cost)
                    usage = ev.get("usage") or {}
                    res.tokens_in = int(usage.get("input_tokens") or 0)
                    res.tokens_out = int(usage.get("output_tokens") or 0)
                    res.tokens_cached = int((usage.get("cache_read_input_tokens") or 0)
                                            + (usage.get("cache_creation_input_tokens") or 0))
                    rtext = ev.get("result")
                    if rtext:
                        text_parts.append(str(rtext))
                t = _extract_text(ev)
                if t:
                    text_parts.append(t)
            res.exit_code = proc.wait()
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  ClaudeCliRunner spawn: {e}", file=sys.stderr)
            res.exit_code = 1
            return res

        res.output = (text_parts[-1] if text_parts else "").strip() or "\n".join(text_parts).strip()
        res.success = res.exit_code == 0 and bool(res.output)
        return res


# ───────────────────────── Factory (squelette routeur) ─────────────────────────

_RUNNERS: dict[str, type[AgentRunner]] = {
    "claude-cli": ClaudeCliRunner,
}


def get_runner(name: str) -> AgentRunner:
    """Returns an instance of the named backend. The router will later plug in
    the per-task/brand choice. For now: 'claude-cli'."""
    cls = _RUNNERS.get(name)
    if cls is None:
        raise ValueError(f"runner inconnu: {name!r} (dispo: {sorted(_RUNNERS)})")
    return cls()


# ───────────────────────── Continuity: Claude plan failover ─────────────────────────

# Default fallback brand(s) when the Claude plan is exhausted. MUST be
# pay-as-you-go API runners (outside the subscription plan) — falling back to
# Claude (Sonnet…) does not help: same plan. Override: SY_RUNNER_FALLBACK_CHAIN.
DEFAULT_FALLBACK_CHAIN = ["synedre-mistral"]


def _fallback_chain() -> list[str]:
    env = os.environ.get("SY_RUNNER_FALLBACK_CHAIN")
    if env:
        return [s.strip() for s in env.split(",") if s.strip()]
    return list(DEFAULT_FALLBACK_CHAIN)


def run_with_failover(prompt: str, *, primary: str = "claude-cli",
                      fallback_chain: list[str] | None = None, **kw) -> RunResult:
    """Runs `primary`; if the Claude plan is exhausted (res.limit_hit), falls back
    to the 1st AVAILABLE, non-capped fallback brand. We NEVER block:
    continuity comes first. The fallback result is traced (ran_on_fallback +
    fallback_reason) for premium replay at reset. Altitude policy
    (P0/judgment flagged replay_on_reset) handled by the caller via the field.

    Guardrails: a fallback with provider 'anthropic' is skipped (same plan); if
    a fallback is itself limited the chain continues; a NON-limit failure is
    not masked (the result is returned as-is, escalate-on-fail handles it)."""
    # Registers the API runners (synedre-mistral, …) in the factory.
    try:
        import synedre.sy_runner_synedre  # noqa: F401
    except Exception as e:  # noqa: BLE001
        print(f"⚠️  runners API indispo: {e}", file=sys.stderr)

    try:
        primary_runner = get_runner(primary)
    except ValueError as e:
        print(f"⚠️  runner primaire {primary!r} inconnu ({e}) → claude-cli", file=sys.stderr)
        primary_runner = get_runner("claude-cli")
    res = primary_runner.run(prompt, **kw)
    if not res.limit_hit:
        return res

    reason = res.fallback_reason or "claude-forfait"
    print(f"⛔ Claude plan exhausted ({reason}) → failover", file=sys.stderr)
    for name in (fallback_chain if fallback_chain is not None else _fallback_chain()):
        try:
            fb = get_runner(name)
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  fallback {name!r} unavailable: {e}", file=sys.stderr)
            continue
        if getattr(fb, "provider", "") == "anthropic":
            print(f"⏭️  {name!r} on the Claude plan — skipped", file=sys.stderr)
            continue
        # The primary's model is specific to ITS brand: it is not forced onto a
        # fallback from another brand (let the adapter pick its default).
        fb_kw = {**kw, "model": None}
        fbres = fb.run(prompt, **fb_kw)
        fbres.ran_on_fallback = True
        fbres.fallback_reason = reason
        if fbres.limit_hit:
            continue  # fallback itself capped → next link in the chain
        print(f"✅ failover to {fbres.provider}/{fbres.model} "
              f"(success={fbres.success})", file=sys.stderr)
        return fbres

    # Chain exhausted: return the primary (limited) result, the caller decides.
    print("⚠️  fallback chain exhausted — no fallback available", file=sys.stderr)
    return res


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        print("runners:", sorted(_RUNNERS))
        return 0
    name = argv[0]
    if name == "failover":
        prompt = " ".join(argv[1:]) or "Reply only: OK"
        res = run_with_failover(prompt)
    else:
        prompt = " ".join(argv[1:]) or "Reply only: OK"
        res = get_runner(name).run(prompt)
    from dataclasses import asdict
    print(json.dumps(asdict(res), ensure_ascii=False, indent=2))
    return 0 if res.success else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
