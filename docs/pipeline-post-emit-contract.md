# Post-Emit Pipeline Step Contract

This document makes explicit the implicit call chain that runs after a card is
emitted in `engine/laya/pipeline/emit.py`. It describes the *current* behavior
as an ordering/dependency contract — it is not a proposal for a new interface.
See [issue #13](https://github.com/kushin77/laya/issues/13).

## Summary of the real order

The chain is driven entirely by `run_emit()` in `emit.py`. Steps execute in
this order:

1. `_persist_card` — synchronous, in the emit transaction
2. `_count_siblings` → `is_carry_forward` flag
3. `_auto_resolve_terminal_siblings` — best-effort
4. `_embed_card` — synchronous
5. `_broadcast_card` — synchronous, **before** grouping/resolution
6. `_resolve_context_grouping` (→ `context_grouping.py`) — synchronous
7. `resolve_semantic_entities` (→ `entity_resolution.py`) — synchronous
8. `log_to_audit`
9. `_trigger_followups` — fires detached, non-blocking tasks

**This corrects the ordering implied by the issue title.** The issue names
the order as `entity_resolution -> context_grouping -> group_summary ->
omni/omni_change`. The actual order is the reverse for the first two:
**context_grouping runs before entity_resolution**, both synchronously inside
`run_emit()`. `group_summary` and `omni` are not part of this synchronous
chain at all — see below.

## Step-by-step contract

### 1. `_persist_card` (emit.py:181)
- **Consumes:** the incoming card payload.
- **Produces:** INSERT/UPDATE into `action_cards`; INSERT OR IGNORE into
  `omni_queue` in the same transaction; bumps `group_active_at`.
- **Downstream coupling:** this is the omni enqueue point. Omni is **not**
  called synchronously — it is enqueued for a separate consumer (see Omni,
  below).
- **Skip condition:** if `_skip_summaries(event_id)` is set (reprocess flag),
  the `omni_queue` insert is skipped, as are the `group_summary` and daily
  summary triggers in step 9. `entity_resolution` and `context_grouping`
  still run.

### 2–3. Sibling counting / auto-resolve
- `_count_siblings` sets `is_carry_forward`, which gates both
  `_auto_resolve_terminal_siblings` (step 3) and the `group_summary` trigger
  in step 9.

### 4. `_embed_card` (emit.py:352)
- **Produces:** writes `thread_context`; embeds the card into ChromaDB;
  returns `embed_text`.
- `embed_text` is passed forward into both context grouping (step 6) and
  entity resolution (step 7) — this is the shared input that couples them.

### 5. `_broadcast_card`
- Publishes `card_created`/`card_updated` over the websocket.
- Deliberately runs **before** context grouping and entity resolution so the
  UI update isn't blocked on their (potentially LLM-backed) latency — see
  emit.py:745-749.

### 6. Context Grouping (`context_grouping.py`)
- **Called via:** `_resolve_context_grouping`, calling
  `resolve_context_group` or `assign_or_join_context_group`.
- **Signatures:**
  - `resolve_context_group(*, card_id, entity_id, embed_text, space_id, platform, entity_refs) -> str | None`
  - `assign_or_join_context_group(card_id, matched_card_id, label, space_id, *, entity_refs, matched_entity_refs) -> str | None`
- **Consumes:** `embed_text` from step 4, entity refs already known at emit
  time.
- **Produces:** a context group id; does not write it itself — the caller in
  `emit.py` updates `action_cards.context_id`. Reads ChromaDB for semantic
  matching.
- **Skip condition:** gated by the `smart_grouping.context_association`
  setting (default true).
- **Runs before entity resolution.** Does not call entity_resolution,
  group_summary, or omni directly.

### 7. Entity Resolution (`entity_resolution.py`)
- **Called via:** `resolve_semantic_entities(card_id, embed_text, entity_values) -> None`.
- **Consumes:** `embed_text` from step 4, the context group id assigned in
  step 6, and `entity_values` extracted from the card.
- **Produces:** semantic entity links, via `_create_semantic_link`
  internally. Best-effort — exceptions are swallowed (emit.py:787-790).
- **Runs after context grouping**, and does not call context_grouping,
  group_summary, or omni directly.

### 8. `log_to_audit`
- Writes the audit trail entry for the emit.

### 9. `_trigger_followups` (emit.py:571)
- Fires three **detached, non-blocking** `asyncio.create_task` calls (none
  are awaited by `run_emit()`, so failures here do not affect the emit
  response):
  - `group_summary.trigger_group_summary_update(entity_id, card_id, space_id)`
    — only if `is_carry_forward` (from step 2) and summaries aren't skipped.
  - `summarize.trigger_summary_update` — daily summary.
  - `processing_rules.run_processing_rules`.

### Group Summary (`group_summary.py`)
- **Entry point:** `trigger_group_summary_update` (group_summary.py:49),
  debounced via `_debounced_group_summary`.
- **Consumes:** `entity_id`, `card_id`, `space_id` — not `embed_text` or any
  output of context_grouping/entity_resolution directly; it re-reads what it
  needs from `action_cards`/`group_summaries`.
- **Produces:** writes to the `group_summaries` table; may cascade to a
  context-group-level summary via `_cascade_to_context_group`.
- **Not part of the synchronous emit chain** — runs as a detached task, and
  only when `is_carry_forward` is true.

### Omni (`omni.py`) and Omni Change (`omni_change.py`)
- Omni is **not called from `emit.py` at all**. It is enqueued via the
  `omni_queue` row written in step 1, and consumed independently by a
  separate poller (`start_omni_processor` → `_queue_loop` →
  `_process_queue`, omni.py:347-421).
- `_process_queue` (omni.py:359) reads `omni_queue` joined with
  `action_cards`, groups by space, and drives snapshot/delta logic
  (`_load_full_snapshot`, `_compute_delta`, `_apply_delta`), deleting
  processed rows from `omni_queue` when done.
- `omni_change.py` is **not an independent pipeline step**. It is a
  pure-function helper module (`compute_incremental_change_summary`,
  `compute_resynthesis_change_summary`, `merge_change_summaries`, etc.)
  imported and called internally by `omni.py` (omni.py:35). The issue title's
  "omni/omni_change" refers to omni's internal use of this helper, not a
  separate step in the chain.

## Coupling summary (who calls whom directly)

- `emit.py` → `context_grouping.py` (sync)
- `emit.py` → `entity_resolution.py` (sync, after context_grouping)
- `emit.py` → `group_summary.py` (detached task, conditional on carry-forward)
- `emit.py` → `summarize.py`, `processing_rules.py` (detached tasks)
- `emit.py` → `omni_queue` table (enqueue only, no direct call)
- omni queue consumer (`omni.py`) → `omni_change.py` (internal helper import)

No step among context_grouping, entity_resolution, group_summary, or omni
calls any of the others directly — the only real coupling is through shared
inputs (`embed_text`, `card_id`, `entity_id`) and the implicit ordering
enforced by `emit.py` itself. There is no shared "pipeline step" interface
today; this document is the explicit description of that implicit contract.
