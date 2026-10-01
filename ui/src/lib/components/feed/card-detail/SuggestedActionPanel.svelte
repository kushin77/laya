<!-- Copyright 2026 Aayush Chawla -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
	import type { ActionCard } from '$lib/api/types';
	import { engineApi } from '$lib/api/engine';
	import { untrack } from 'svelte';
	import { lastMessage } from '$lib/stores/websocket';

	let { card }: { card: ActionCard } = $props();

	const terminalStatuses = new Set(['done', 'failed', 'dismissed', 'archived']);
	const isTerminal = $derived(terminalStatuses.has(card.status));

	let executingActionId = $state<string | null>(null);
	let executeError = $state<string | null>(null);
	let editingActionId = $state<string | null>(null);
	let editedPayload = $state<Record<string, string>>({});
	let savingPayload = $state(false);
	// Per-action spinner state for AI Polish. Seeded from `_polishing` flags
	// persisted in the action payload, so re-mounting the panel mid-flight
	// still shows the spinner. WS `action_payload_updated` events keep it
	// in sync across navigations and clients.
	let polishingActionIds = $state(new Set<string>());
	let polishErrors = $state<Record<string, string>>({});

	async function executeAction(actionId: string) {
		executingActionId = actionId;
		card.selected_action_id = actionId;
		executeError = null;
		try {
			const mods = editingActionId === actionId && Object.keys(editedPayload).length > 0
				? editedPayload
				: undefined;
			const result = await engineApi.executeAction(card.card_id, actionId, mods);
			card.status = result.status as ActionCard['status'];
			if (result.error) {
				card.last_error = result.error;
			} else {
				card.last_error = undefined;
			}
			if (result.result_url && result.status === 'done') {
				const action = card.suggested_actions?.find(a => a.action_id === actionId);
				if (action?.action_type === 'open_url') {
					try {
						const { open } = await import('@tauri-apps/plugin-shell');
						await open(result.result_url);
					} catch {
						window.open(result.result_url, '_blank', 'noopener,noreferrer');
					}
				}
			}
			editingActionId = null;
			editedPayload = {};
		} catch (err) {
			executeError = err instanceof Error ? err.message : 'Execution failed';
		} finally {
			executingActionId = null;
		}
	}

	/** Identify the main editable text field in an action payload (body, comment, message, etc.). */
	function getEditableTextField(payload: Record<string, unknown>): string | null {
		for (const key of ['body', 'comment', 'message', 'description']) {
			if (typeof payload[key] === 'string' && (payload[key] as string).length > 0) return key;
		}
		return null;
	}

	function startEditing(
		action: { action_id: string; payload: Record<string, unknown> },
		fallbackBody?: string
	) {
		editingActionId = action.action_id;
		const p = action.payload;
		// Extract all string fields for editing — works for email (to/subject/body),
		// Bitbucket/GitHub (comment), Slack (message), Jira (comment), etc.
		// Skip underscore-prefixed keys (e.g. _edited, _polishing, _polish_error)
		// which are internal UI-state flags, not user-editable content.
		editedPayload = {};
		for (const [key, value] of Object.entries(p)) {
			if (key.startsWith('_')) continue;
			if (typeof value === 'string' && value.length > 0) {
				editedPayload[key] = value;
			}
		}
		// When the engine couldn't parse the LLM's payload (it arrives as
		// `{raw: "subject"}` because the model emitted a non-JSON string), the
		// action has no body/comment field but the actual draft text still lives
		// in staged_output.content. Seed `body` so the user can edit + save and
		// the next executor pass has something usable to send.
		if (fallbackBody && !editedPayload.body && !editedPayload.comment && !editedPayload.message && !editedPayload.description) {
			editedPayload.body = fallbackBody;
		}
	}

	async function polishDraft(action: { action_id: string }) {
		if (polishingActionIds.has(action.action_id)) return;
		// Optimistic spinner — confirmed by the WS echo once the server flips
		// `_polishing` to true, then cleared when polish completes.
		polishingActionIds = new Set([...polishingActionIds, action.action_id]);
		const { [action.action_id]: _drop, ...restErrors } = polishErrors;
		polishErrors = restErrors;
		try {
			await engineApi.polishActionPayload(card.card_id, action.action_id);
		} catch (err) {
			const next = new Set(polishingActionIds);
			next.delete(action.action_id);
			polishingActionIds = next;
			polishErrors = {
				...polishErrors,
				[action.action_id]: err instanceof Error ? err.message : 'Polish failed'
			};
		}
	}

	// Seed spinner state from persisted `_polishing` flags whenever the viewed
	// card changes (fresh panel mount, or user switches cards). The WS effect
	// below handles subsequent updates — so we don't re-seed on every mutation,
	// which would otherwise wipe client-side errors from failed API calls.
	let _seededCardId = $state<string | null>(null);
	$effect(() => {
		if (_seededCardId === card.card_id) return;
		_seededCardId = card.card_id;
		const actions = card.suggested_actions ?? [];
		const seed = new Set<string>();
		const errs: Record<string, string> = {};
		for (const a of actions) {
			const p = a.payload as Record<string, unknown> | undefined;
			if (p?._polishing === true) seed.add(a.action_id);
			if (typeof p?._polish_error === 'string') errs[a.action_id] = p._polish_error as string;
		}
		polishingActionIds = seed;
		polishErrors = errs;
	});

	// Listen for per-action payload updates (polish start/complete, manual save).
	// The feed's WS handler is responsible for mutating groups[] — this handler
	// ONLY updates local spinner/error state.
	//
	// The body runs inside untrack() so the effect depends only on $lastMessage.
	// Without untrack, reading card.suggested_actions / action.payload here
	// tracks those reactive proxies; the subsequent writes to action.payload
	// then re-trigger this same effect, loop without bound, starve the
	// microtask queue, and freeze the UI (blocking savePayload's finally, so
	// "Saving..." never clears, and blocking any navigation after Polish).
	$effect(() => {
		const msg = $lastMessage;
		if (!msg || msg.type !== 'action_payload_updated') return;
		untrack(() => {
			if (msg.card_id !== card.card_id) return;
			const actionId = (msg as { action_id?: string }).action_id;
			const newPayload = (msg.payload as { payload?: Record<string, unknown> })?.payload;
			if (!actionId || !newPayload) return;
			if (newPayload._polishing === true) {
				polishingActionIds = new Set([...polishingActionIds, actionId]);
			} else if (newPayload._polishing === false) {
				const next = new Set(polishingActionIds);
				next.delete(actionId);
				polishingActionIds = next;
			}
			const err = newPayload._polish_error;
			if (typeof err === 'string' && err) {
				polishErrors = { ...polishErrors, [actionId]: err };
			} else if (newPayload._polishing === false && actionId in polishErrors) {
				const { [actionId]: _drop, ...rest } = polishErrors;
				polishErrors = rest;
			}
		});
	});

	async function savePayload(action: { action_id: string; payload: Record<string, unknown> }) {
		savingPayload = true;
		try {
			await engineApi.updateActionPayload(card.card_id, action.action_id, editedPayload);
			// Update the local action payload so the read-only view reflects saved
			// changes. Also flip _edited locally so the Polish button appears
			// immediately — the WS echo will confirm this shortly.
			Object.assign(action.payload, editedPayload);
			action.payload._edited = true;
			editingActionId = null;
			editedPayload = {};
		} catch (err) {
			executeError = err instanceof Error ? err.message : 'Failed to save draft';
		} finally {
			savingPayload = false;
		}
	}
