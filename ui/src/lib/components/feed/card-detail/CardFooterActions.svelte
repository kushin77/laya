<!-- Copyright 2026 Aayush Chawla -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
	import type { ActionCard, CardEgressContext, CardEgressAction } from '$lib/api/types';
	import { engineApi } from '$lib/api/engine';
	import { goto } from '$app/navigation';
	import { glassTheme } from '$lib/stores/glassTheme';
	import { portal } from '$lib/actions/portal';
	import { compose } from '$lib/stores/compose';
	import { spaces, loadSpaces } from '$lib/stores/spaces';
	import { createPositionedMenu } from '$lib/actions/positionedMenu.svelte';
	import ClassificationDialog from '../ClassificationDialog.svelte';
	import DeleteConfirmDialog from './DeleteConfirmDialog.svelte';

	let {
		card,
		onclose,
		onlink,
		onshowrelated,
		onunlinked,
		onrunagentclick,
	}: {
		card: ActionCard;
		onclose: () => void;
		onlink?: (card: ActionCard) => void;
		onshowrelated?: (card: ActionCard) => void;
		onunlinked?: (cardId: string, entityId: string) => void;
		onrunagentclick?: () => void;
	} = $props();

	let relatedCount = $state<number | null>(null);
	let unlinkingCard = $state(false);
	const overflowMenu = createPositionedMenu({ placement: 'above' });
	let showClassificationDialog = $state(false);
	let showDeleteConfirm = $state(false);
	let deleting = $state(false);

	// Move-to-space: an inline footer action (lowest priority — the first that would
	// collapse into overflow) that reparents the card's whole GROUP to another space.
	const moveMenu = createPositionedMenu({ placement: 'above' });
	let moveConfirm = $state<null | { space_id: string; space_name: string; warning: string; scope: string; count: number }>(null);
	let moving = $state(false);

	let egressContext = $state<CardEgressContext | null>(null);
	let egressLoading = $state(false);

	// Load spaces once so the picker knows the alternatives (store is cheap/cached).
	$effect(() => { loadSpaces(); });

	const otherSpaces = $derived($spaces.filter((s) => s.space_id !== (card.space_id ?? 'default')));
	const hasRelated = $derived(relatedCount != null && relatedCount > 0);

	// Pick a target space → dry-run the move so the backend tells us the true scope
	// (entity/context group vs standalone) + the warning to confirm.
	async function pickMoveSpace(spaceId: string, spaceName: string) {
		moveMenu.open = false;
		try {
			const preview = await engineApi.moveCard(card.card_id, { space_id: spaceId, dry_run: true });
			moveConfirm = {
				space_id: spaceId,
				space_name: preview.space_name ?? spaceName,
				warning: preview.warning ?? `Move this card to "${spaceName}"?`,
				scope: preview.scope ?? 'standalone',
				count: preview.card_count ?? 1,
			};
		} catch {
			moveConfirm = { space_id: spaceId, space_name: spaceName, warning: `Move this card to "${spaceName}"?`, scope: 'standalone', count: 1 };
		}
	}

	async function confirmMove() {
		if (!moveConfirm) return;
		moving = true;
		try {
			await engineApi.moveCard(card.card_id, { space_id: moveConfirm.space_id });
			moveConfirm = null;
			// The card (and its group) left the current space; the WS card_updated
			// broadcast re-filters the feed. Close the panel since it's no longer in view.
			onclose();
		} catch {
			// Keep the dialog open on failure so the user can retry / cancel.
		} finally {
			moving = false;
		}
	}

	// Guard the related/egress fetches on the card_id actually changing. The `card`
	// prop is replaced with a fresh object on every WS status tick of the selected
	// card (same card_id, new identity), which re-ran these effects and refetched
	// related + egress context each time (review §2 UI — P4-34). Skip when the
	// card_id is unchanged.
	let _relatedFor: string | null = null;
	$effect(() => {
		const cardId = card.card_id;
		if (_relatedFor === cardId) return;
		_relatedFor = cardId;
		relatedCount = null;
		if (!onshowrelated) return;
		engineApi.getRelatedCards(cardId).then((data) => {
			if (card.card_id === cardId) {
				relatedCount = data.total_related_cards;
			}
		}).catch(() => {});
	});

	let _egressFor: string | null = null;
	$effect(() => {
		const cardId = card.card_id;
		const entityId = card.entity_id;
		if (_egressFor === cardId) return;
		_egressFor = cardId;
		egressContext = null;
		egressLoading = false;
		if (!entityId) return;
		egressLoading = true;
		engineApi.getCardEgressContext(cardId).then((ctx) => {
			if (card.card_id === cardId) egressContext = ctx;
		}).catch(() => {
			egressContext = null;
		}).finally(() => { egressLoading = false; });
	});

	function openPlatformAction(action: CardEgressAction) {
		if (!egressContext) return;
		overflowMenu.open = false;
		compose.openCompose(
			egressContext.platform,
			action.action_type,
			egressContext.prefill,
			card.card_id,
			egressContext.event_id ?? undefined,
			egressContext.connection_id
		);
	}

	async function unlinkCard() {
		unlinkingCard = true;
		try {
			await engineApi.unlinkRelatedCard(card.card_id);
			const entityId = card.entity_id ?? '';
			overflowMenu.open = false;
			onunlinked?.(card.card_id, entityId);
			try {
				const data = await engineApi.getRelatedCards(card.card_id);
				relatedCount = data.total_related_cards;
			} catch {
				relatedCount = 0;
			}
		} finally {
			unlinkingCard = false;
		}
	}

	function deleteCard() {
		// Optimistic: close immediately, fire API in background
		showDeleteConfirm = false;
		onclose();
		engineApi.deleteCard(card.card_id).catch(() => {
			// If delete fails, next WS reload will restore the card
		});
	}
