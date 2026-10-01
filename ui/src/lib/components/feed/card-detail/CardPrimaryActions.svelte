<!-- Copyright 2026 Aayush Chawla -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
	import type { ActionCard } from '$lib/api/types';
	import { engineApi } from '$lib/api/engine';

	let {
		card,
		showRunAgentInput = $bindable(false),
		runAgentPrompt = $bindable(''),
		startingAgent = false,
		onstartagent,
	}: {
		card: ActionCard;
		showRunAgentInput?: boolean;
		runAgentPrompt?: string;
		startingAgent?: boolean;
		onstartagent?: () => void;
	} = $props();

	let markingDone = $state(false);
	let dismissing = $state(false);
	let archiving = $state(false);
	let reopening = $state(false);
	let dismissReason = $state('');
	let showDismissInput = $state(false);

	async function markDone() {
		markingDone = true;
		try {
			await engineApi.markCardDone(card.card_id);
			card.status = 'done';
		} finally {
			markingDone = false;
		}
	}

	async function dismiss() {
		dismissing = true;
		try {
			await engineApi.dismissCard(card.card_id, dismissReason || undefined);
			card.status = 'dismissed';
			showDismissInput = false;
		} finally {
			dismissing = false;
		}
	}

	async function archive() {
		archiving = true;
		try {
			await engineApi.archiveCard(card.card_id);
			card.status = 'archived';
		} finally {
			archiving = false;
		}
	}

	async function reopen() {
		reopening = true;
		try {
			const result = await engineApi.reopenCard(card.card_id);
			card.status = result.status as ActionCard['status'];
		} finally {
			reopening = false;
		}
	}
</script>

<div class="mt-3">
	{#if showRunAgentInput}
		<div class="flex flex-col gap-2">
			<div class="flex items-center gap-2 text-laya-secondary text-surface-400">
				<svg class="h-3.5 w-3.5 text-cyan-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
				Run Agent
			</div>
			<input
				bind:value={runAgentPrompt}
				placeholder="What should the agent focus on? (optional)"
				class="flex-1 rounded-md border border-surface-600 bg-surface-900 px-2 py-1.5 text-laya-secondary text-surface-50 placeholder-surface-500"
			/>
			<div class="flex gap-2">
				<button
					class="flex-1 rounded-md bg-cyan-700/40 px-2 py-1.5 text-laya-secondary font-medium text-cyan-300 transition-colors hover:bg-cyan-700/60 disabled:opacity-50"
					onclick={() => onstartagent?.()}
					disabled={startingAgent}
				>
					{startingAgent ? 'Starting...' : 'Start'}
				</button>
				<button
					class="text-laya-base text-surface-400 hover:text-surface-200"
					onclick={() => { showRunAgentInput = false; runAgentPrompt = ''; }}
				>
					Cancel
				</button>
			</div>
		</div>
	{:else if showDismissInput}
		<div class="flex gap-2">
			<input
				bind:value={dismissReason}
				placeholder="Reason (optional)"
				class="flex-1 rounded-md border border-surface-600 bg-surface-900 px-2 py-1.5 text-laya-secondary text-surface-50 placeholder-surface-500"
			/>
			<button
				class="rounded-md bg-surface-600 px-3 py-1.5 text-laya-secondary font-medium text-surface-200 hover:bg-surface-500"
				onclick={dismiss}
				disabled={dismissing}
			>
				{dismissing ? '...' : 'Confirm'}
			</button>
			<button
				class="text-laya-base text-surface-400 hover:text-surface-200"
				onclick={() => (showDismissInput = false)}
			>
				Cancel
			</button>
		</div>
	{:else if card.status === 'ready'}
		<div class="flex gap-2">
			<button
				class="flex-1 rounded-md bg-green-700/40 px-2 py-1.5 text-laya-secondary font-medium text-green-300 transition-colors hover:bg-green-700/60 disabled:opacity-50"
				onclick={markDone}
				disabled={markingDone}
			>
				{markingDone ? '...' : 'Done'}
			</button>
			<button
				class="flex-1 rounded-md bg-surface-700/50 px-2 py-1.5 text-laya-secondary font-medium text-surface-400 transition-colors hover:bg-surface-700"
				onclick={() => (showDismissInput = true)}
			>
				Dismiss
			</button>
			<button
				class="flex-1 rounded-md bg-surface-700/30 px-2 py-1.5 text-laya-secondary font-medium text-surface-500 transition-colors hover:bg-surface-700 disabled:opacity-50"
				onclick={archive}
				disabled={archiving}
			>
				{archiving ? '...' : 'Archive'}
			</button>
		</div>
	{:else if card.status === 'dismissed' || card.status === 'archived' || card.status === 'done' || card.status === 'failed'}
		<div class="flex gap-2">
			<button
				class="flex-1 rounded-md bg-laya-orange/15 px-2 py-1.5 text-laya-secondary font-medium text-laya-orange transition-colors hover:bg-laya-orange/25 disabled:opacity-50"
				onclick={reopen}
				disabled={reopening}
			>
				{reopening ? 'Reopening...' : card.status === 'archived' ? 'Unarchive' : card.status === 'failed' ? 'Retry' : 'Reopen'}
			</button>
			{#if card.status !== 'archived'}
				<button
					class="flex-1 rounded-md bg-surface-700/30 px-2 py-1.5 text-laya-secondary font-medium text-surface-500 transition-colors hover:bg-surface-700 disabled:opacity-50"
					onclick={archive}
					disabled={archiving}
				>
					{archiving ? '...' : 'Archive'}
				</button>
			{/if}
		</div>
	{:else}
		<div class="flex gap-2">
			<button
				class="flex-1 rounded-md bg-surface-700/30 px-2 py-1.5 text-laya-secondary font-medium text-surface-500 transition-colors hover:bg-surface-700 disabled:opacity-50"
				onclick={archive}
				disabled={archiving}
			>
				{archiving ? '...' : 'Archive'}
			</button>
		</div>
	{/if}
</div>
