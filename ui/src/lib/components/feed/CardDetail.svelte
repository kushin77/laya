<!-- Copyright 2026 Aayush Chawla -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
	import type { ActionCard } from '$lib/api/types';
	import { engineApi } from '$lib/api/engine';
	import { parseBackendDate } from '$lib/utils/datetime';
	import MarkdownRender from '$lib/components/MarkdownRender.svelte';
	import PlatformBadge from '$lib/components/PlatformBadge.svelte';
	import { glassTheme } from '$lib/stores/glassTheme';
	import { detailExpanded } from '$lib/stores/detailPanel';
	import CardHeader from './card-detail/CardHeader.svelte';
	import CardTags from './card-detail/CardTags.svelte';
	import SuggestedActionPanel from './card-detail/SuggestedActionPanel.svelte';
	import CardFooterActions from './card-detail/CardFooterActions.svelte';
	import CardPrimaryActions from './card-detail/CardPrimaryActions.svelte';

	let {
		card,
		onclose,
		ondismiss,
		ongotocard,
		onlink,
		onshowrelated,
		onunlinked,
		onrunagent,
	}: { card: ActionCard; onclose: () => void; ondismiss?: () => void; ongotocard?: (card: ActionCard) => void; onlink?: (card: ActionCard) => void; onshowrelated?: (card: ActionCard) => void; onunlinked?: (cardId: string, entityId: string) => void; onrunagent?: (entityId: string) => void } = $props();

	let actorTruncated = $state(false);
	let emailTruncated = $state(false);

	let showRunAgentInput = $state(false);
	let runAgentPrompt = $state('');
	let startingAgent = $state(false);

	const outputTypeLabels: Record<string, string> = {
		draft_reply: 'Draft Reply',
		code_fix: 'Code Fix',
		briefing: 'Briefing',
		summary: 'Summary',
		agent_result: 'Agent Result',
		agent_plan: 'Implementation Plan'
	};

	const statusColors: Record<string, string> = {
		pending: 'text-yellow-400',
		ready: 'text-amber-400',
		agent_running: 'text-violet-400',
		awaiting_input: 'text-violet-400',
		done: 'text-green-500',
		failed: 'text-red-500',
		dismissed: 'text-surface-500',
		archived: 'text-surface-600'
	};

	const statusLabels: Record<string, string> = {
		pending: 'Processing',
		ready: 'Ready',
		agent_running: 'Agent Running',
		awaiting_input: 'Input Needed',
		done: 'Done',
		failed: 'Failed',
		dismissed: 'Dismissed',
		archived: 'Archived'
	};

	// Watches an element for text overflow and reports the result via callback.
	// The text param is included so the action's `update` re-runs (and re-measures)
	// when the underlying text changes — ResizeObserver alone fires only on size changes,
	// so it would miss a shorter string fitting after a card switch.
	function trackTruncation(node: HTMLElement, params: { onChange: (t: boolean) => void; text: string }) {
		let { onChange } = params;
		const measure = () => onChange(node.scrollWidth > node.clientWidth + 1);
		measure();
		const ro = new ResizeObserver(measure);
		ro.observe(node);
		return {
			update(next: { onChange: (t: boolean) => void; text: string }) {
				onChange = next.onChange;
				queueMicrotask(measure);
			},
			destroy() { ro.disconnect(); }
		};
	}

	async function startEntityAgent() {
		if (!card.entity_id || !onrunagent) return;
		startingAgent = true;
		try {
			await engineApi.runEntityAgent(card.entity_id, {
				prompt: runAgentPrompt || undefined
			});
			card.has_workspace = true;
			showRunAgentInput = false;
			runAgentPrompt = '';
		} finally {
			startingAgent = false;
		}
	}
</script>

<!-- In focus mode ($detailExpanded) the overlay wrapper provides the panel surface,
     so we drop our own card chrome to avoid a doubled border/background. -->
