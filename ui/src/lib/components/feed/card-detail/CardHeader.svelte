<!-- Copyright 2026 Aayush Chawla -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
	import type { ActionCard } from '$lib/api/types';
	import { engineApi } from '$lib/api/engine';
	import { chatOpen, chatSession, chatListOpen } from '$lib/stores/chat';
	import { buildSingleCardContext } from '$lib/utils/cardContext';
	import { glassTheme } from '$lib/stores/glassTheme';
	import { portal } from '$lib/actions/portal';
	import { detailExpanded } from '$lib/stores/detailPanel';
	import { PRIORITY_LABELS, PRIORITY_COLORS } from '$lib/utils/cardVisuals';
	import { createPositionedMenu } from '$lib/actions/positionedMenu.svelte';
	import OriginalContentModal from '../OriginalContentModal.svelte';

	let {
		card,
		onclose,
		ondismiss,
		ongotocard,
	}: { card: ActionCard; onclose: () => void; ondismiss?: () => void; ongotocard?: (card: ActionCard) => void } = $props();

	const colors = PRIORITY_COLORS;
	const priorityLabel = PRIORITY_LABELS;

	const personaColors: Record<string, string> = {
		ENGINEER: 'border-violet-500 text-violet-400',
		COMMS: 'border-emerald-500 text-emerald-400',
		OPS: 'border-amber-500 text-amber-400',
		SALES: 'border-sky-500 text-sky-400',
		HR: 'border-rose-500 text-rose-400',
		FINANCE: 'border-teal-500 text-teal-400'
	};

	let copied = $state(false);
	let bookmarking = $state(false);
	let reprocessing = $state(false);
	let showOriginalModal = $state(false);
	let fixedTooltip = $state<{ text: string; top: number; left: number } | null>(null);

	// Header sits at the top of the panel, so the menu drops *below* the trigger.
	const headerMenu = createPositionedMenu({ placement: 'below' });

	function showTooltip(el: HTMLElement, text: string) {
		const rect = el.getBoundingClientRect();
		fixedTooltip = { text, top: rect.bottom + 4, left: rect.left + rect.width / 2 };
	}
	function hideTooltip() { fixedTooltip = null; }

	async function copyId() {
		await navigator.clipboard.writeText(card.card_id);
		copied = true;
		setTimeout(() => (copied = false), 1500);
	}

	function chatAbout() {
		chatSession.update((s) => ({
			...s,
			cardContext: buildSingleCardContext(card),
			cardIds: [card.card_id]
		}));
		chatListOpen.set(false);
		chatOpen.set(true);
	}

	async function toggleBookmark() {
		bookmarking = true;
		try {
			if (card.bookmarked_at) {
				await engineApi.unbookmarkCard(card.card_id);
				card.bookmarked_at = undefined;
			} else {
				const result = await engineApi.bookmarkCard(card.card_id);
				card.bookmarked_at = result.bookmarked_at;
			}
		} finally {
			bookmarking = false;
		}
	}

	async function reprocess() {
		headerMenu.open = false;
		if (reprocessing) return;
		reprocessing = true;
		try {
			await engineApi.reprocessCard(card.card_id);
			// Reflect the reprocess immediately; the WS card_updated stream drives
			// the card back through provisional → ready as the pipeline re-runs.
			card.status = 'pending';
		} catch (e) {
			console.error('Reprocess failed:', e);
		} finally {
			reprocessing = false;
		}
	}
</script>