</script>

<!-- Secondary actions -->
<div class="flex items-center justify-end gap-1">
	{#if card.has_workspace}
		<a
			href="/workspace/{card.card_id}"
			class="flex items-center gap-1 rounded-md px-2 py-1 text-laya-secondary text-violet-400/80 transition-colors hover:bg-violet-500/15 hover:text-violet-300"
			onclick={(e) => { e.preventDefault(); e.stopPropagation(); goto(`/workspace/${card.card_id}`); }}
		>
			<svg class="h-3 w-3" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
			Workspace
		</a>
	{/if}
	<button
		class="flex items-center gap-1 rounded-md px-2 py-1 text-laya-secondary text-surface-400 transition-colors hover:bg-surface-700/50 hover:text-surface-200"
		onclick={() => (showClassificationDialog = true)}
	>
		<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
		Classify
	</button>
	{#if onshowrelated && hasRelated}
		<button
			class="flex items-center gap-1 rounded-md px-2 py-1 text-laya-secondary text-surface-400 transition-colors hover:bg-surface-700/50 hover:text-laya-orange"
			onclick={() => onshowrelated(card)}
		>
			<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle cx="5" cy="12" r="2" stroke-width="2" /><circle cx="19" cy="6" r="2" stroke-width="2" /><circle cx="19" cy="18" r="2" stroke-width="2" /><path stroke-linecap="round" stroke-width="2" d="M7 11l10-4M7 13l10 4" /></svg>
			Related ({relatedCount})
		</button>
	{/if}
	{#if onrunagentclick && card.entity_id && !card.has_workspace}
		<button
			class="flex items-center gap-1 rounded-md px-2 py-1 text-laya-secondary text-surface-400 transition-colors hover:bg-surface-700/50 hover:text-cyan-400"
			onclick={onrunagentclick}
		>
			<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
			Run Agent
		</button>
	{/if}
	<!-- Move to space — last inline action (lowest priority; first to overflow) -->
	{#if $spaces.length > 1}
		<button
			bind:this={moveMenu.btnEl}
			class="flex items-center gap-1 rounded-md px-2 py-1 text-laya-secondary text-surface-400 transition-colors hover:bg-surface-700/50 hover:text-laya-orange"
			onclick={moveMenu.toggle}
			aria-label="Move to space"
		>
			<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 13h6m0 0l-2-2m2 2l-2 2" /></svg>
			Move
		</button>
	{/if}
	<!-- Overflow menu: Link / Unlink / Delete -->
	<div class="relative">
		<button
			bind:this={overflowMenu.btnEl}
			class="flex items-center justify-center rounded-md px-1.5 py-1 text-laya-secondary text-surface-400 transition-colors hover:bg-surface-700/50 hover:text-surface-200"
			onclick={overflowMenu.toggle}
			aria-label="More actions"
		>
			<svg class="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 20 20">
				<path d="M6 10a2 2 0 11-4 0 2 2 0 014 0zM12 10a2 2 0 11-4 0 2 2 0 014 0zM18 10a2 2 0 11-4 0 2 2 0 014 0z" />
			</svg>
		</button>
	</div>
</div>

{#if showDeleteConfirm}
	<DeleteConfirmDialog
		title="Delete card permanently?"
		{deleting}
		onconfirm={deleteCard}
		oncancel={() => (showDeleteConfirm = false)}
	>
		{#snippet message()}
			All details, intelligence, workspace sessions, and related events for this card will be
			<span class="font-medium text-red-400">permanently removed</span>. This cannot be undone.
		{/snippet}
	</DeleteConfirmDialog>
{/if}

{#if moveMenu.open}
	<div
		bind:this={moveMenu.menuEl}
		use:portal
		class="fixed z-[100] w-48 rounded-lg border p-1 {$glassTheme ? 'glass-menu' : 'border-surface-600 bg-surface-900 shadow-xl shadow-black/50'}"
		style="top: {moveMenu.pos.top}px; right: {moveMenu.pos.right}px; transform: translateY(-100%);"
		role="menu"
	>
		<div class="px-2.5 py-1 text-laya-micro font-medium uppercase tracking-wide text-surface-500">Move to space</div>
		{#each otherSpaces as space (space.space_id)}
			<button
				class="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-laya-secondary text-surface-300 transition-colors hover:bg-surface-700 hover:text-surface-200"
				role="menuitem"
				onclick={() => pickMoveSpace(space.space_id, space.name)}
			>
				<span class="inline-block h-1.5 w-1.5 shrink-0 rounded-full" style="background-color: {space.color}"></span>
				<span class="truncate">{space.name}</span>
			</button>
		{/each}
		{#if otherSpaces.length === 0}
			<div class="px-2.5 py-1.5 text-laya-secondary text-surface-500">No other spaces</div>
		{/if}
	</div>
{/if}

{#if moveConfirm}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
		role="dialog"
		aria-label="Confirm move to space"
		tabindex="-1"
		onclick={(e) => { if (e.target === e.currentTarget) moveConfirm = null; }}
		onkeydown={(e) => { if (e.key === 'Escape') moveConfirm = null; }}
	>
		<div class="mx-4 w-full max-w-md rounded-xl border border-surface-700 bg-surface-800 p-5 shadow-2xl">
			<div class="mb-3 flex items-start gap-3">
				<div class="mt-0.5 rounded-full bg-laya-orange/15 p-1.5">
					<svg class="h-4 w-4 text-laya-orange" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 13h6m0 0l-2-2m2 2l-2 2" /></svg>
				</div>
				<div>
					<h4 class="text-laya-base font-semibold text-surface-50">Move to "{moveConfirm.space_name}"?</h4>
					<p class="mt-1 text-laya-secondary leading-relaxed text-surface-400">{moveConfirm.warning}</p>
				</div>
			</div>
			<div class="flex justify-end gap-2">
				<button
					class="rounded-md px-3 py-1.5 text-laya-secondary text-surface-400 transition-colors hover:text-surface-200 disabled:opacity-50"
					onclick={() => (moveConfirm = null)}
					disabled={moving}
				>
					Cancel
				</button>
				<button
					class="rounded-md bg-laya-orange/20 px-3 py-1.5 text-laya-secondary font-medium text-laya-orange transition-colors hover:bg-laya-orange/30 disabled:opacity-50"
					onclick={confirmMove}
					disabled={moving}
				>
					{moving ? 'Moving...' : 'Move'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if showClassificationDialog}
	<ClassificationDialog
		{card}
		onclose={() => (showClassificationDialog = false)}
	/>
{/if}

{#if overflowMenu.open}
	<div
		bind:this={overflowMenu.menuEl}
		use:portal
		class="fixed z-[100] w-44 rounded-lg border p-1 {$glassTheme ? 'glass-menu' : 'border-surface-600 bg-surface-900 shadow-xl shadow-black/50'}"
		style="top: {overflowMenu.pos.top}px; right: {overflowMenu.pos.right}px; transform: translateY(-100%);"
		role="menu"
	>
		{#if onlink}
			<button
				class="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-laya-secondary text-surface-300 transition-colors hover:bg-surface-700 hover:text-surface-200"
				role="menuitem"
				onclick={() => { overflowMenu.open = false; onlink(card); }}
			>
				<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg>
				Link to...
			</button>
		{/if}
		{#if hasRelated}
			<button
				class="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-laya-secondary text-surface-300 transition-colors hover:bg-surface-700 hover:text-red-400 disabled:opacity-50"
				role="menuitem"
				disabled={unlinkingCard}
				onclick={unlinkCard}
			>
				<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /><line x1="4" y1="4" x2="20" y2="20" stroke="currentColor" stroke-width="2" stroke-linecap="round" /></svg>
				{unlinkingCard ? 'Unlinking...' : 'Unlink'}
			</button>
		{/if}
		{#if card.status === 'archived'}
			<button
				class="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-laya-secondary text-surface-300 transition-colors hover:bg-surface-700 hover:text-red-400 disabled:opacity-50"
				role="menuitem"
				disabled={deleting}
				onclick={() => { overflowMenu.open = false; showDeleteConfirm = true; }}
			>
				<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
				Delete
			</button>
		{/if}
		{#if egressContext && egressContext.actions.length > 0}
			<div class="my-1 border-t {$glassTheme ? 'border-surface-700/40' : 'border-surface-600'}"></div>
			{#each egressContext.actions as action (action.action_type)}
				<button
					class="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-laya-secondary text-surface-300 transition-colors hover:bg-surface-700 hover:text-surface-200"
					role="menuitem"
					onclick={() => openPlatformAction(action)}
				>
					<svg class="h-3.5 w-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
					<span class="truncate">{action.label}</span>
					{#if action.impact === 'high'}
						<span class="ml-auto text-laya-micro font-bold text-amber-500/70">!</span>
					{/if}
				</button>
			{/each}
			{#if !egressContext.connected}
				<p class="px-2.5 py-1 text-laya-micro text-surface-500 italic">
					Connect {egressContext.platform} to use
				</p>
			{/if}
		{:else if egressLoading}
			<div class="my-1 border-t {$glassTheme ? 'border-surface-700/40' : 'border-surface-600'}"></div>
			<div class="flex items-center gap-2 px-2.5 py-1.5 text-laya-micro text-surface-500">
				<svg class="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" /><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
				Loading actions
			</div>
		{/if}
	</div>
{/if}
