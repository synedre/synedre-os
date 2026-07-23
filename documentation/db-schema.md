<!-- AUTO-GENERATED from core/shyrka/bootstrap.sql by sy_db_schema_doc.py -- DO NOT EDIT. Regenerate after bootstrap.sql changes. -->

# Database schema — `shyrka`

The Synedre OS orchestrator core schema. DDL-only (no data), generated from `core/shyrka/bootstrap.sql` over a 69-table whitelist + 8 engine functions. This page is reference (Layer 2 of the doc-doctrine, ADR-0001) — for *why* a table exists, see its COMMENT and the ADRs; for *how* to use it, see the in-code docstrings (Layer 1).

_Legend: 36/69 tables and 86 columns carry a COMMENT (the engine's doctrine, kept verbatim). `NOT NULL` and `DEFAULT` are surfaced; constraint clauses (PK/FK/CHECK) are in bootstrap.sql, not repeated here._

## Sessions & runtime

### `sy_user`

> Modèle utilisateur centralisé (inspiré Honcho) — remplace les memory/user_*.md éparpillés. Source unique pour contexte utilisateur injecté dans sessions Claude.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_user` | integer | NOT NULL | — |
| `codename` | character varying(64) | NOT NULL | — |
| `full_name` | text | NOT NULL | — |
| `dimensions` | jsonb | NOT NULL | '{}'::jsonb |
| `created_at` | timestamp with time zone | NOT NULL | now() |
| `updated_at` | timestamp with time zone | NOT NULL | now() |

Column notes:
- **`dimensions`** — Arbre JSONB : profile, communication_style, schedule, skills, history, preferences, private_only_for_alex.

### `sy_claude_session`

> Index metadata des sessions Claude Code (.jsonl) — Phase UI-7 cockpit. Full content reste sur filesystem ~/.claude/projects/<project>/<uuid>.jsonl, accessible via endpoint streaming.

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

> Entité de premier rang RUN. Source unique de /hub/runs (runs-only). Les 2 sources (atlas-inbox via email intent=run, console via chat) écrivent ici. Les emails intent question/chantier/noise NE deviennent PAS des runs.

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
- **`source`** — Origine du run : atlas-inbox (email) | console (chat). Affiché en colonne Source.
- **`trigger`** — Mécanisme déclencheur : email | chat | cron.
- **`scope`** — Périmètre : shyrka | <codename tenant>. NULL si non dérivable (cas inbox).
- **`ref_type`** — Type de la ref polymorphe : atlas_email (id_atlas_email) | brainstorm_job_thread (uuid thread console).
- **`ref_id`** — Identifiant polymorphe : id_atlas_email pour atlas-inbox, uuid thread pour console.

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

> Taches deleguees aux agents depuis cockpit /hub/ (Phase UI-1 synedre-os-cockpit, 2026-05-16). Worker daemon = Phase UI-2.

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
- **`codename`** — Slug unique kebab-case, identifie la run dans logs et URL /hub/runs/<codename>.
- **`agent_codename`** — FK logique vers sy_agents.codename.
- **`perimeter`** — JSON list de chemins fichiers/dirs autorises a l agent (sandboxing).
- **`exit_criteria`** — Texte libre conditions de fin attendues par operateur.
- **`status`** — pending | running | completed | failed | cancelled
- **`output_log`** — Streamed stdout/stderr concat ephemere peut etre tronque.

### `sy_autonomy_window`

> Fenêtre autonomie par jour (dow 0=lundi..6=dimanche, aligné datetime.weekday()). start_hour->end_hour (wrap minuit si start>end). enabled=false coupe le démarrage ce jour. Édité par /autonomie + /hub/autonomie. Chantier autonomie-horaire.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `dow` | smallint | NOT NULL | — |
| `jour` | character varying(10) | NOT NULL | — |
| `start_hour` | smallint | NOT NULL | 19 |
| `end_hour` | smallint | NOT NULL | 4 |
| `enabled` | boolean | NOT NULL | true |
| `date_upd` | timestamp with time zone | NOT NULL | now() |


## Chantier, travail & tâche

### `sy_chantier`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_chantier` | integer | NOT NULL | — |
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
- **`archived_at`** — Soft archive. NULL = actif (filtre UI par défaut). Renseignée = archivé (RAG searchable préservé).
- **`mission_letter`** — Lettre de mission markdown structurée (contexte/objectifs/scope/critères/contraintes/briefing-équipes). Optionnelle. Injectée conditionnellement dans persona + qa_run (travail #161).
- **`scope`** — Périmètre projet (synedre|codemyshop-oss|codemyshop-enterprise|tenant|business). Distinct de client_id qui désigne le tenant cible. Affiché comme badge sur /hub/chantier.
- **`preprod_test_plan`** — Markdown libre : URLs preprod à valider, commandes <TENANT>, checks visuels. Affiché par /chantier <codename> quand status=test. Doctrine review-chantier-only 2026-05-18.
- **`ship_command`** — Commande exacte à exécuter pour clôturer le chantier (ex: ./ship synedre-os, ./ship <TENANT>-v2, ./ship all). Affiché par /chantier <codename> quand status=test.
- **`external_contacts`** — CSV emails (ex: julien.tchoryk@<TENANT>.com,xavier.tostivint@<TENANT>.com) à surveiller proactivement par Marco Polo (agent veille). Cron sy_dream feature_8 scan sy_inbox_emails J-7 → matche → unpause + tâche @veille si activité.
- **`auto_explode`** — Si TRUE et travail discovery du chantier passe done, déclenche pipeline LLM sy_chantier_explode_discovery pour créer les travaux Phase A/B/C automatiquement. Kill-switch DB doctrine 2026-05-20 chantier auto-explode-discovery.
- **`qa_verdict`** — Verdict de l'orbite QA en phase test : green|red|incomplete|pending. green + auto-closable → done.
- **`qa_proof_path`** — Chemin de la preuve QA 3 axes (sy_run_qa) produite par l'orbite — zéro faux-vert.
- **`auto_deployed_at`** — Dernier ./deploy AUTO réussi lancé par sy_autonomie_tick (cible non-cliente). Throttle : le tick passe chaque heure dans la fenêtre 19h-4h et redéploierait sinon ~10×/nuit un chantier en test. Seul un deploy rc=0 tamponne — un échec doit pouvoir rejouer. NULL = jamais auto-déployé.
- **`preferred_dows`** — Jours de semaine (0=lundi..6=dimanche, aligné datetime.weekday()) où ce chantier est éligible à une run autonome. NULL = éligible tout jour où sy_autonomy_window est ouverte (comportement historique). Chantier #504.

### `sy_chantier_travail`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_travail` | integer | NOT NULL | — |
| `id_chantier` | integer | NOT NULL | 0 |
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
| `conduite_slug` | character varying(128) | — | — |
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
| `resolves_travail_id` | integer | — | — |
| `depends_on_travail_id` | integer | — | — |
| `runner` | character varying(32) | — | — |
| `auto_disabled_at` | timestamp with time zone | — | — |
| `auto_disabled_reason` | text | — | — |
| `auto_timeout_count` | integer | NOT NULL | 0 |

Column notes:
- **`review_notified_at`** — Date push email fondateur quand travail bascule en review. NULL = pas encore notifié.
- **`mode_auto`** — Si TRUE, la skill /chantier <code> -tr <travail> --auto enchaîne automatiquement les tâches todo sans intervention. Stop conditions : fail tâche, scope creep, deploy KO. Travail #157.
- **`qa_iteration_count`** — Compteur d itérations QA déclenchées en mode --auto (travail #159). Max 3 sinon STOP escalade fondateur.
- **`resolves_travail_id`** — Si NOT NULL, ce travail-bis résout le travail référencé (cible = status=paused). Quand le bis passe done, cascade auto : paused→done + tâches todo→cancelled + append decision_json « resolved by bis ». Chantier #57 doctrine 2026-05-20.
- **`depends_on_travail_id`** — DEPRECATED (tache #974, 2026-05-24): migré vers sy_travail_dep (DAG N:M). Col conservée READ-ONLY pour 1 release. Lire depuis sy_travail_dep, écrire via INSERT/DELETE sy_travail_dep. Trigger trg_travail_depends_on_readonly bloque toute écriture non-NULL.
- **`auto_disabled_at`** — Coupe-circuit anti-runaway : tamponné par sy_task_worker quand il désarme mode_auto sur rc!=0 / qa=fail. NOT NULL = désarmement délibéré, le tick d'autonomie ne ré-arme JAMAIS. NULL = jamais armé, propagation depuis chantier.mode_auto autorisée. Purgé par le réarmement manuel (run-auto / bouton ▶).
- **`auto_disabled_reason`** — Raison du désarmement anti-runaway (ex "rc=1 + qa=fail"). Traçabilité : sans elle, « mode_auto=false » ne dit pas POURQUOI et le prochain lecteur re-arme à l'aveugle.

### `sy_chantier_agent`

> Équipes recrutées par chantier — role production/validation (travail #159).

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_assignment` | integer | NOT NULL | — |
| `id_chantier` | integer | NOT NULL | — |
| `agent_codename` | character varying(64) | NOT NULL | — |
| `role` | character varying(32) | NOT NULL | — |
| `"position"` | integer | NOT NULL | 0 |
| `date_assigned` | timestamp with time zone | NOT NULL | now() |
| `date_unassigned` | timestamp with time zone | — | — |
| `notes` | text | — | — |

### `sy_chantier_claude_session`

> Travail #165 — 1 chantier = 1 session Claude Code (UUID jsonl ~/.claude/projects/-home-ubuntu-synedre-os/). Cap 3 actives concurrentes hors sycl-default.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_session` | integer | NOT NULL | — |
| `id_chantier` | integer | NOT NULL | — |
| `jsonl_uuid` | uuid | NOT NULL | — |
| `started_at` | timestamp with time zone | NOT NULL | now() |
| `last_active_at` | timestamp with time zone | NOT NULL | now() |
| `status` | character varying(16) | NOT NULL | 'active'::character varying |
| `size_bytes` | bigint | — | — |
| `closed_at` | timestamp with time zone | — | — |
| `closed_reason` | character varying(32) | — | — |

### `sy_chantier_lock`

> Lock par chantier pour empêcher 2 sessions Claude Code sur LE MEME chantier. TTL 30 min auto-cleanup via cron + auto-release au Stop hook. Doctrine 2026-05-20 chantier #58.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_chantier` | integer | NOT NULL | — |
| `session_id` | character varying(64) | NOT NULL | — |
| `terminal_pid` | integer | — | — |
| `hostname` | character varying(64) | — | — |
| `opened_at` | timestamp with time zone | NOT NULL | now() |
| `last_activity` | timestamp with time zone | NOT NULL | now() |
| `owner_kind` | character varying(8) | NOT NULL | 'user'::character varying |

Column notes:
- **`session_id`** — Identifiant unique session Claude Code. Source ordre: env CLAUDE_SESSION_ID > sha256(tty) > pid-user@host.

### `sy_chantier_readiness`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_readiness` | integer | NOT NULL | — |
| `id_chantier` | integer | NOT NULL | — |
| `verdict` | character varying(16) | NOT NULL | — |
| `score` | integer | NOT NULL | 0 |
| `reasons` | text | — | — |
| `missing` | text | — | — |
| `enriched` | text | — | — |
| `action_taken` | character varying(32) | — | 'none'::character varying |
| `chantier_status_at_run` | character varying(32) | — | — |
| `mode_auto_at_run` | boolean | — | — |
| `total_taches` | integer | — | — |
| `assignees` | integer | — | — |
| `date_add` | timestamp with time zone | — | now() |
| `date_upd` | timestamp with time zone | — | now() |

### `sy_chantier_qa_run`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_run` | integer | NOT NULL | — |
| `id_chantier` | integer | NOT NULL | — |
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

### `sy_chantier_relevance`

> Dernier verdict de pertinence par chantier (heuristique + LLM). Source unique pour le bouton audit /hub/chantier. Chantier #129 — 2026-05-26.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_relevance` | integer | NOT NULL | — |
| `id_chantier` | integer | NOT NULL | — |
| `verdict` | character varying(16) | NOT NULL | — |
| `confidence` | numeric(3,2) | NOT NULL | — |
| `rationale` | text | NOT NULL | — |
| `source` | character varying(16) | NOT NULL | — |
| `chantier_status_at_run` | character varying(16) | NOT NULL | — |
| `total_taches` | integer | — | — |
| `done_taches` | integer | — | — |
| `age_days` | integer | — | — |
| `llm_model` | character varying(64) | — | — |
| `llm_input_tokens` | integer | — | — |
| `llm_output_tokens` | integer | — | — |
| `id_audit_job` | integer | — | — |
| `date_add` | timestamp with time zone | NOT NULL | now() |
| `date_upd` | timestamp with time zone | NOT NULL | now() |

### `sy_chantier_tache`

> 3e niveau hierarchie chantier (tenant -> travail -> tache). Phase UI-9 cockpit synedre-os-cockpit.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_tache` | integer | NOT NULL | — |
| `id_travail` | integer | NOT NULL | — |
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
- **`status`** — todo → doing → testing → done | iterating (retour si test KO) | cancelled
- **`priority`** — P0 | P1 | P2 | P3
- **`iteration_count`** — Incrémenté à chaque cycle testing→iterating. 0 = première tentative.
- **`last_test_result`** — pass | fail | inconclusive
- **`scope`** — Zone d'impact pour calibrer l'estimateur LLM (cicatrice #6). 7 valeurs canoniques : synedre-internal, codemyshop-oss, codemyshop-enterprise, tenant-single, tenant-multi, infra, doctrine. NULL = legacy avant travail #154.
- **`visual_intent`** — 火眼金睛 : ce qui doit être VISIBLE à l'écran après le changement (déclaré à la création). NULL = tâche non-visuelle.
- **`visual_url`** — 火眼金睛 : URL où vérifier le rendu (NULL = staging du chantier). Cf sy_huoyan_<TENANT> --chantier.
- **`recommended_model_orient`** — Override GLM par tache quand le chantier est en doctrine_camp=orient. NULL = derive du tier via _GLM_TIER_MAP. Distinct de recommended_model (tier Anthropic) pour que la bascule entre camps reste reversible. Chantier #508 tache #123732.

### `sy_chantier_tool`

> Outils disponibles sur un chantier (tenant). id_chantier=NULL = outil par defaut global, sinon attache custom.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_tool` | integer | NOT NULL | — |
| `id_chantier` | integer | — | — |
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
- **`tool_type`** — skill (slash command) | automate (synedre/sy_*.py) | endpoint (api call) | custom (ad hoc)
- **`config_json`** — Config specifique (target_url, args, etc.) selon tool_type.

### `sy_tache_dep`

> DAG N:M deps intra-travail entre tâches — id_tache_blocked ne peut démarrer tant que id_tache_blocker n'est pas done

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_dep` | integer | NOT NULL | — |
| `id_tache_blocked` | integer | NOT NULL | — |
| `id_tache_blocker` | integer | NOT NULL | — |
| `date_add` | timestamp without time zone | NOT NULL | now() |

Column notes:
- **`id_tache_blocked`** — Tâche bloquée (dépend de id_tache_blocker)
- **`id_tache_blocker`** — Tâche bloqueur (doit être done avant que id_tache_blocked puisse démarrer)

### `sy_tache_iteration`

> Pattern ReAct (Yao 2022) : cycle Reasoning + Acting + Observation par itération de tâche. iteration_n=1 = première tentative, incrément à chaque retour testing→iterating.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_iteration` | integer | NOT NULL | — |
| `id_tache` | integer | NOT NULL | — |
| `iteration_n` | integer | NOT NULL | — |
| `agent_codename` | character varying(64) | — | — |
| `reason` | text | — | — |
| `action` | text | — | — |
| `observation` | text | — | — |
| `test_result` | character varying(16) | — | — |
| `tools_used` | text | — | — |
| `duration_ms` | integer | — | — |
| `date_add` | timestamp with time zone | NOT NULL | now() |
| `id_cicatrice` | integer | — | — |
| `tokens_used` | integer | — | — |

Column notes:
- **`reason`** — Raisonnement de l agent : pourquoi cette action ?
- **`action`** — Action prise (tool call, code change, message…)
- **`observation`** — Résultat observé (output, erreur, état après)
- **`test_result`** — pass | fail | inconclusive | skip
- **`tools_used`** — JSON array de slugs sy_chantier_tool utilisés dans cette itération.
- **`id_cicatrice`** — FK logique vers sy_cicatrices.id_cicatrice (déjà existante avec 642 cic). NULL = itération sans cicatrice (succès direct ou skip). Renseignée quand test_result=fail et la leçon a été gravée.

### `sy_tache_skill`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_tache_skill` | integer | NOT NULL | — |
| `id_tache` | integer | NOT NULL | — |
| `skill_name` | character varying(64) | NOT NULL | — |
| `"position"` | integer | NOT NULL | 0 |
| `date_add` | timestamp with time zone | NOT NULL | now() |

### `sy_tache_tool`

> N-N tâche ↔ outils utilisés. Trace : quel outil a servi à réaliser quelle tâche.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_tache_tool` | integer | NOT NULL | — |
| `id_tache` | integer | NOT NULL | — |
| `id_tool` | integer | NOT NULL | — |
| `"position"` | integer | NOT NULL | 0 |
| `used_at` | timestamp with time zone | — | — |
| `notes` | text | — | — |
| `date_add` | timestamp with time zone | NOT NULL | now() |

### `sy_travail_agent`

> N-N travail ↔ agents : qui bosse sur ce travail. is_lead=1 = orchestrateur (max 1 par travail recommandé).

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_assignment` | integer | NOT NULL | — |
| `id_travail` | integer | NOT NULL | — |
| `agent_codename` | character varying(64) | NOT NULL | — |
| `role` | character varying(64) | — | — |
| `is_lead` | smallint | NOT NULL | 0 |
| `"position"` | integer | NOT NULL | 0 |
| `date_assigned` | timestamp with time zone | NOT NULL | now() |
| `date_unassigned` | timestamp with time zone | — | — |
| `notes` | text | — | — |

### `sy_travail_dep`

> DAG N:M deps entre travaux — id_travail_blocked ne peut demarrer tant que id_travail_blocker n'est pas done

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_travail_blocked` | integer | NOT NULL | — |
| `id_travail_blocker` | integer | NOT NULL | — |
| `date_add` | timestamp without time zone | NOT NULL | now() |

Column notes:
- **`id_travail_blocked`** — Travail bloque (depend de id_travail_blocker)
- **`id_travail_blocker`** — Travail bloqueur (doit etre done avant que id_travail_blocked puisse demarrer)

### `sy_travail_review`

> Review fondateur d un travail (déclenchée quand toutes les tâches sont done). 1 travail = N reviews (re-review si rejected → cicatrice gravée → retour dev → re-review).

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_review` | integer | NOT NULL | — |
| `id_travail` | integer | NOT NULL | — |
| `iteration_n` | integer | NOT NULL | — |
| `status` | character varying(16) | NOT NULL | 'pending'::character varying |
| `reviewed_by` | character varying(64) | — | — |
| `notes` | text | — | — |
| `id_cicatrice` | integer | — | — |
| `date_add` | timestamp with time zone | NOT NULL | now() |
| `date_upd` | timestamp with time zone | NOT NULL | now() |

Column notes:
- **`status`** — pending (en attente) | validated (✓) | rejected (✗ → cicatrice)
- **`id_cicatrice`** — FK logique vers sy_cicatrices.id_cicatrice (renseignée si status=rejected).


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

> Events stream-json des spawns Claude Code, généralisée multi-source (email/chantier/task_run/manual). Chantier #92 multi-agent-cockpit. Capture fine du raisonnement agents pour cockpit live + roadmap F9 self-improving.

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
- **`agent_codename`** — Codename de l'agent qui émet l'event (sy_agents.codename). Atlas pour les sources email, peut être turing/lovelace/mitnick/etc. pour les sources chantier.
- **`source_type`** — Type de source qui a déclenché ce spawn : email (Atlas Inbox), chantier (--auto), task_run (sy_task_run worker), manual (CLI interactive).
- **`source_id`** — BIGINT FK polymorphe vers la table de la source (id_atlas_email pour email, id_chantier pour chantier, id_task_run pour task_run, id_session pour manual).

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

> N-N agent ↔ skills. is_default=1 = compétence native ; sinon acquise. acquired_from_travail = trace du chantier qui a apporté la skill.

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_agent_skill` | integer | NOT NULL | — |
| `agent_codename` | character varying(64) | NOT NULL | — |
| `skill_slug` | character varying(64) | NOT NULL | — |
| `is_default` | smallint | NOT NULL | 0 |
| `acquired_from_travail` | character varying(64) | — | — |
| `acquired_at` | timestamp with time zone | NOT NULL | now() |
| `mastery_level` | smallint | — | 1 |
| `notes` | text | — | — |
| `date_upd` | timestamp with time zone | NOT NULL | now() |

Column notes:
- **`mastery_level`** — 1-5 (1=débutant, 5=maître). Augmente avec l usage.

### `sy_agent_tool`

> Registre des outils CLI Claude Code dont dispose Atlas (spawn bypassPermissions, sans restriction --allowedTools). builtin = garanti ; mcp = conditionnel (dépend des serveurs MCP en settings au spawn).

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

> Routing IA canonique (chantier #191). Lu par sy_ai_provider.py (Python) et ai-gateway.ts (TS). Remplace ai-routing.yaml.

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

### `sy_automate_conduites`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_automate` | integer | NOT NULL | — |
| `conduite_slug` | character varying(128) | NOT NULL | — |
| `step_position` | integer | NOT NULL | 0 |
| `date_add` | timestamp with time zone | NOT NULL | now() |

### `sy_automate_llm_run`

> Cout $ + tokens + modele par execution des automates cron LLM hors chantiers autonomes (sy_agent_event ne couvre que brainstorm/chantier/email). Chantier #505.

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

> Registre des crons supervisés + leur dernier battement de cœur. Le battement est écrit PAR LE SCRIPT lui-même (synedre/sy_cron_beat.py), JAMAIS par la ligne de crontab : un beat accolé en `; beat` aurait rapporté « vivant » le 2026-07-17 alors que python n'avait jamais tourné (le sourcing échouait, le && cassait avant). Le beat prouve que le SCRIPT s'est exécuté, pas que cron a tiré. Lu par synedre/sy_cron_deadman.py. Chantier #465.

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
- **`script_name`** — Nom du script SANS chemin ni extension (ex: sy_whatsapp_to_<TENANT>). Clé d'identité partagée entre le beat (écriture) et le détecteur (lecture).
- **`registered_at`** — Date d'inscription au registre. INDISPENSABLE : sans elle, une ligne jamais battue (last_beat_at NULL) n'a pas d'âge et le détecteur ne peut pas dire depuis quand elle est morte. Or le cron MORT-NÉ (câblé de travers, jamais exécuté une seule fois) est précisément la panne du 2026-07-17 — le cas le plus important à attraper.
- **`last_beat_at`** — Dernier battement. NULL = ce script n'a JAMAIS battu depuis registered_at : mort-né, pas « en attente ». Le détecteur mesure alors le silence depuis registered_at.
- **`last_status`** — ok | fail — état du DERNIER run. Complète sy_cron_errors : `fail` = le script a tourné et mal fini (il bat quand même, il est vivant) ; un silence = il n'a pas tourné du tout. Deux pannes différentes, deux signaux différents.
- **`expected_interval_s`** — Cadence nominale déclarée, en secondes (ex: 15 pour sy_whatsapp_to_<TENANT> = 4 lignes crontab décalées 0/15/30/45s ; 60 pour un * * * * * simple). DÉCLARÉE et non déduite du crontab : explicite > magique, et le crontab n'est pas git-tracké.
- **`max_silence_s`** — Seuil de mort : au-delà de ce silence, le script est déclaré mort. Seuil ABSOLU en secondes plutôt qu'un facteur multiplicatif — un facteur 3 sur un cron à 15s alerterait au bout de 45s, soit au moindre hoquet. Chaque cron déclare la fenêtre d'absence qui compte VRAIMENT pour lui. CHECK: doit dépasser expected_interval_s.
- **`last_alerted_at`** — Dernière alerte émise pour ce script. Anti-spam : sans ça le détecteur ré-alerterait à chaque passage pour le même mort. Un garde qui bruit meurt socialement (Alex filtre, puis n'ouvre plus) — le cas nul (registre tout vert = ZÉRO email) est un livrable.
- **`active`** — FALSE = supervision suspendue (cron volontairement éteint). Ne pas supprimer la ligne pour faire taire une alerte : on perdrait registered_at et l'historique.


## Doctrine, cicatrices & introspection

### `sy_conscience_health`

> Bilan de santé nocturne de Shyrka : agrégat des audits par dimension. Chantier #182 Phase 2. Read-only.

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

> Angles morts doc de Shyrka : façades réelles non couvertes par un chapitre. #182 Phase 5. Read-only.

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

> Miroir nocturne de Shyrka : écart doc(proprioception)↔code(corps). Chantier #182 Phase 0. Read-only.

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

> Feature regard-des-autres (#192) : revues doc publique par modèles externes, gatées anti-injection.

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
| `cicatrice_id` | integer | — | — |
| `submitted_by` | text | — | — |
| `created_at` | timestamp with time zone | NOT NULL | now() |
| `processed_at` | timestamp with time zone | — | — |

Column notes:
- **`prompt_generated`** — HTML public scrubbé issu de sy_doc_chapter UNIQUEMENT. Jamais de contenu .md interne.
- **`external_response`** — Réponse du modèle externe collée par l'humain. Cap 50k chars enforced côté endpoint POST.
- **`injection_attempt_detected`** — Calculé par claude -p sandbox. Si true : log severity=high sy_daily_meet, aucune action.

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

### `sy_cicatrices`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id_cicatrice` | integer | NOT NULL | — |
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
| `id_chantier` | integer | — | — |
| `dup_signature` | character varying(160) | — | — |
| `duplicate_count` | integer | NOT NULL | 0 |
| `last_dup_at` | timestamp with time zone | — | — |

Column notes:
- **`error_type`** — Taxonomie close : frontend_ui, i18n, api_contract, db_schema, auth_session, deploy_propagation, automation_silent_fail, routing_seo, naming_convention, legacy_cleanup, infra_git, email_imap, accessibility, tenant_isolation, data_quality, other. Legacy: convention (à requalifier via sy_cicatrice_qualify.py).
- **`severity`** — low | medium | high | critical (CHECK chk_cicatrices_severity).
- **`error_type_proposed`** — Catégorie proposée par LLM-qualify (à committer dans error_type après review humaine).
- **`qualify_confidence`** — Confiance 0.00-1.00. <0.70 = review humaine requise avant commit error_type=error_type_proposed.
- **`qualify_reasoning`** — Justification 1-ligne du LLM (audit trail).
- **`tags`** — Axes orthogonaux : tenant, env, priorité, domaine. Recherche via @> (array contains).
- **`dup_signature`** — Signature canonique auto-only (format auto:<pattern_id>@<agent_codename>). NULL = chemin non-auto (victoire, fail_tache manuel, publish) → dédup désactivée. Chantier dédup cicatrices (run mode plan).
- **`duplicate_count`** — Occurrences regravées absorbées par la dédup auto (NOT NULL DEFAULT 0). Compteur INDEPENDANT de recall_count (qui mesure les servies).
- **`last_dup_at`** — Timestamp de la dernière occurrence absorbée. NULL tant qu'aucun doublon n'a été vu.

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

> Réflexes décentralisés — règles de garde actives (pont settings.json → DB → décision).

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

> Trace de toutes les décisions prises par la façade sy_reflex.py.

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

> Staging INERTE des propositions de réflexe (organe immunité adaptative, #230). JAMAIS lu par sy_reflex.py (qui ne lit que sy_reflex WHERE active=1 AND tier=bras). Pas de colonne active : aucun arming accidentel possible. Promotion = arm() humain gaté.

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
- **`evidence`** — Cicatrices sources : {cluster_id, member_ids:[...], samples:[{id,error_type,desc}], recall, recency}. Une proposition sans evidence est refusée (vecteur V3).
- **`status`** — pending → reviewed (Mitnick a tranché) → promoted (armé dans sy_reflex, geste Alex) | rejected. Le CHECK chk_reflex_proposal_arming_gate interdit promoted sans revue clean.
- **`mitnick_verdict`** — Verdict de la revue sécurité (agent Mitnick) AVANT tout arming. clean = sûr à armer ; flagged = refusé. NULL = pas encore revu.


## Lexicon & LLM pricing

### `sy_lexicon`

> Registre canonique ops-interne du vocabulaire Synedre OS (statuts, identifiants, verbes). Source de vérité après chargement. Périmètre : ops uniquement — aucun vocabulaire produit/SEO (→ sy_dictionary). Chantier #174 lexique-canonique-ops, tâche #1480.

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
- **`statuts_autorises`** — Tableau jsonb des valeurs autorisées pour la colonne cible (ex: [\"planning\",\"dev\",...]). NULL si non applicable.
- **`synonymes_interdits`** — Tableau jsonb des synonymes à bannir (ex: [\"state\",\"etat\"]). NULL si non applicable.
- **`entry_scope`** — Portée de l'entrée. Valeur seed = 'ops-interne'. Nommé entry_scope (pas scope) pour éviter confusion avec scope métier.
- **`check_db_cible`** — true = entree adossee a un CHECK DB sur colonne_cible (statuts/scope contraints, enforcement triple registre+CHECK+linter) ; false = linter-seul (verbes CLI deploy/ship, identifiants codename/slug/id sans enum). Dette P3 chantier #174.

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

> Usage API IA par appel (tokens+coût) — imputation/refacturation par tenant (Pacioli). Alimenté par sy_ai_provider._meter_usage.

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

> Canaris uptime par TYPE de page (tolérance zéro) — 1 URL représentative par type et par tenant prod. Lu par sy_canary_monitor.py.

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

> Faits marque VÉRIFIÉS par tenant (grounding SEO). Multi-tenant : zéro tenant en dur dans le code. RÈGLE DURE 4 invariants.

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
- **`authority_url`** — Lien autorité externe (EEAT) injecté déterministiquement — éditorial, fourni par le tenant (jamais halluciné).
- **`sector_topics`** — Angles lexicaux du vertical (injectés dans les prompts contenu) — ex food: calibre, conditionnement, conservation. Multi-tenant: jamais de vertical en dur dans le moteur.

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

> Snapshot quotidien de couverture SEO source FR (id_lang=1). Chantier #228.

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

> Suivi couverture SEO i18n (slug/nom/meta/h1 traduits) par tenant/langue/entité/champ. Alimenté par sy_audit_seo_i18n (cron shyrka). Complète sy_seo_health_history (sentinel #197).

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

PL/pgSQL guards that encode the orchestrator's runtime doctrine (chantier gates, append-only audit, updated_at). Kept auto-contained in the distro: one function that coupled to a comm-only table was dropped with its trigger.

| Function | Args | Returns | Role |
|---|---|---|---|
| `fn_chantier_done_requires_tasks_complete` | — | trigger | gate: a chantier may not go `done` with open tasks. |
| `fn_set_updated_at` | — | trigger | trigger: bumps updated_at on row change. |
| `fn_travail_depends_on_readonly` | — | trigger | guard: deprecated depends_on column is read-only (use sy_travail_dep). |
| `guard_chantier_archive_requires_kpi_reached` | — | trigger | gate: a chantier with an outcome_kpi cannot archive until the KPI is reached. |
| `guard_chantier_done_requires_guardrail` | — | trigger | gate: a chantier must transition through status, never INSERT as done/archived. |
| `guard_chantier_done_requires_outcome_proof` | — | trigger | gate: closing a chantier requires an outcome proof. |
| `is_safe_regex` | p text | boolean | validates a stored regex pattern (CHECK on sy_reflex). |
| `set_cicatrice_guardrail_default` | — | trigger | trigger: defaults a cicatrice's guardrail at INSERT. |

---
_Generated by `02_atlas/workers/release/sy_db_schema_doc.py` from 69 tables + 8 functions. Edit bootstrap.sql, then regenerate — never edit this page._