<div class="flex h-full flex-col overflow-hidden {$detailExpanded ? '' : ($glassTheme ? 'rounded-xl border glass-card border-surface-700/40 bg-surface-900/40' : 'rounded-xl border border-surface-700 bg-surface-800')}">
	<CardHeader {card} {onclose} {ondismiss} {ongotocard} />

	<!-- Scrollable content -->
	<div class="flex-1 overflow-y-auto overflow-x-hidden break-words px-5 py-4">
		<!-- Source platform + subject ID + actor info -->
		{#if card.entity_id || card.actor_name || card.actor_email}
			<div class="mb-3 flex flex-col gap-0.5">
				{#if card.entity_id}
					<div class="mb-1 flex items-center gap-1.5 min-w-0">
						<PlatformBadge platform={card.entity_id.split(':')[0]} />
						{#if card.source_context}
							<span class="text-laya-secondary text-surface-400">{card.source_context}</span>
						{/if}
						{#if card.source_ref}
							{#if card.source_url}
								<a
									href={card.source_url}
									target="_blank"
									rel="noopener noreferrer"
									class="inline-flex items-center gap-1 text-laya-secondary font-medium text-laya-orange hover:text-laya-peach transition-colors min-w-0 truncate"
								>
									<span class="truncate">{card.source_ref}</span>
									<svg class="h-2.5 w-2.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
									</svg>
								</a>
							{:else}
								<span class="text-laya-secondary font-medium text-surface-400 truncate">{card.source_ref}</span>
							{/if}
						{/if}
					</div>
				{/if}
				{#if card.actor_name}
					<div class="flex items-center gap-1.5 min-w-0">
						<span class="shrink-0 text-laya-micro font-semibold uppercase tracking-wider text-surface-500">Actor</span>
						<span class="group/actor relative min-w-0 flex-1">
							<span use:trackTruncation={{ onChange: (t) => (actorTruncated = t), text: card.actor_name }} class="block truncate text-laya-secondary text-surface-300">{card.actor_name}</span>
							{#if actorTruncated}
								<span class="pointer-events-none absolute left-0 top-full z-50 mt-1 max-w-xs break-all whitespace-normal rounded-md border border-transparent glass-tooltip px-2 py-1 text-laya-micro font-medium opacity-0 transition-opacity duration-75 group-hover/actor:opacity-100">
									{card.actor_name}
								</span>
							{/if}
						</span>
					</div>
				{/if}
				{#if card.actor_email}
					<div class="flex items-center gap-1.5 min-w-0">
						<span class="shrink-0 text-laya-micro font-semibold uppercase tracking-wider text-surface-500">Email</span>
						<span class="group/email relative min-w-0 flex-1">
							<span use:trackTruncation={{ onChange: (t) => (emailTruncated = t), text: card.actor_email }} class="block truncate text-laya-secondary text-surface-400">{card.actor_email}</span>
							{#if emailTruncated}
								<span class="pointer-events-none absolute left-0 top-full z-50 mt-1 max-w-xs break-all whitespace-normal rounded-md border border-transparent glass-tooltip px-2 py-1 text-laya-micro font-medium opacity-0 transition-opacity duration-75 group-hover/email:opacity-100">
									{card.actor_email}
								</span>
							{/if}
						</span>
					</div>
				{/if}
			</div>
		{/if}

		<!-- Header + summary -->
		<h2 class="mb-2 text-laya-heading font-semibold text-surface-50">{card.header}</h2>
		<p class="mb-5 text-laya-base text-surface-300">{card.summary}</p>

		<!-- Tags -->
		<CardTags {card} />

		<!-- Intelligence report -->
		{#if card.intelligence && card.intelligence.length > 0}
			<div class="mb-5">
				<h3 class="mb-2 text-laya-secondary font-semibold uppercase tracking-wider text-surface-400">Intelligence Report</h3>
				<ul class="space-y-1.5">
					{#each card.intelligence as point}
						<li class="flex items-start gap-2 text-laya-base text-surface-300 min-w-0">
							<span class="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-surface-500"></span>
							<span class="min-w-0 break-words">{point}</span>
						</li>
					{/each}
				</ul>
			</div>
		{/if}

		<!-- Staged output. Skipped for draft_reply when there's a suggested action —
		     the editable preview below renders the same draft text with Edit/Polish
		     controls, so we'd otherwise duplicate the same content. -->
		{#if card.staged_output && !(card.staged_output.type === 'draft_reply' && (card.suggested_actions?.length ?? 0) > 0)}
			<div class="mb-5">
				<h3 class="mb-2 text-laya-secondary font-semibold uppercase tracking-wider text-surface-400">
					{outputTypeLabels[card.staged_output.type] ?? 'Output'}
				</h3>
				{#if card.staged_output.type === 'code_fix'}
					<pre class="overflow-x-auto rounded-lg bg-surface-900 p-3 text-laya-secondary text-surface-200">{card.staged_output.content}</pre>
				{:else if card.staged_output.type === 'agent_plan'}
					<MarkdownRender
						content={card.staged_output.content}
						class="max-h-96 overflow-y-auto rounded-lg border border-surface-700 bg-surface-900/50 p-4 text-laya-base text-surface-200"
					/>
				{:else}
					<MarkdownRender
						content={card.staged_output.content}
						class="max-h-96 overflow-y-auto overflow-x-auto rounded-lg border border-surface-700 bg-surface-900/50 p-4 text-laya-base text-surface-200"
					/>
				{/if}
			</div>
		{/if}

		<!-- Suggested actions -->
		<SuggestedActionPanel {card} />

		<!-- Metadata -->
		<div class="mt-4 border-t pt-3 {$glassTheme ? 'border-surface-700/40' : 'border-surface-700'}">
			<div class="flex flex-wrap gap-x-4 gap-y-1 text-laya-secondary text-surface-500">
				{#if card.confidence}
					<span>Confidence: {Math.round(card.confidence * 100)}%</span>
				{/if}
				<span>Category: {card.category}</span>
				{#if card.status === 'failed' && card.last_error}
					<span class="{statusColors[card.status]} relative group cursor-help">
						Status: {statusLabels[card.status]}
						<span class="invisible group-hover:visible absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2.5 py-1.5 text-laya-secondary leading-tight bg-surface-800 border border-surface-600 text-surface-300 rounded shadow-lg whitespace-normal max-w-[280px] w-max z-50">
							{card.last_error}
						</span>
					</span>
				{:else}
					<span class={statusColors[card.status] ?? 'text-surface-400'}>Status: {statusLabels[card.status] ?? card.status}</span>
				{/if}
				{#if card.created_at}
					<span>Created: {parseBackendDate(card.created_at)?.toLocaleString()}</span>
				{/if}
			</div>
		</div>
	</div>

	<!-- Footer -->
	<div class="border-t px-5 py-2 {$glassTheme ? 'border-surface-700/40' : 'border-surface-700'}">
		<CardFooterActions
			{card}
			{onclose}
			{onlink}
			{onshowrelated}
			{onunlinked}
			onrunagentclick={onrunagent ? () => (showRunAgentInput = true) : undefined}
		/>
		<CardPrimaryActions
			{card}
			bind:showRunAgentInput
			bind:runAgentPrompt
			{startingAgent}
			onstartagent={startEntityAgent}
		/>
	</div>
</div>