<!-- Header bar -->
<div class="flex items-center justify-between border-b px-5 py-4 {$glassTheme ? 'border-surface-700/40' : 'border-surface-700'}">
	<div class="flex items-center gap-2">
		<span class="rounded px-1.5 py-0.5 text-laya-micro font-bold uppercase {colors[card.priority] ?? colors.MEDIUM}">
			{priorityLabel[card.priority] ?? card.priority}
		</span>
		<span class="rounded border px-1.5 py-0.5 text-laya-micro font-medium uppercase {personaColors[card.persona] ?? personaColors.ENGINEER}">
			{card.persona}
		</span>
		{#if card.privacy_tier === 3}
			<span class="rounded bg-red-900/50 px-1.5 py-0.5 text-laya-micro font-medium text-red-300">
				CONFIDENTIAL
			</span>
		{/if}
	</div>
	<div class="flex items-center gap-1">
		<!-- Overflow menu — collapses all header actions except close -->
		<button
			bind:this={headerMenu.btnEl}
			onclick={headerMenu.toggle}
			onmouseenter={(e) => showTooltip(e.currentTarget, 'More actions')}
			onmouseleave={hideTooltip}
			aria-label="More actions"
			class="rounded p-1.5 transition-colors {headerMenu.open ? 'text-surface-200' : 'text-surface-500 hover:text-surface-200'}"
		>
			<svg class="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
				<path d="M6 10a2 2 0 11-4 0 2 2 0 014 0zM12 10a2 2 0 11-4 0 2 2 0 014 0zM18 10a2 2 0 11-4 0 2 2 0 014 0z" />
			</svg>
		</button>
		<!-- Expand / collapse the wide focus-mode overlay (same as the chat sidebar). -->
		<button
			onclick={() => detailExpanded.set(!$detailExpanded)}
			onmouseenter={(e) => showTooltip(e.currentTarget, $detailExpanded ? 'Collapse' : 'Expand')}
			onmouseleave={hideTooltip}
			aria-label={$detailExpanded ? 'Collapse panel' : 'Expand panel'}
			class="rounded p-1.5 text-surface-500 transition-colors hover:text-surface-200"
		>
			{#if $detailExpanded}
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 9h5V4M20 9h-5V4M4 15h5v5M20 15h-5v5" />
				</svg>
			{:else}
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 4H4v5M15 4h5v5M9 20H4v-5M15 20h5v-5" />
				</svg>
			{/if}
		</button>
		<button aria-label="Close panel" class="rounded p-1.5 text-surface-400 transition-colors hover:text-surface-100" onclick={() => ondismiss ? ondismiss() : onclose()}>
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
			</svg>
		</button>
	</div>
</div>

{#if showOriginalModal}
	<OriginalContentModal
		cardId={card.card_id}
		onclose={() => (showOriginalModal = false)}
	/>
{/if}

{#if fixedTooltip}
	<div
		use:portal
		class="pointer-events-none fixed z-[100] -translate-x-1/2 whitespace-nowrap rounded-md border border-transparent glass-tooltip px-2 py-1 text-laya-micro font-medium"
		style="top: {fixedTooltip.top}px; left: {fixedTooltip.left}px;"
	>
		{fixedTooltip.text}
	</div>
{/if}

{#if headerMenu.open}
	<div
		bind:this={headerMenu.menuEl}
		use:portal
		class="fixed z-[100] w-44 rounded-lg border p-1 {$glassTheme ? 'glass-menu' : 'border-surface-600 bg-surface-900 shadow-xl shadow-black/50'}"
		style="top: {headerMenu.pos.top}px; right: {headerMenu.pos.right}px;"
		role="menu"
	>
		{#if ongotocard}
			<button
				class="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-laya-secondary text-surface-300 transition-colors hover:bg-surface-700 hover:text-surface-200"
				role="menuitem"
				onclick={() => { headerMenu.open = false; ongotocard?.(card); }}
			>
				<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5" /></svg>
				Go to card
			</button>
		{/if}
		<button
			class="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-laya-secondary transition-colors hover:bg-surface-700 {copied ? 'text-green-400' : 'text-surface-300 hover:text-surface-200'}"
			role="menuitem"
			onclick={copyId}
		>
			{#if copied}
				<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>
				Copied!
			{:else}
				<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
				Copy card ID
			{/if}
		</button>
		<button
			class="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-laya-secondary text-surface-300 transition-colors hover:bg-surface-700 hover:text-surface-200"
			role="menuitem"
			onclick={() => { headerMenu.open = false; showOriginalModal = true; }}
		>
			<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
			Show original content
		</button>
		<button
			class="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-laya-secondary text-surface-300 transition-colors hover:bg-surface-700 hover:text-surface-200"
			role="menuitem"
			onclick={() => { headerMenu.open = false; chatAbout(); }}
		>
			<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>
			Chat about card
		</button>
		<button
			class="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-laya-secondary transition-colors hover:bg-surface-700 disabled:opacity-50 {card.bookmarked_at ? 'text-laya-orange' : 'text-surface-300 hover:text-laya-orange'}"
			role="menuitem"
			disabled={bookmarking}
			onclick={toggleBookmark}
		>
			<svg class="h-3.5 w-3.5" fill={card.bookmarked_at ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" /></svg>
			{card.bookmarked_at ? 'Remove bookmark' : 'Bookmark'}
		</button>
		<!-- Reprocess: re-run the pipeline on this card's event (recovery for a
		     card whose LLM output came back garbled). Disabled while the card is
		     already in flight. -->
		<div class="my-1 border-t border-surface-700/60"></div>
		<button
			class="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-laya-secondary transition-colors hover:bg-surface-700 disabled:opacity-40 disabled:hover:bg-transparent {reprocessing ? 'text-laya-orange' : 'text-surface-300 hover:text-surface-200'}"
			role="menuitem"
			disabled={reprocessing || card.status === 'pending' || card.status === 'agent_running'}
			onclick={reprocess}
		>
			<svg class="h-3.5 w-3.5 {reprocessing ? 'animate-spin' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
			{reprocessing ? 'Reprocessing…' : 'Reprocess'}
		</button>
	</div>
{/if}
