<!-- AUTO-GENERATED from core/shyrka/bootstrap.sql by sy_db_schema_doc.py -- DO NOT EDIT. Regenerate after bootstrap.sql changes. -->

# Database schema — `shyrka`

The Synedre OS orchestrator core schema. DDL-only (no data), generated from `core/shyrka/bootstrap.sql` over a 69-table whitelist + 8 engine functions. This page is reference (Layer 2 of the doc-doctrine, ADR-0001) — for *why* a table exists, see its COMMENT and the ADRs; for *how* to use it, see the in-code docstrings (Layer 1).

_Legend: 36/69 tables and 86 columns carry a COMMENT (the engine's doctrine, kept verbatim). `NOT NULL` and `DEFAULT` are surfaced; constraint clauses (PK/FK/CHECK) are in bootstrap.sql, not repeated here._

## Sessions & runtime

### `sy_user`

> Centralized user model (inspired by Honcho) — replaces scattered memory/user_*.md files. Single source of user context injected into Claude sessions.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_user` | integer | NOT NULL | — |
| `codename` | character varying(64) | NOT NULL | — |
| `full_name` | text | NOT NULL | — |
| `dimensions` | jsonb | NOT NULL | '{}'::jsonb |
| `created_at` | timestamp with time zone | NOT NULL | now() |
| `updated_at` | timestamp with time zone | NOT NULL | now() |

Column notes:
- **`dimensions`** — JSONB tree: profile, communication_style, schedule, skills, history, preferences, private_only_for_alex.

### `sy_claude_session`

> Metadata index of Claude Code sessions (.jsonl). Full content stays on the filesystem at ~/.claude/projects/<project>/<uuid>.jsonl, accessible via a streaming endpoint.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_session` | character varying(36) | NOT NULL | — |
| `project` | character varying(255) | NOT NULL | — |
| `file_path` | character varying(512) | NOT NULL | — |
| `started_at` | timestamp with time zone | — | — |
| `ended_at` | timestamp with time zone | — | — |
| `message_count` | integer | — | 0 |
| `first_prompt` | text | — | — |
| `last_prompt` | text | — | — |
| `git_branch` | character varying(128) | — | — |
| `version` | character varying(32) | — | — |
| `size_bytes` | bigint | — | — |
| `mtime` | timestamp without time zone | — | — |
| `date_add` | timestamp with time zone | NOT NULL | now() |
| `date_upd` | timestamp with time zone | NOT NULL | now() |

### `sy_run`

> First-class RUN entity. Single source for /hub/runs (runs-only). Both sources (atlas-inbox via email intent=run, console via chat) write here. Emails with intent question/jobsite/noise do NOT become runs.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_run` | integer | NOT NULL | — |
| `source` | character varying(32) | NOT NULL | — |
| `trigger` | character varying(16) | NOT NULL | — |
| `scope` | character varying(64) | — | — |
| `title` | text | — | — |
| `status` | character varying(24) | NOT NULL | 'queued'::character varying |
| `ref_type` | character varying(32) | — | — |
| `ref_id` | character varying(64) | — | — |
| `started_at` | timestamp with time zone | — | — |
| `finished_at` | timestamp with time zone | — | — |
| `date_add` | timestamp with time zone | NOT NULL | now() |
| `date_upd` | timestamp with time zone | NOT NULL | now() |

Column notes:
- **`source`** — Origin of the run: atlas-inbox (email) | console (chat). Shown in the Source column.
- **`trigger`** — Triggering mechanism: email | chat | cron.
- **`scope`** — Perimeter: shyrka | <tenant codename>. NULL if not derivable (inbox case).
- **`ref_type`** — Type of the polymorphic ref: atlas_email (id_atlas_email) | brainstorm_job_thread (console thread uuid).
- **`ref_id`** — Polymorphic identifier: id_atlas_email for atlas-inbox, thread uuid for console.

### `sy_job_queue`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_job` | integer | NOT NULL | — |
| `kind` | character varying(64) | NOT NULL | — |
| `payload_json` | jsonb | NOT NULL | '{}'::jsonb |
| `status` | character varying(16) | NOT NULL | 'queued'::character varying |
| `error` | text | — | — |
| `date_add` | timestamp without time zone | NOT NULL | now() |
| `picked_at` | timestamp without time zone | — | — |
| `done_at` | timestamp without time zone | — | — |

### `sy_task_run`

> Tasks delegated to agents from the /hub/ cockpit. Executed by the worker daemon.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_task_run` | integer | NOT NULL | — |
| `codename` | character varying(64) | NOT NULL | — |
| `agent_codename` | character varying(64) | NOT NULL | — |
| `title` | character varying(255) | NOT NULL | — |
| `prompt` | text | NOT NULL | — |
| `template` | character varying(64) | — | — |
| `perimeter` | text | — | — |
| `exit_criteria` | text | — | — |
| `status` | character varying(32) | NOT NULL | 'pending'::character varying |
| `created_by` | character varying(64) | — | — |
| `started_at` | timestamp with time zone | — | — |
| `finished_at` | timestamp with time zone | — | — |
| `output_log` | text | — | — |
| `exit_code` | integer | — | — |
| `date_add` | timestamp with time zone | NOT NULL | now() |
| `date_upd` | timestamp with time zone | NOT NULL | now() |
| `actual_tokens` | integer | — | — |
| `cost_usd` | numeric(10,6) | — | — |
| `model` | character varying(100) | — | — |
| `input_context_tokens` | integer | — | — |
| `snapshot_commit_sha` | character varying | — | — |
| `snapshot_migrated_tables` | jsonb | — | — |
| `restored_at` | timestamp with time zone | — | — |
| `restore_reason` | text | — | — |

Column notes:
- **`codename`** — Unique kebab-case slug identifying the run in logs and at /hub/runs/<codename>.
- **`agent_codename`** — Logical FK to sy_agents.codename.
- **`perimeter`** — JSON list of file/directory paths the agent is allowed to touch (sandboxing).
- **`exit_criteria`** — Free text: completion conditions expected by the operator.
- **`status`** — pending | running | completed | failed | cancelled
- **`output_log`** — Streamed concatenated stdout/stderr; ephemeral, may be truncated.

### `sy_autonomy_window`

> Autonomy window per day (dow 0=Monday..6=Sunday, aligned with datetime.weekday()). start_hour->end_hour (wraps past midnight if start>end). enabled=false disables startup that day. Edited via /autonomie and /hub/autonomie.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `dow` | smallint | NOT NULL | — |
| `jour` | character varying(10) | NOT NULL | — |
| `start_hour` | smallint | NOT NULL | 19 |
| `end_hour` | smallint | NOT NULL | 4 |
| `enabled` | boolean | NOT NULL | true |
| `date_upd` | timestamp with time zone | NOT NULL | now() |


## Jobsite, work order & task

### `sy_jobsite`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_jobsite` | integer | NOT NULL | — |
| `codename` | character varying(64) | NOT NULL | — |
| `title` | character varying(255) | NOT NULL | — |
| `client_id` | character varying(32) | — | — |
| `status` | character varying(9) | NOT NULL | 'draft'::character varying |
| `priority` | character varying(2) | NOT NULL | 'P2'::character varying |
| `current_focus` | text | — | — |
| `deadline` | date | — | — |
| `notes` | text | — | — |
| `date_add` | timestamp with time zone | NOT NULL | now() |
| `date_upd` | timestamp with time zone | NOT NULL | now() |
| `archived_at` | timestamp without time zone | — | — |
| `archived_by` | character varying(64) | — | — |
| `mission_letter` | text | — | — |
| `scope` | character varying(32) | — | — |
| `preprod_test_plan` | text | — | — |
| `ship_command` | character varying(255) | — | — |
| `external_contacts` | text | — | — |
| `auto_explode` | boolean | NOT NULL | true |
| `mode_auto` | boolean | NOT NULL | false |
| `max_cost_eur` | numeric(8,2) | — | — |
| `requires_outcome_proof` | boolean | NOT NULL | false |
| `outcome_evidence` | text | — | — |
| `outcome_kpi` | text | — | — |
| `outcome_current` | text | — | — |
| `outcome_reached_at` | timestamp with time zone | — | — |
| `qa_verdict` | character varying(16) | — | — |
| `qa_verdict_at` | timestamp with time zone | — | — |
| `qa_proof_path` | text | — | — |
| `auto_deployed_at` | timestamp with time zone | — | — |
| `id_tenant` | character varying | — | — |
| `id_customer` | character varying | — | — |
| `completed_notified_at` | timestamp with time zone | — | — |
| `billing_mode` | text | NOT NULL | 'forfait'::text |
| `preferred_dows` | smallint[] | — | — |
| `doctrine_camp` | character varying | NOT NULL | 'occident'::character varying |
| `auto_analyse` | boolean | NOT NULL | true |
| `analyzed_at` | timestamp with time zone | — | — |
| `drift_suspected` | boolean | NOT NULL | false |
| `drift_report` | jsonb | — | — |
| `drift_checked_at` | timestamp with time zone | — | — |
| `regime` | character varying(16) | — | — |
| `autonomie_eligible` | boolean | NOT NULL | false |
| `classification_report` | jsonb | — | — |

Column notes:
- **`archived_at`** — Soft archive. NULL = active (default UI filter). Set = archived (kept searchable via RAG).
- **`mission_letter`** — Structured markdown mission letter (context/objectives/scope/criteria/constraints/team briefing). Optional. Conditionally injected into persona + qa_run.
- **`scope`** — Project perimeter (synedre|codemyshop-oss|codemyshop-enterprise|tenant|business). Distinct from client_id, which designates the target tenant. Shown as a badge on /hub/jobsite.
- **`preprod_test_plan`** — Free markdown: preprod URLs to validate, <TENANT> commands, visual checks. Displayed by /jobsite <codename> when status=test.
- **`ship_command`** — Exact command to run to close the jobsite (e.g. ./ship synedre-os, ./ship <TENANT>-v2, ./ship all). Displayed by /jobsite <codename> when status=test.
- **`external_contacts`** — CSV of email addresses (e.g. jane.doe@<TENANT>.com,john.smith@<TENANT>.com) proactively monitored by Marco Polo (watch agent). The sy_dream cron scans sy_inbox_emails over the last 7 days → matches → unpauses the jobsite and creates a task for the watch agent when activity is detected.
- **`auto_explode`** — If TRUE, when the jobsite's discovery work order passes done, triggers the sy_jobsite_explode_discovery LLM pipeline to create the Phase A/B/C work orders automatically. DB kill-switch.
- **`qa_verdict`** — QA orbit verdict during the test phase: green|red|incomplete|pending. green + auto-closable → done.
- **`qa_proof_path`** — Path to the 3-axis QA proof (sy_run_qa) produced by the orbit — zero false greens.
- **`auto_deployed_at`** — Last successful AUTO ./deploy launched by sy_autonomie_tick (non-client target). Throttle: the tick runs hourly within the 19h-4h window and would otherwise redeploy a jobsite in test ~10x per night. Only a deploy with rc=0 stamps it — a failure must be able to retry. NULL = never auto-deployed.
- **`preferred_dows`** — Weekdays (0=Monday..6=Sunday, aligned with datetime.weekday()) on which this jobsite is eligible for an autonomous run. NULL = eligible any day the sy_autonomy_window is open (historical behavior).

### `sy_jobsite_work_order`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_work_order` | integer | NOT NULL | — |
| `id_jobsite` | integer | NOT NULL | 0 |
| `codename` | character varying(64) | NOT NULL | — |
| `title` | character varying(255) | NOT NULL | — |
| `client_id` | character varying(32) | — | — |
| `status` | character varying(9) | NOT NULL | 'planning'::character varying |
| `priority` | character varying(2) | NOT NULL | 'P2'::character varying |
| `current_phase` | character varying(128) | — | — |
| `current_task` | text | — | — |
| `next_action` | text | — | — |
| `blockers` | text | — | — |
| `context_json` | text | — | — |
| `decisions_json` | text | — | — |
| `discoveries_json` | text | — | — |
| `repo_paths` | text | — | — |
| `related_vps` | text | — | — |
| `related_backlog` | text | — | — |
| `deadline` | date | — | — |
| `estimated_effort_d` | numeric(5,1) | — | — |
| `spent_effort_d` | numeric(5,1) | — | 0.0 |
| `notes` | text | — | — |
| `playbook_slug` | character varying(128) | — | — |
| `agent_codename` | character varying(64) | — | — |
| `agent_prompt` | text | — | — |
| `zone_perimeter` | text | — | — |
| `contract_dto` | text | — | — |
| `exit_criteria` | text | — | — |
| `current_cue_position` | integer | — | — |
| `date_add` | timestamp with time zone | NOT NULL | now() |
| `date_upd` | timestamp with time zone | NOT NULL | now() |
| `review_notified_at` | timestamp without time zone | — | — |
| `mode_auto` | boolean | NOT NULL | false |
| `qa_iteration_count` | integer | NOT NULL | 0 |
| `resolves_work_order_id` | integer | — | — |
| `depends_on_work_order_id` | integer | — | — |
| `runner` | character varying(32) | — | — |
| `auto_disabled_at` | timestamp with time zone | — | — |
| `auto_disabled_reason` | text | — | — |
| `auto_timeout_count` | integer | NOT NULL | 0 |

Column notes:
- **`review_notified_at`** — Date the founder was emailed when the work order moved to review. NULL = not yet notified.
- **`mode_auto`** — If TRUE, the /jobsite <code> -tr <work_order> --auto skill chains todo tasks automatically without intervention. Stop conditions: task failure, scope creep, failed deploy.
- **`qa_iteration_count`** — Count of QA iterations triggered in --auto mode. Max 3, then STOP and escalate to the founder.
- **`resolves_work_order_id`** — If NOT NULL, this follow-up work order resolves the referenced one (target = status=paused). When the follow-up passes done, auto cascade: paused→done + todo tasks→cancelled + append a resolved-by-follow-up entry to decision_json.
- **`depends_on_work_order_id`** — DEPRECATED: migrated to sy_work_order_dep (N:M DAG). Column kept READ-ONLY for one release. Read from sy_work_order_dep, write via INSERT/DELETE on sy_work_order_dep. Trigger trg_work_order_depends_on_readonly blocks any non-NULL write.
- **`auto_disabled_at`** — Anti-runaway circuit breaker: stamped by sy_task_worker when it disarms mode_auto on rc!=0 / qa=fail. NOT NULL = deliberate disarm, the autonomy tick NEVER re-arms. NULL = never armed, propagation from jobsite.mode_auto allowed. Cleared by manual re-arming (run-auto / the ▶ button).
- **`auto_disabled_reason`** — Reason for the anti-runaway disarm (e.g. "rc=1 + qa=fail"). Traceability: without it, mode_auto=false does not say WHY, and the next reader re-arms blindly.

### `sy_jobsite_agent`

> Teams recruited per jobsite — role production/validation.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_assignment` | integer | NOT NULL | — |
| `id_jobsite` | integer | NOT NULL | — |
| `agent_codename` | character varying(64) | NOT NULL | — |
| `role` | character varying(32) | NOT NULL | — |
| `"position"` | integer | NOT NULL | 0 |
| `date_assigned` | timestamp with time zone | NOT NULL | now() |
| `date_unassigned` | timestamp with time zone | — | — |
| `notes` | text | — | — |

### `sy_jobsite_claude_session`

> 1 jobsite = 1 Claude Code session (UUID jsonl under ~/.claude/projects/<project>/). Cap of 3 concurrent active sessions excluding sycl-default.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_session` | integer | NOT NULL | — |
| `id_jobsite` | integer | NOT NULL | — |
| `jsonl_uuid` | uuid | NOT NULL | — |
| `started_at` | timestamp with time zone | NOT NULL | now() |
| `last_active_at` | timestamp with time zone | NOT NULL | now() |
| `status` | character varying(16) | NOT NULL | 'active'::character varying |
| `size_bytes` | bigint | — | — |
| `closed_at` | timestamp with time zone | — | — |
| `closed_reason` | character varying(32) | — | — |

### `sy_jobsite_lock`

> Per-jobsite lock preventing two Claude Code sessions on the SAME jobsite. 30 min TTL with auto-cleanup via cron and auto-release on the Stop hook.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_jobsite` | integer | NOT NULL | — |
| `session_id` | character varying(64) | NOT NULL | — |
| `terminal_pid` | integer | — | — |
| `hostname` | character varying(64) | — | — |
| `opened_at` | timestamp with time zone | NOT NULL | now() |
| `last_activity` | timestamp with time zone | NOT NULL | now() |
| `owner_kind` | character varying(8) | NOT NULL | 'user'::character varying |

Column notes:
- **`session_id`** — Unique Claude Code session identifier. Order of precedence: env CLAUDE_SESSION_ID > sha256(tty) > pid-user@host.

### `sy_jobsite_readiness`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_readiness` | integer | NOT NULL | — |
| `id_jobsite` | integer | NOT NULL | — |
| `verdict` | character varying(16) | NOT NULL | — |
| `score` | integer | NOT NULL | 0 |
| `reasons` | text | — | — |
| `missing` | text | — | — |
| `enriched` | text | — | — |
| `action_taken` | character varying(32) | — | 'none'::character varying |
| `jobsite_status_at_run` | character varying(32) | — | — |
| `mode_auto_at_run` | boolean | — | — |
| `total_tasks` | integer | — | — |
| `assignees` | integer | — | — |
| `date_add` | timestamp with time zone | — | now() |
| `date_upd` | timestamp with time zone | — | now() |

### `sy_jobsite_qa_run`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_run` | integer | NOT NULL | — |
| `id_jobsite` | integer | NOT NULL | — |
| `triggered_by` | character varying(16) | NOT NULL | 'manual'::character varying |
| `yaml_version` | integer | — | — |
| `base_url` | character varying(255) | — | — |
| `total_checks` | integer | NOT NULL | 0 |
| `passed` | integer | NOT NULL | 0 |
| `failed` | integer | NOT NULL | 0 |
| `status` | character varying(16) | NOT NULL | 'running'::character varying |
| `output_json` | text | — | — |
| `duration_ms` | integer | — | — |
| `date_add` | timestamp with time zone | NOT NULL | now() |
| `date_upd` | timestamp with time zone | NOT NULL | now() |

### `sy_jobsite_relevance`

> Latest relevance verdict per jobsite (heuristic + LLM). Single source for the audit button on /hub/jobsite.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_relevance` | integer | NOT NULL | — |
| `id_jobsite` | integer | NOT NULL | — |
| `verdict` | character varying(16) | NOT NULL | — |
| `confidence` | numeric(3,2) | NOT NULL | — |
| `rationale` | text | NOT NULL | — |
| `source` | character varying(16) | NOT NULL | — |
| `jobsite_status_at_run` | character varying(16) | NOT NULL | — |
| `total_tasks` | integer | — | — |
| `done_tasks` | integer | — | — |
| `age_days` | integer | — | — |
| `llm_model` | character varying(64) | — | — |
| `llm_input_tokens` | integer | — | — |
| `llm_output_tokens` | integer | — | — |
| `id_audit_job` | integer | — | — |
| `date_add` | timestamp with time zone | NOT NULL | now() |
| `date_upd` | timestamp with time zone | NOT NULL | now() |

### `sy_jobsite_task`

> Third level of the jobsite hierarchy (tenant -> work order -> task).

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_task` | integer | NOT NULL | — |
| `id_work_order` | integer | NOT NULL | — |
| `title` | character varying(255) | NOT NULL | — |
| `description` | text | — | — |
| `status` | character varying(16) | NOT NULL | 'todo'::character varying |
| `priority` | character varying(2) | NOT NULL | 'P2'::character varying |
| `assignee_codename` | character varying(64) | — | — |
| `estimated_h` | numeric(5,2) | — | — |
| `spent_h` | numeric(5,2) | — | 0 |
| `"position"` | integer | NOT NULL | 0 |
| `started_at` | timestamp with time zone | — | — |
| `finished_at` | timestamp with time zone | — | — |
| `date_add` | timestamp with time zone | NOT NULL | now() |
| `date_upd` | timestamp with time zone | NOT NULL | now() |
| `iteration_count` | integer | NOT NULL | 0 |
| `last_test_at` | timestamp with time zone | — | — |
| `last_test_result` | character varying(16) | — | — |
| `estimated_tokens` | integer | — | — |
| `actual_tokens` | integer | — | — |
| `actual_cost_usd` | numeric(10,4) | — | — |
| `recommended_model` | character varying(32) | — | — |
| `scope` | character varying(32) | — | — |
| `visual_intent` | text | — | — |
| `visual_url` | text | — | — |
| `replay_on_reset` | smallint | NOT NULL | 0 |
| `last_fallback_reason` | character varying(64) | — | — |
| `replayed_at` | timestamp with time zone | — | — |
| `decompose_depth` | integer | NOT NULL | 0 |
| `task_type` | character varying(50) | — | NULL::character varying |
| `recommended_model_orient` | character varying(64) | — | NULL::character varying |

Column notes:
- **`status`** — todo → doing → testing → done | iterating (returned if a test fails) | cancelled
- **`priority`** — P0 | P1 | P2 | P3
- **`iteration_count`** — Incremented on each testing→iterating cycle. 0 = first attempt.
- **`last_test_result`** — pass | fail | inconclusive
- **`scope`** — Impact zone used to calibrate the LLM estimator. 7 canonical values: synedre-internal, codemyshop-oss, codemyshop-enterprise, tenant-single, tenant-multi, infra, doctrine. NULL = legacy rows.
- **`visual_intent`** — 火眼金睛 (visual QA): what must be VISIBLE on screen after the change (declared at creation). NULL = non-visual task.
- **`visual_url`** — 火眼金睛 (visual QA): URL where the rendering is checked (NULL = the jobsite's staging). See sy_huoyan_<TENANT> --jobsite.
- **`recommended_model_orient`** — Per-task GLM override when the jobsite runs with doctrine_camp=orient. NULL = derived from the tier via _GLM_TIER_MAP. Distinct from recommended_model (Anthropic tier) so switching between camps stays reversible.

### `sy_jobsite_tool`

> Tools available on a jobsite (tenant). id_jobsite=NULL = global default tool, otherwise a custom attachment.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_tool` | integer | NOT NULL | — |
| `id_jobsite` | integer | — | — |
| `slug` | character varying(64) | NOT NULL | — |
| `label` | character varying(128) | NOT NULL | — |
| `description` | text | — | — |
| `tool_type` | character varying(32) | NOT NULL | 'custom'::character varying |
| `config_json` | text | — | — |
| `icon` | character varying(16) | — | '🔧'::character varying |
| `"position"` | integer | NOT NULL | 0 |
| `active` | smallint | NOT NULL | 1 |
| `date_add` | timestamp with time zone | NOT NULL | now() |
| `date_upd` | timestamp with time zone | NOT NULL | now() |

Column notes:
- **`tool_type`** — skill (slash command) | automate (synedre/sy_*.py) | endpoint (API call) | custom (ad hoc)
- **`config_json`** — Tool-specific config (target_url, args, etc.) depending on tool_type.

### `sy_task_dep`

> N:M dependency DAG between tasks within a work order — id_task_blocked cannot start until id_task_blocker is done

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_dep` | integer | NOT NULL | — |
| `id_task_blocked` | integer | NOT NULL | — |
| `id_task_blocker` | integer | NOT NULL | — |
| `date_add` | timestamp without time zone | NOT NULL | now() |

Column notes:
- **`id_task_blocked`** — Blocked task (depends on id_task_blocker)
- **`id_task_blocker`** — Blocking task (must be done before id_task_blocked can start)

### `sy_task_iteration`

> ReAct pattern (Yao 2022): Reasoning + Acting + Observation cycle per task iteration. iteration_n=1 = first attempt, incremented on each testing→iterating transition.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_iteration` | integer | NOT NULL | — |
| `id_task` | integer | NOT NULL | — |
| `iteration_n` | integer | NOT NULL | — |
| `agent_codename` | character varying(64) | — | — |
| `reason` | text | — | — |
| `action` | text | — | — |
| `observation` | text | — | — |
| `test_result` | character varying(16) | — | — |
| `tools_used` | text | — | — |
| `duration_ms` | integer | — | — |
| `date_add` | timestamp with time zone | NOT NULL | now() |
| `id_scar` | integer | — | — |
| `tokens_used` | integer | — | — |

Column notes:
- **`reason`** — Agent's reasoning: why this action?
- **`action`** — Action taken (tool call, code change, message...)
- **`observation`** — Observed result (output, error, resulting state)
- **`test_result`** — pass | fail | inconclusive | skip
- **`tools_used`** — JSON array of sy_jobsite_tool slugs used in this iteration.
- **`id_scar`** — Logical FK to sy_scars.id_scar. NULL = iteration without a scar (direct success or skip). Set when test_result=fail and the lesson was recorded.

### `sy_task_skill`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_task_skill` | integer | NOT NULL | — |
| `id_task` | integer | NOT NULL | — |
| `skill_name` | character varying(64) | NOT NULL | — |
| `"position"` | integer | NOT NULL | 0 |
| `date_add` | timestamp with time zone | NOT NULL | now() |

### `sy_task_tool`

> N-N task <-> tools used. Traces which tool served which task.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_task_tool` | integer | NOT NULL | — |
| `id_task` | integer | NOT NULL | — |
| `id_tool` | integer | NOT NULL | — |
| `"position"` | integer | NOT NULL | 0 |
| `used_at` | timestamp with time zone | — | — |
| `notes` | text | — | — |
| `date_add` | timestamp with time zone | NOT NULL | now() |

### `sy_work_order_agent`

> N-N work order <-> agents: who works on this work order. is_lead=1 = orchestrator (max 1 per work order recommended).

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_assignment` | integer | NOT NULL | — |
| `id_work_order` | integer | NOT NULL | — |
| `agent_codename` | character varying(64) | NOT NULL | — |
| `role` | character varying(64) | — | — |
| `is_lead` | smallint | NOT NULL | 0 |
| `"position"` | integer | NOT NULL | 0 |
| `date_assigned` | timestamp with time zone | NOT NULL | now() |
| `date_unassigned` | timestamp with time zone | — | — |
| `notes` | text | — | — |

### `sy_work_order_dep`

> N:M dependency DAG between work orders — id_work_order_blocked cannot start until id_work_order_blocker is done

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_work_order_blocked` | integer | NOT NULL | — |
| `id_work_order_blocker` | integer | NOT NULL | — |
| `date_add` | timestamp without time zone | NOT NULL | now() |

Column notes:
- **`id_work_order_blocked`** — Blocked work order (depends on id_work_order_blocker)
- **`id_work_order_blocker`** — Blocking work order (must be done before id_work_order_blocked can start)

### `sy_work_order_review`

> Founder review of a work order (triggered when all its tasks are done). 1 work order = N reviews (re-review if rejected → scar recorded → back to dev → re-review).

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_review` | integer | NOT NULL | — |
| `id_work_order` | integer | NOT NULL | — |
| `iteration_n` | integer | NOT NULL | — |
| `status` | character varying(16) | NOT NULL | 'pending'::character varying |
| `reviewed_by` | character varying(64) | — | — |
| `notes` | text | — | — |
| `id_scar` | integer | — | — |
| `date_add` | timestamp with time zone | NOT NULL | now() |
| `date_upd` | timestamp with time zone | NOT NULL | now() |

Column notes:
- **`status`** — pending (awaiting review) | validated (✓) | rejected (✗ → scar)
- **`id_scar`** — Logical FK to sy_scars.id_scar (set when status=rejected).


## Agents

### `sy_agents`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_agent` | integer | NOT NULL | — |
| `codename` | character varying(64) | NOT NULL | — |
| `nickname` | character varying(64) | NOT NULL | — |
| `role` | character varying(255) | NOT NULL | — |
| `inspiration` | text | — | — |
| `quote` | text | — | — |
| `version` | character varying(10) | — | '1.0'::character varying |
| `personality` | text | — | — |
| `description` | text | — | — |
| `job_sheet` | text | — | — |
| `job_mission` | text | — | — |
| `job_perimeter` | text | — | — |
| `job_responsibilities` | text | — | — |
| `content_md` | text | — | — |
| `job_key_checks` | text | — | — |
| `cognitive_frame` | text | — | — |
| `heritage` | character varying(255) | — | — |
| `proof` | text | — | — |
| `orbite` | integer | NOT NULL | 3 |
| `group_name` | character varying(64) | — | 'execution'::character varying |
| `prompt_domains` | character varying(255) | — | — |
| `phases` | character varying(64) | — | — |
| `avatar_prompt` | text | — | — |
| `avatar_url` | character varying(512) | — | — |
| `initials` | character varying(4) | — | — |
| `profile_path` | character varying(255) | — | — |
| `show_on_homepage` | integer | NOT NULL | 1 |
| `auto_spawn` | integer | NOT NULL | 0 |
| `active` | integer | NOT NULL | 1 |
| `"position"` | integer | NOT NULL | 0 |
| `spawn_count` | integer | NOT NULL | 0 |
| `error_count` | integer | NOT NULL | 0 |
| `date_add` | timestamp with time zone | NOT NULL | — |
| `date_upd` | timestamp with time zone | NOT NULL | — |
| `role_en` | text | — | — |
| `heritage_en` | text | — | — |
| `proof_en` | text | — | — |
| `description_en` | text | — | — |
| `personality_en` | text | — | — |
| `inspiration_en` | text | — | — |
| `cognitive_frame_en` | text | — | — |
| `job_mission_en` | text | — | — |
| `product_scope` | character varying(48) | NOT NULL | 'transverse'::character varying |

### `sy_agent_activity`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_activity` | integer | NOT NULL | — |
| `activity_id` | character varying(32) | — | — |
| `agent_codename` | character varying(64) | NOT NULL | — |
| `action` | character varying(100) | NOT NULL | — |
| `summary` | character varying(500) | — | ''::character varying |
| `severity` | character varying(20) | — | 'info'::character varying |
| `duration_ms` | integer | — | 0 |
| `details` | text | — | — |
| `date_add` | timestamp with time zone | NOT NULL | CURRENT_TIMESTAMP |

### `sy_agent_event`

> Stream-json events from Claude Code spawns, generalized to multiple sources (email/jobsite/task_run/manual). Fine-grained capture of agent reasoning for the live cockpit and the self-improving roadmap.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_event` | integer | NOT NULL | — |
| `id_atlas_email` *(FK to external table dropped in OSS distro)* | integer | — | — |
| `event_seq` | integer | NOT NULL | — |
| `event_type` | character varying(64) | NOT NULL | — |
| `tool_name` | character varying(64) | — | — |
| `duration_ms` | integer | — | — |
| `payload` | jsonb | NOT NULL | — |
| `ts` | timestamp with time zone | NOT NULL | now() |
| `agent_codename` | character varying(64) | NOT NULL | 'atlas'::character varying |
| `source_type` | character varying(16) | NOT NULL | 'email'::character varying |
| `source_id` | bigint | — | — |

Column notes:
- **`agent_codename`** — Codename of the agent emitting the event (sy_agents.codename). Atlas for email sources; can be turing/lovelace/mitnick/etc. for jobsite sources.
- **`source_type`** — Type of source that triggered this spawn: email (Atlas Inbox), jobsite (--auto), task_run (sy_task_run worker), manual (interactive CLI).
- **`source_id`** — Polymorphic BIGINT FK to the source table (id_atlas_email for email, id_jobsite for jobsite, id_task_run for task_run, id_session for manual).

### `sy_agent_heartbeat`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_heartbeat` | integer | NOT NULL | — |
| `agent_codename` | character varying(64) | NOT NULL | — |
| `status` | character varying(20) | — | 'idle'::character varying |
| `last_seen` | timestamp with time zone | NOT NULL | CURRENT_TIMESTAMP |

### `sy_agent_relations`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_relation` | integer | NOT NULL | — |
| `id_agent_from` | integer | NOT NULL | — |
| `id_agent_to` | integer | NOT NULL | — |
| `relation_type` | character varying(16) | NOT NULL | — |
| `date_add` | timestamp with time zone | NOT NULL | — |

### `sy_agent_skill`

> N-N agent <-> skills. is_default=1 = native skill; otherwise acquired. acquired_from_work_order records the jobsite that brought in the skill.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_agent_skill` | integer | NOT NULL | — |
| `agent_codename` | character varying(64) | NOT NULL | — |
| `skill_slug` | character varying(64) | NOT NULL | — |
| `is_default` | smallint | NOT NULL | 0 |
| `acquired_from_work_order` | character varying(64) | — | — |
| `acquired_at` | timestamp with time zone | NOT NULL | now() |
| `mastery_level` | smallint | — | 1 |
| `notes` | text | — | — |
| `date_upd` | timestamp with time zone | NOT NULL | now() |

Column notes:
- **`mastery_level`** — 1-5 (1=beginner, 5=master). Increases with usage.

### `sy_agent_tool`

> Registry of Claude Code CLI tools available to Atlas (spawned with bypassPermissions, no --allowedTools restriction). builtin = guaranteed; mcp = conditional (depends on the MCP servers configured in settings at spawn time).

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_tool` | integer | NOT NULL | — |
| `name` | character varying(48) | NOT NULL | — |
| `category` | character varying(32) | NOT NULL | — |
| `description` | text | NOT NULL | — |
| `source` | character varying(16) | NOT NULL | 'builtin'::character varying |
| `active` | smallint | NOT NULL | 1 |
| `"position"` | integer | NOT NULL | 0 |
| `date_add` | timestamp without time zone | NOT NULL | now() |
| `date_upd` | timestamp without time zone | NOT NULL | now() |

### `sy_agent_xp`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_xp` | integer | NOT NULL | — |
| `agent_codename` | character varying(64) | NOT NULL | — |
| `xp` | integer | NOT NULL | 0 |
| `level` | integer | NOT NULL | 1 |
| `date_add` | timestamp with time zone | NOT NULL | CURRENT_TIMESTAMP |
| `date_upd` | timestamp with time zone | NOT NULL | CURRENT_TIMESTAMP |

### `sy_agent_xp_history`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_history` | integer | NOT NULL | — |
| `agent_codename` | character varying(64) | NOT NULL | — |
| `delta` | integer | NOT NULL | — |
| `reason` | character varying(500) | NOT NULL | — |
| `xp_after` | integer | NOT NULL | — |
| `date_add` | timestamp with time zone | NOT NULL | CURRENT_TIMESTAMP |

### `sy_ai_routing`

> Canonical AI routing. Read by sy_ai_provider.py (Python) and ai-gateway.ts (TS). Replaces ai-routing.yaml.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `feature` | text | NOT NULL | — |
| `embed_provider` | text | — | — |
| `complete_provider` | text | — | — |
| `model` | text | — | — |
| `extra` | jsonb | — | — |
| `note` | text | — | — |
| `updated_at` | timestamp with time zone | NOT NULL | now() |


## Automates

### `sy_automates`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_automate` | integer | NOT NULL | — |
| `key_name` | character varying(64) | NOT NULL | — |
| `nom` | character varying(128) | NOT NULL | — |
| `description` | text | — | — |
| `caste` | character varying(64) | NOT NULL | '''execution'''::character varying |
| `kind` | character varying(9) | NOT NULL | '''recurring'''::character varying |
| `schedule` | character varying(64) | — | — |
| `hour_utc` | smallint | — | — |
| `agent_codename` | character varying(64) | — | — |
| `cli_model` | character varying(64) | — | — |
| `active` | smallint | NOT NULL | 1 |
| `"position"` | integer | NOT NULL | 0 |
| `date_add` | timestamp with time zone | NOT NULL | now() |
| `date_upd` | timestamp with time zone | NOT NULL | now() |
| `scope` | character varying(48) | NOT NULL | 'synedre'::character varying |
| `billing_mode` | character varying(16) | — | — |

### `sy_automate_agents`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_automate` | integer | NOT NULL | — |
| `agent_codename` | character varying(64) | NOT NULL | — |
| `role` | character varying(8) | NOT NULL | '''user'''::character varying |
| `date_add` | timestamp with time zone | NOT NULL | now() |

### `sy_automate_playbooks`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_automate` | integer | NOT NULL | — |
| `playbook_slug` | character varying(128) | NOT NULL | — |
| `step_position` | integer | NOT NULL | 0 |
| `date_add` | timestamp with time zone | NOT NULL | now() |

### `sy_automate_llm_run`

> Cost ($), tokens and model per execution of the LLM cron automations outside autonomous jobsites (sy_agent_event only covers brainstorm/jobsite/email).

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_run` | bigint | NOT NULL | — |
| `script_name` | text | NOT NULL | — |
| `ts` | timestamp with time zone | NOT NULL | now() |
| `provider` | text | — | — |
| `model` | text | — | — |
| `cost_usd` | numeric | — | — |
| `input_tokens` | bigint | — | — |
| `output_tokens` | bigint | — | — |
| `cache_read_tokens` | bigint | — | — |
| `cache_creation_tokens` | bigint | — | — |
| `num_turns` | integer | — | — |
| `duration_ms` | bigint | — | — |
| `success` | boolean | NOT NULL | true |
| `error_msg` | text | — | — |

### `sy_automate_logs`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_log` | integer | NOT NULL | — |
| `automate` | character varying(64) | NOT NULL | — |
| `env` | character varying(16) | NOT NULL | '''preprod'''::character varying |
| `result` | character varying(20) | — | — |
| `duration_s` | numeric(10,2) | — | 0.00 |
| `step_count` | integer | — | 0 |
| `error_count` | integer | — | 0 |
| `warning_count` | integer | — | 0 |
| `counters` | text | — | — |
| `steps` | text | — | — |
| `errors` | text | — | — |
| `warnings` | text | — | — |
| `result_detail` | text | — | — |
| `context` | text | — | — |
| `date_add` | timestamp with time zone | NOT NULL | now() |


## Cron

### `sy_cron_heartbeat`

> Registry of supervised cron jobs and their last heartbeat. The beat is written BY THE SCRIPT itself (synedre/sy_cron_beat.py), NEVER by the crontab line: a beat appended as `; beat` once reported a job as alive while python had never actually run (sourcing failed, the && broke before reaching it). The beat proves the SCRIPT executed, not that cron fired. Read by synedre/sy_cron_deadman.py.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `script_name` | text | NOT NULL | — |
| `registered_at` | timestamp with time zone | NOT NULL | now() |
| `last_beat_at` | timestamp with time zone | — | — |
| `last_status` | text | — | — |
| `last_duration_ms` | integer | — | — |
| `expected_interval_s` | integer | NOT NULL | — |
| `max_silence_s` | integer | NOT NULL | — |
| `last_alerted_at` | timestamp with time zone | — | — |
| `active` | boolean | NOT NULL | true |
| `notes` | text | — | — |

Column notes:
- **`script_name`** — Script name WITHOUT path or extension (e.g. sy_whatsapp_to_<TENANT>). Identity key shared between the beat (writer) and the detector (reader).
- **`registered_at`** — Registration date. ESSENTIAL: without it, a row that never beat (last_beat_at NULL) has no age, and the detector cannot tell how long it has been dead. The STILLBORN cron (miswired, never executed even once) is precisely the failure mode that matters most to catch.
- **`last_beat_at`** — Last heartbeat. NULL = this script has NEVER beaten since registered_at: stillborn, not merely waiting. The detector then measures the silence from registered_at.
- **`last_status`** — ok | fail — state of the LAST run. Complements sy_cron_errors: `fail` = the script ran and ended badly (it still beats, it is alive); silence = it did not run at all. Two different failures, two different signals.
- **`expected_interval_s`** — Declared nominal cadence, in seconds (e.g. 15 for sy_whatsapp_to_<TENANT> = 4 crontab lines offset by 0/15/30/45s; 60 for a plain * * * * *). DECLARED rather than derived from the crontab: explicit beats magic, and the crontab is not git-tracked.
- **`max_silence_s`** — Death threshold: beyond this silence the script is declared dead. ABSOLUTE threshold in seconds rather than a multiplicative factor — a 3x factor on a 15s cron would alert after 45s, i.e. at the slightest hiccup. Each cron declares the absence window that TRULY matters for it. CHECK: must exceed expected_interval_s.
- **`last_alerted_at`** — Last alert emitted for this script. Anti-spam: without it the detector would re-alert on every pass for the same dead script. A noisy guard dies socially (the operator filters it, then stops opening) — the null case (all-green registry = ZERO emails) is a deliverable.
- **`active`** — FALSE = supervision suspended (cron intentionally switched off). Do not delete the row to silence an alert: registered_at and the history would be lost.


## Doctrine, scars & introspection

### `sy_conscience_health`

> Shyrka's nightly health report: aggregate of the audits per dimension. Read-only.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_health` | integer | NOT NULL | — |
| `run_date` | date | NOT NULL | CURRENT_DATE |
| `dimension` | character varying(24) | NOT NULL | — |
| `status` | character varying(12) | NOT NULL | 'ok'::character varying |
| `score` | integer | — | — |
| `metric` | jsonb | — | — |
| `summary` | text | — | — |
| `created_at` | timestamp with time zone | NOT NULL | now() |

### `sy_doc_coverage`

> Shyrka's documentation blind spots: real facades not covered by any chapter. Read-only.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_coverage` | integer | NOT NULL | — |
| `run_date` | date | NOT NULL | CURRENT_DATE |
| `unit` | character varying(160) | NOT NULL | — |
| `family` | character varying(48) | — | — |
| `covered` | smallint | NOT NULL | 0 |
| `created_at` | timestamp with time zone | NOT NULL | now() |
| `kind` | character varying(16) | NOT NULL | 'facade'::character varying |

### `sy_doc_drift`

> Shyrka's nightly mirror: gap between doc (proprioception) and code (body). Read-only.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_drift` | integer | NOT NULL | — |
| `run_date` | date | NOT NULL | CURRENT_DATE |
| `slug` | character varying(64) | NOT NULL | — |
| `source_file` | character varying(128) | — | — |
| `drift_kind` | character varying(32) | NOT NULL | 'clean'::character varying |
| `drift_score` | integer | NOT NULL | 0 |
| `source_hash_current` | character varying(64) | — | — |
| `source_hash_published` | character varying(64) | — | — |
| `dead_refs` | text[] | — | — |
| `details` | text | — | — |
| `created_at` | timestamp with time zone | NOT NULL | now() |

### `sy_doc_external_review`

> Outside-eyes feature: reviews of the public docs by external models, gated against prompt injection.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_review` | integer | NOT NULL | — |
| `chapter_slug` | text | NOT NULL | — |
| `lang` | text | NOT NULL | 'fr'::text |
| `prompt_generated` | text | — | — |
| `external_model` | text | — | — |
| `external_response` | text | — | — |
| `status` | text | NOT NULL | 'submitted'::text |
| `verdict_json` | jsonb | — | — |
| `injection_attempt_detected` | boolean | NOT NULL | false |
| `pending_id` | integer | — | — |
| `scar_id` | integer | — | — |
| `submitted_by` | text | — | — |
| `created_at` | timestamp with time zone | NOT NULL | now() |
| `processed_at` | timestamp with time zone | — | — |

Column notes:
- **`prompt_generated`** — Scrubbed public HTML built from sy_doc_chapter ONLY. Never any internal .md content.
- **`external_response`** — External model's response pasted in by the human. 50k char cap enforced by the POST endpoint.
- **`injection_attempt_detected`** — Computed by a sandboxed claude -p. If true: log severity=high in sy_daily_meet, no action taken.

### `sy_doc_gap`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_gap` | integer | NOT NULL | — |
| `id_review` | integer | NOT NULL | — |
| `chapter_slug` | text | NOT NULL | — |
| `claim` | text | NOT NULL | — |
| `triage_kind` | text | NOT NULL | — |
| `severity` | text | NOT NULL | 'medium'::text |
| `reason` | text | — | — |
| `suggested_agent` | text | — | — |
| `backlog_id` *(FK to external table dropped in OSS distro)* | integer | — | — |
| `dedup_key` | text | NOT NULL | — |
| `created_at` | timestamp with time zone | NOT NULL | now() |

### `sy_doc_public_mirror`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `slug` | text | NOT NULL | — |
| `lang` | text | NOT NULL | 'fr'::text |
| `html` | text | NOT NULL | — |
| `updated_at` | timestamp with time zone | NOT NULL | now() |

### `sy_scars`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_scar` | integer | NOT NULL | — |
| `agent_codename` | character varying(64) | NOT NULL | — |
| `error_type` | character varying(64) | NOT NULL | '''convention'''::character varying |
| `description` | text | NOT NULL | — |
| `check_added` | text | — | — |
| `root_cause` | text | — | — |
| `corrected_by` | character varying(64) | — | '''alexandre'''::character varying |
| `client_id` | character varying(32) | — | — |
| `severity` | character varying(8) | NOT NULL | '''medium'''::character varying |
| `resolved` | smallint | NOT NULL | 1 |
| `date_add` | timestamp with time zone | NOT NULL | now() |
| `error_type_proposed` | character varying(64) | — | — |
| `qualify_confidence` | numeric(3,2) | — | — |
| `qualify_reasoning` | text | — | — |
| `tags` | text[] | — | — |
| `kind` | character varying(16) | NOT NULL | 'failure'::character varying |
| `importance` | smallint | — | — |
| `recall_count` | integer | NOT NULL | 0 |
| `last_recall_at` | timestamp without time zone | — | — |
| `learnable` | boolean | NOT NULL | false |
| `public_status` | character varying(16) | — | — |
| `guardrail_status` | character varying(16) | — | — |
| `id_jobsite` | integer | — | — |
| `dup_signature` | character varying(160) | — | — |
| `duplicate_count` | integer | NOT NULL | 0 |
| `last_dup_at` | timestamp with time zone | — | — |

Column notes:
- **`error_type`** — Closed taxonomy: frontend_ui, i18n, api_contract, db_schema, auth_session, deploy_propagation, automation_silent_fail, routing_seo, naming_convention, legacy_cleanup, infra_git, email_imap, accessibility, tenant_isolation, data_quality, other. Legacy: convention (to be requalified via sy_scar_qualify.py).
- **`severity`** — low | medium | high | critical (CHECK chk_scars_severity).
- **`error_type_proposed`** — Category proposed by the LLM qualifier (to be committed into error_type after human review).
- **`qualify_confidence`** — Confidence 0.00-1.00. <0.70 = human review required before committing error_type=error_type_proposed.
- **`qualify_reasoning`** — One-line LLM justification (audit trail).
- **`tags`** — Orthogonal axes: tenant, env, priority, domain. Searched via @> (array contains).
- **`dup_signature`** — Auto-only canonical signature (format auto:<pattern_id>@<agent_codename>). NULL = non-auto path (victory, manual task failure, publish) → dedup disabled.
- **`duplicate_count`** — Re-recorded occurrences absorbed by auto-dedup (NOT NULL DEFAULT 0). Counter INDEPENDENT from recall_count (which measures served recalls).
- **`last_dup_at`** — Timestamp of the last absorbed occurrence. NULL until a duplicate has been seen.

### `sy_header_shell_health_history`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_snapshot` | integer | NOT NULL | — |
| `client_codename` | character varying(100) | NOT NULL | — |
| `run_at` | timestamp with time zone | NOT NULL | now() |
| `checked` | integer | NOT NULL | 0 |
| `n_degraded` | integer | NOT NULL | 0 |
| `pct_degraded` | numeric(5,2) | NOT NULL | 0 |
| `verdict` | character varying(16) | NOT NULL | 'ok'::character varying |
| `bad_sample_json` | text | — | — |
| `detail_json` | text | — | — |
| `date_add` | timestamp with time zone | NOT NULL | now() |

### `sy_reflex`

> Decentralized reflexes — active guard rules (settings.json -> DB -> decision bridge).

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_reflex` | integer | NOT NULL | — |
| `event` | text | NOT NULL | — |
| `tool_matcher` | text | NOT NULL | ''::text |
| `scope` | text | NOT NULL | 'global'::text |
| `path_glob` | text | — | — |
| `pattern` | text | — | — |
| `handler` | text | — | — |
| `action` | text | NOT NULL | 'deny'::text |
| `reason` | text | NOT NULL | — |
| `fail_mode` | text | NOT NULL | 'closed'::text |
| `active` | smallint | NOT NULL | 1 |
| `date_add` | timestamp without time zone | NOT NULL | now() |
| `date_upd` | timestamp without time zone | NOT NULL | now() |
| `tier` | text | NOT NULL | 'bras'::text |

### `sy_reflex_audit`

> Trace of every decision made by the sy_reflex.py facade.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_audit` | integer | NOT NULL | — |
| `id_reflex` | integer | — | — |
| `event` | text | — | — |
| `tool_name` | text | — | — |
| `file_path` | text | — | — |
| `decision` | text | NOT NULL | — |
| `reason` | text | — | — |
| `cwd` | text | — | — |
| `session_id` | text | — | — |
| `matched_token` | text | — | — |
| `date_add` | timestamp without time zone | NOT NULL | now() |

### `sy_reflex_proposal`

> INERT staging of reflex proposals (adaptive-immunity organ). NEVER read by sy_reflex.py (which only reads sy_reflex WHERE active=1 AND tier=bras). No active column: no accidental arming possible. Promotion = gated human arm().

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_proposal` | integer | NOT NULL | — |
| `cluster_signature` | text | NOT NULL | — |
| `dominant_error_type` | text | — | — |
| `proposed_by_agent` | character varying(64) | NOT NULL | 'immunite'::character varying |
| `event` | text | NOT NULL | — |
| `tool_matcher` | text | NOT NULL | ''::text |
| `scope` | text | NOT NULL | 'global'::text |
| `path_glob` | text | — | — |
| `pattern` | text | — | — |
| `handler` | text | — | — |
| `action` | text | NOT NULL | 'warn'::text |
| `reason` | text | — | — |
| `fail_mode` | text | NOT NULL | 'closed'::text |
| `tier` | text | NOT NULL | 'bras'::text |
| `evidence` | jsonb | — | — |
| `status` | character varying(16) | NOT NULL | 'pending'::character varying |
| `mitnick_verdict` | character varying(16) | — | — |
| `reviewed_by` | character varying(64) | — | — |
| `reviewed_at` | timestamp without time zone | — | — |
| `rejected_reason` | text | — | — |
| `promoted_to_reflex_id` | integer | — | — |
| `date_add` | timestamp without time zone | NOT NULL | now() |
| `date_upd` | timestamp without time zone | NOT NULL | now() |

Column notes:
- **`evidence`** — Source scars: {cluster_id, member_ids:[...], samples:[{id,error_type,desc}], recall, recency}. A proposal without evidence is rejected.
- **`status`** — pending → reviewed (Mitnick has ruled) → promoted (armed in sy_reflex, human action) | rejected. The CHECK chk_reflex_proposal_arming_gate forbids promoted without a clean review.
- **`mitnick_verdict`** — Security review verdict (Mitnick agent) BEFORE any arming. clean = safe to arm; flagged = refused. NULL = not yet reviewed.


## Lexicon & LLM pricing

### `sy_lexicon`

> Canonical internal-ops registry of the Synedre OS vocabulary (statuses, identifiers, verbs). Source of truth once loaded. Scope: ops only — no product/SEO vocabulary (see sy_dictionary).

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_lexicon` | integer | NOT NULL | — |
| `concept` | character varying(128) | NOT NULL | — |
| `mot_canonique` | character varying(128) | NOT NULL | — |
| `slug` | character varying(128) | NOT NULL | — |
| `table_cible` | character varying(128) | — | — |
| `colonne_cible` | character varying(128) | — | — |
| `statuts_autorises` | jsonb | — | — |
| `synonymes_interdits` | jsonb | — | — |
| `entry_scope` | character varying(64) | NOT NULL | 'ops-interne'::character varying |
| `notes` | text | — | — |
| `created_at` | timestamp with time zone | NOT NULL | now() |
| `updated_at` | timestamp with time zone | NOT NULL | now() |
| `check_db_cible` | boolean | NOT NULL | false |

Column notes:
- **`statuts_autorises`** — jsonb array of allowed values for the target column (e.g. ["planning","dev",...]). NULL if not applicable.
- **`synonymes_interdits`** — jsonb array of synonyms to ban (e.g. ["state","etat"]). NULL if not applicable.
- **`entry_scope`** — Scope of the entry. Seed value = 'ops-interne'. Named entry_scope (not scope) to avoid confusion with business scope.
- **`check_db_cible`** — true = entry backed by a DB CHECK on colonne_cible (constrained statuses/scope; triple enforcement registry+CHECK+linter); false = linter-only (CLI verbs deploy/ship, identifiers codename/slug/id without an enum).

### `sy_llm_pricing`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_pricing` | integer | NOT NULL | — |
| `provider` | character varying(32) | NOT NULL | — |
| `model` | character varying(100) | NOT NULL | — |
| `input_per_mtok` | numeric(10,4) | NOT NULL | — |
| `output_per_mtok` | numeric(10,4) | NOT NULL | — |
| `cache_read_per_mtok` | numeric(10,4) | — | — |
| `cache_write_per_mtok` | numeric(10,4) | — | — |
| `effective_date` | date | NOT NULL | — |
| `source` | character varying(64) | — | — |
| `active` | smallint | NOT NULL | 1 |
| `date_add` | timestamp with time zone | NOT NULL | now() |
| `capability_tier` | character varying(8) | — | — |

### `sy_ai_usage`

> AI API usage per call (tokens + cost) — per-tenant attribution and rebilling (Pacioli). Fed by sy_ai_provider._meter_usage.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_usage` | bigint | NOT NULL | — |
| `provider` | text | NOT NULL | — |
| `model` | text | NOT NULL | — |
| `meter_tag` | text | NOT NULL | ''::text |
| `input_tokens` | integer | NOT NULL | 0 |
| `output_tokens` | integer | NOT NULL | 0 |
| `cost_usd` | numeric(10,6) | NOT NULL | 0 |
| `created_at` | timestamp with time zone | NOT NULL | now() |


## Pentest

### `sy_pentest_finding`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_finding` | integer | NOT NULL | — |
| `id_run` | integer | — | — |
| `tenant_codename` | text | NOT NULL | — |
| `domain` | text | NOT NULL | — |
| `layer` | text | NOT NULL | 'passive'::text |
| `tool` | text | — | — |
| `check_key` | text | NOT NULL | — |
| `severity` | text | NOT NULL | — |
| `title` | text | NOT NULL | — |
| `detail` | text | — | — |
| `fingerprint` | text | NOT NULL | — |
| `status` | text | NOT NULL | 'open'::text |
| `first_seen` | timestamp with time zone | NOT NULL | now() |
| `last_seen` | timestamp with time zone | NOT NULL | now() |
| `fixed_at` | timestamp with time zone | — | — |
| `alerted_at` | timestamp with time zone | — | — |

### `sy_pentest_run`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_run` | integer | NOT NULL | — |
| `started_at` | timestamp with time zone | NOT NULL | now() |
| `finished_at` | timestamp with time zone | — | — |
| `mode` | text | NOT NULL | 'passive'::text |
| `targets_count` | integer | NOT NULL | 0 |
| `findings_count` | integer | NOT NULL | 0 |
| `p0_count` | integer | NOT NULL | 0 |
| `p1_count` | integer | NOT NULL | 0 |
| `p2_count` | integer | NOT NULL | 0 |
| `notes` | text | — | — |


## SEO engine (technical)

### `sy_canary_target`

> Uptime canaries per page TYPE (zero tolerance) — one representative URL per type and per production tenant. Read by sy_canary_monitor.py.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_canary` | integer | NOT NULL | — |
| `client_id` | character varying(64) | NOT NULL | — |
| `page_type` | character varying(32) | NOT NULL | — |
| `path` | character varying(512) | NOT NULL | — |
| `label` | character varying(160) | — | — |
| `critical` | smallint | NOT NULL | 1 |
| `active` | smallint | NOT NULL | 1 |
| `date_add` | timestamp with time zone | NOT NULL | now() |
| `date_upd` | timestamp with time zone | NOT NULL | now() |

### `sy_seo_authority_cache`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `client_codename` | text | NOT NULL | — |
| `entity_type` | text | NOT NULL | — |
| `entity_id` | integer | NOT NULL | — |
| `url` | text | NOT NULL | — |
| `label` | text | NOT NULL | — |
| `validated_at` | timestamp with time zone | NOT NULL | now() |

### `sy_seo_brand_brief`

> VERIFIED brand facts per tenant (SEO grounding). Multi-tenant: zero hardcoded tenant in the code. HARD RULE, 4 invariants.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `client_codename` | text | NOT NULL | — |
| `facts` | text | NOT NULL | — |
| `updated_at` | timestamp with time zone | — | now() |
| `authority_url` | text | — | — |
| `authority_label` | text | — | — |
| `sector_topics` | text | — | — |
| `seo_register` | text | — | — |
| `seo_markers` | text | — | — |
| `seo_gen_content` | boolean | NOT NULL | false |
| `authority_map` | text | — | — |
| `authority_domains` | jsonb | — | — |

Column notes:
- **`authority_url`** — External authority link (EEAT) injected deterministically — editorial, supplied by the tenant (never hallucinated).
- **`sector_topics`** — Lexical angles of the vertical (injected into content prompts) — e.g. food: caliber, packaging, shelf life. Multi-tenant: never a hardcoded vertical in the engine.

### `sy_seo_bulk_queue`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_job` | integer | NOT NULL | — |
| `tenant` | character varying(64) | NOT NULL | — |
| `entity` | character varying(16) | NOT NULL | 'category'::character varying |
| `id_entity` | integer | NOT NULL | — |
| `preprod` | boolean | NOT NULL | false |
| `status` | character varying(16) | NOT NULL | 'pending'::character varying |
| `error_msg` | text | — | — |
| `requested_by` | integer | — | — |
| `date_add` | timestamp(0) without time zone | NOT NULL | now() |
| `date_upd` | timestamp(0) without time zone | NOT NULL | now() |

### `sy_seo_coverage_snapshot`

> Daily snapshot of source-language SEO coverage (FR, id_lang=1).

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_snapshot` | integer | NOT NULL | — |
| `client_codename` | text | NOT NULL | — |
| `entity` | text | NOT NULL | — |
| `dim` | text | NOT NULL | — |
| `total_pages` | integer | NOT NULL | — |
| `filled` | integer | NOT NULL | — |
| `holes` | integer | NOT NULL | — |
| `is_optional` | boolean | NOT NULL | false |
| `run_at` | timestamp with time zone | NOT NULL | now() |

### `sy_seo_health_history`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_snapshot` | integer | NOT NULL | — |
| `client_codename` | character varying(100) | NOT NULL | — |
| `run_at` | timestamp with time zone | NOT NULL | now() |
| `sitemap_total` | integer | — | — |
| `n_200` | integer | — | — |
| `n_404` | integer | — | — |
| `n_5xx` | integer | — | — |
| `pct_404` | numeric(5,2) | — | — |
| `gsc_clicks_28d` | integer | — | — |
| `gsc_impr_28d` | integer | — | — |
| `gsc_clicks_prev` | integer | — | — |
| `gsc_impr_prev` | integer | — | — |
| `gsc_clicks_delta_pct` | numeric(7,2) | — | — |
| `gsc_impr_delta_pct` | numeric(7,2) | — | — |
| `verdict` | character varying(16) | NOT NULL | 'ok'::character varying |
| `detail_json` | text | — | — |
| `date_add` | timestamp with time zone | NOT NULL | now() |

### `sy_seo_i18n_audit`

> i18n SEO coverage tracking (translated slug/name/meta/h1) per tenant/language/entity/field. Fed by sy_audit_seo_i18n (shyrka cron). Complements sy_seo_health_history (SEO sentinel).

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_audit` | integer | NOT NULL | — |
| `client_codename` | character varying(64) | NOT NULL | — |
| `lang` | character varying(8) | NOT NULL | — |
| `entity` | character varying(32) | NOT NULL | — |
| `field` | character varying(32) | NOT NULL | — |
| `total` | integer | NOT NULL | 0 |
| `missing` | integer | NOT NULL | 0 |
| `duplicate` | integer | NOT NULL | 0 |
| `french` | integer | NOT NULL | 0 |
| `is_ok` | boolean | NOT NULL | false |
| `last_check` | timestamp with time zone | NOT NULL | now() |

### `sy_seo_keyword_position`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_position` | integer | NOT NULL | — |
| `client_codename` | character varying(100) | NOT NULL | — |
| `keyword` | character varying(255) | NOT NULL | — |
| `period_month` | date | NOT NULL | — |
| `avg_position` | numeric(6,2) | — | — |
| `clicks` | integer | NOT NULL | 0 |
| `impressions` | integer | NOT NULL | 0 |
| `ctr` | numeric(6,4) | — | — |
| `computed_at` | timestamp with time zone | NOT NULL | now() |

### `sy_seo_page_backup`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_backup` | integer | NOT NULL | — |
| `client_codename` | character varying(64) | NOT NULL | — |
| `entity` | character varying(32) | NOT NULL | — |
| `id_entity` | integer | NOT NULL | — |
| `lang` | character varying(8) | NOT NULL | — |
| `phase` | character varying(8) | NOT NULL | 'before'::character varying |
| `snapshot_json` | jsonb | NOT NULL | — |
| `created_at` | timestamp with time zone | NOT NULL | now() |

### `sy_seo_page_status`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_status` | integer | NOT NULL | — |
| `client_codename` | character varying(64) | NOT NULL | — |
| `entity` | character varying(32) | NOT NULL | — |
| `id_entity` | integer | NOT NULL | — |
| `lang` | character varying(8) | NOT NULL | — |
| `dimension` | character varying(32) | NOT NULL | — |
| `status` | character varying(16) | NOT NULL | 'todo'::character varying |
| `detail` | text | — | — |
| `last_check` | timestamp with time zone | NOT NULL | now() |
| `source` | character varying(8) | — | — |

### `sy_seo_remediation_log`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_remediation` | integer | NOT NULL | — |
| `client_codename` | character varying(100) | NOT NULL | — |
| `run_at` | timestamp with time zone | NOT NULL | now() |
| `trigger_verdict` | character varying(16) | NOT NULL | — |
| `trigger_reasons` | text | — | — |
| `actions_json` | text | — | — |
| `pct_404_before` | numeric(5,2) | — | — |
| `pct_404_after` | numeric(5,2) | — | — |
| `resolved` | boolean | NOT NULL | false |
| `escalated` | boolean | NOT NULL | false |
| `ship_command` | text | — | — |
| `date_add` | timestamp with time zone | NOT NULL | now() |

### `sy_seo_sentinel_target`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_target` | integer | NOT NULL | — |
| `client_codename` | character varying(100) | NOT NULL | — |
| `site_url` | character varying(255) | NOT NULL | — |
| `gsc_enabled` | smallint | NOT NULL | 1 |
| `auto_remediate` | smallint | NOT NULL | 0 |
| `enabled` | smallint | NOT NULL | 1 |
| `notes` | text | — | — |
| `date_add` | timestamp with time zone | NOT NULL | now() |
| `date_upd` | timestamp with time zone | NOT NULL | now() |
| `slug_quality_enabled` | smallint | NOT NULL | 0 |

### `sy_seo_stopwords`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `lang` | text | NOT NULL | — |
| `word` | text | NOT NULL | — |

### `sy_seo_tracked_keyword`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_keyword` | integer | NOT NULL | — |
| `client_codename` | character varying(100) | NOT NULL | — |
| `keyword` | character varying(255) | NOT NULL | — |
| `target_url` | character varying(500) | — | — |
| `label` | character varying(120) | — | — |
| `source` | character varying(16) | NOT NULL | 'manual'::character varying |
| `is_active` | smallint | NOT NULL | 1 |
| `date_add` | timestamp with time zone | NOT NULL | now() |
| `date_upd` | timestamp with time zone | NOT NULL | now() |


## Engine functions

PL/pgSQL guards that encode the orchestrator's runtime doctrine (jobsite gates, append-only audit, updated_at). Kept auto-contained in the distro: one function that coupled to a comm-only table was dropped with its trigger.

| Function | Args | Returns | Role |
|---|---|---|---|
| `fn_jobsite_done_requires_tasks_complete` | — | trigger | gate: a jobsite may not go `done` with open tasks. |
| `fn_set_updated_at` | — | trigger | trigger: bumps updated_at on row change. |
| `fn_work_order_depends_on_readonly` | — | trigger | guard: deprecated depends_on column is read-only (use sy_work_order_dep). |
| `guard_jobsite_archive_requires_kpi_reached` | — | trigger | gate: a jobsite with an outcome_kpi cannot archive until the KPI is reached. |
| `guard_jobsite_done_requires_guardrail` | — | trigger | gate: a jobsite must transition through status, never INSERT as done/archived. |
| `guard_jobsite_done_requires_outcome_proof` | — | trigger | gate: closing a jobsite requires an outcome proof. |
| `is_safe_regex` | p text | boolean | validates a stored regex pattern (CHECK on sy_reflex). |
| `set_scar_guardrail_default` | — | trigger | trigger: defaults a scar's guardrail at INSERT. |

---
_Generated by `02_atlas/workers/release/sy_db_schema_doc.py` from 69 tables + 8 functions. Edit bootstrap.sql, then regenerate — never edit this page._