</script>

{#if card.suggested_actions && card.suggested_actions.length > 0}
	<div class="mb-5">
		<h3 class="mb-2 text-laya-secondary font-semibold uppercase tracking-wider text-surface-400">Suggested Actions</h3>
		{#each card.suggested_actions as action}
			{@const isSelected = card.selected_action_id === action.action_id}
			{@const payload = action.payload}
			{@const detectedField = payload ? getEditableTextField(payload) : null}
			{@const isDraftReply = card.staged_output?.type === 'draft_reply'}
			{@const fallbackText = isDraftReply && detectedField === null && payload?.raw ? (card.staged_output?.content ?? '') : ''}
			{@const editableField = detectedField ?? (fallbackText ? 'body' : null)}
			{@const displayText = (detectedField ? (payload[detectedField] as string) : fallbackText) ?? ''}

			<!-- Action payload preview — works for any action with editable text (email body, PR comment, Slack message, etc.).
			     When the engine couldn't parse the LLM's payload (it landed as `{raw: "..."}` because the model
			     emitted a non-JSON string), `detectedField` is null but the actual draft still lives in
			     `staged_output.content` for draft_reply cards — fall back to it so Edit/Polish stay available. -->
			{#if editableField && displayText}
				{@const isEditing = editingActionId === action.action_id}
				{@const isPolishing = polishingActionIds.has(action.action_id)}
				{@const hasEdits = payload._edited === true}
				{@const polishErrorMsg = polishErrors[action.action_id]}
				<div class="relative mb-2 rounded-lg border border-surface-700 bg-surface-900/50 p-3">
					{#if !isEditing}
						<!-- Read-only view: show metadata fields, then the main text. Skip `raw`
						     since it's an engine-side fallback marker, not user content. -->
						{#each Object.entries(payload) as [key, value]}
							{#if !key.startsWith('_') && typeof value === 'string' && value.length > 0 && key !== editableField && key !== 'raw'}
								<div class="mb-1.5 flex items-center gap-1.5 text-laya-secondary">
									<span class="font-medium text-surface-500 capitalize">{key}:</span>
									<span class="text-surface-300">{value}</span>
								</div>
							{/if}
						{/each}
						<div class="max-h-48 overflow-y-auto whitespace-pre-wrap text-laya-base text-surface-200">{displayText}</div>
					{:else}
						<!-- Edit mode: inputs for metadata, textarea for main text -->
						{#each Object.entries(editedPayload) as [key]}
							{#if key !== editableField}
								<div class="mb-1.5 flex items-center gap-1.5 text-laya-secondary">
									<span class="shrink-0 font-medium text-surface-500 capitalize">{key}:</span>
									<input
										type="text"
										class="w-full rounded border border-surface-600 bg-surface-800 px-1.5 py-0.5 text-laya-secondary text-surface-200 outline-none focus:border-laya-orange/50"
										bind:value={editedPayload[key]}
									/>
								</div>
							{/if}
						{/each}
						<textarea
							class="w-full resize-y rounded border border-surface-600 bg-surface-800 p-2 text-laya-base text-surface-200 outline-none focus:border-laya-orange/50"
							rows="6"
							bind:value={editedPayload[editableField]}
						></textarea>
					{/if}
					<!-- Polish-in-flight overlay. Covers payload preview; blocks interaction
					     while the LLM is rewriting. Survives navigation because _polishing
					     is persisted in the action payload. -->
					{#if isPolishing}
						<div class="pointer-events-auto absolute inset-0 flex flex-col items-center justify-center gap-2 rounded-lg bg-surface-900/70 backdrop-blur-sm">
							<svg class="h-6 w-6 animate-spin text-laya-orange" fill="none" viewBox="0 0 24 24">
								<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
								<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
							</svg>
							<span class="text-laya-secondary font-medium text-laya-orange">Polishing draft…</span>
						</div>
					{/if}
					<!-- Edit / Save / Cancel / Polish controls -->
					{#if !isTerminal}
						<div class="mt-2 flex items-center justify-end gap-3">
							{#if polishErrorMsg && !isPolishing}
								<span class="mr-auto text-laya-secondary text-red-400">{polishErrorMsg}</span>
							{/if}
							{#if !isEditing}
								<button
									class="text-laya-secondary text-surface-400 hover:text-laya-orange transition-colors disabled:opacity-40 disabled:hover:text-surface-400"
									onclick={() => startEditing(action, detectedField ? undefined : fallbackText)}
									disabled={isPolishing}
								>
									Edit draft
								</button>
								{#if hasEdits}
									<button
										class="inline-flex items-center gap-1 text-laya-secondary font-medium text-laya-gold hover:text-laya-peach transition-colors disabled:opacity-40 disabled:hover:text-laya-gold"
										onclick={() => polishDraft(action)}
										disabled={isPolishing}
										title="Rewrite this draft with AI to polish the phrasing"
									>
										<svg class="h-3 w-3" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
											<path d="M12 2l1.9 5.6L19.5 9.5l-5.6 1.9L12 17l-1.9-5.6L4.5 9.5l5.6-1.9L12 2zm7 11l.95 2.8L22.75 16.75l-2.8.95L19 20.5l-.95-2.8L15.25 16.75l2.8-.95L19 13zM5 14l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7L5 14z" />
										</svg>
										Polish
									</button>
								{/if}
							{:else}
								<button
									class="text-laya-secondary text-surface-400 hover:text-surface-200 transition-colors"
									onclick={() => { editingActionId = null; editedPayload = {}; }}
									disabled={savingPayload}
								>
									Cancel
								</button>
								<button
									class="text-laya-secondary font-medium text-laya-orange hover:text-laya-gold transition-colors disabled:opacity-50"
									onclick={() => savePayload(action)}
									disabled={savingPayload}
								>
									{savingPayload ? 'Saving...' : 'Save'}
								</button>
							{/if}
						</div>
					{/if}
				</div>
			{/if}

			<div class="mb-2 flex flex-wrap gap-2">
				<button
					class="rounded-lg border px-3 py-1.5 text-laya-secondary font-medium transition-colors disabled:cursor-not-allowed
						{isSelected
							? isTerminal
								? 'border-laya-orange/50 bg-laya-orange/15 text-laya-orange'
								: 'border-surface-500 border-dashed bg-surface-800/50 text-surface-400'
							: card.selected_action_id && !isSelected
								? isTerminal
									? 'border-surface-700 bg-surface-800/50 text-surface-500 opacity-50'
									: 'border-surface-600 bg-surface-700/50 text-surface-200 hover:bg-surface-600'
								: 'border-surface-600 bg-surface-700/50 text-surface-200 hover:bg-surface-600'}"
					onclick={() => executeAction(action.action_id)}
					disabled={!!executingActionId || isTerminal}
				>
					{#if executingActionId === action.action_id}
						Executing...
					{:else}
						{#if isSelected}
							<span class="mr-1">{isTerminal ? '✓' : '↩'}</span>
						{/if}
						{action.label}
						<span class="ml-1 {isSelected && isTerminal ? 'text-laya-orange/60' : 'text-surface-500'}">({action.target_platform})</span>
					{/if}
				</button>
			</div>
		{/each}
		{#if executeError}
			<p class="mt-2 text-laya-secondary text-red-400">{executeError}</p>
		{/if}
	</div>
{/if}
