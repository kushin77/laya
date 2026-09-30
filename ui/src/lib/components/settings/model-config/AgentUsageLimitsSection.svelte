<!-- Copyright 2026 Aayush Chawla -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
	import { glassTheme } from '$lib/stores/glassTheme';
	import type { AgentBackend } from '$lib/api/types';
	import { parseBackendDate } from '$lib/utils/datetime';
	import {
		agentBudgetEnabled,
		agentBudgetAgents,
		agentBudgetStatus,
		savingAgentBudget,
		resumingAgentBudget,
		debounceSaveAgentBudget,
		handleResumeAgent,
		fmtTokensShort,
		agentStatusFor
	} from '$lib/stores/agentBudget';

	let { agentBackends, agentLabels }: {
		agentBackends: AgentBackend[];
		agentLabels: Record<string, string>;
	} = $props();

	// Seed a default config row for every available agent so the inputs can bind.
	$effect(() => {
		for (const b of agentBackends) {
			if (b.available && !$agentBudgetAgents[b.agent_id]) {
				$agentBudgetAgents[b.agent_id] = { window_token_limit: null, window_hours: 5, pause_at_percent: 85 };
			}
		}
	});
</script>

<div id="agent-usage" class="{$glassTheme ? 'glass-section' : 'rounded-lg border border-surface-700 bg-surface-800'} p-5">
	<div class="mb-4">
		<div class="mb-1 flex items-center gap-2">
			<h3 class="text-laya-heading font-medium">Agent Usage Limits</h3>
			<span class="rounded bg-laya-gold/25 px-1 text-laya-micro font-semibold uppercase tracking-wide text-laya-amber">Beta</span>
			{#if $savingAgentBudget}<span class="ml-auto text-laya-micro text-laya-orange">Saving…</span>{/if}
		</div>
		<p class="text-laya-secondary text-surface-500">Agents bill against usage limits, not dollars. Set a token budget per rolling window — Laya pauses ingestion when reached and auto-resumes when the window resets.</p>
	</div>

	{#if $agentBudgetStatus?.is_paused}
		<div class="mb-4 flex items-center justify-between rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3">
			<div class="flex items-center gap-2">
				<svg class="h-4 w-4 text-red-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
				</svg>
				<span class="text-laya-base text-red-300">
					Usage limit reached — ingestion paused{#if $agentBudgetStatus.paused_until} until {parseBackendDate($agentBudgetStatus.paused_until)?.toLocaleString()}{/if}
				</span>
			</div>
			<button
				onclick={handleResumeAgent}
				disabled={$resumingAgentBudget}
				class="rounded-md bg-red-500/20 px-3 py-1.5 text-laya-secondary font-medium text-red-300 transition-colors hover:bg-red-500/30 disabled:opacity-50"
			>
				{$resumingAgentBudget ? 'Resuming…' : 'Resume Now'}
			</button>
		</div>
	{/if}

	<div class="space-y-4">
		<div class="flex items-center gap-3">
			<button
				aria-label="Toggle agent usage limits"
				onclick={() => { $agentBudgetEnabled = !$agentBudgetEnabled; debounceSaveAgentBudget(); }}
				class="relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors {$agentBudgetEnabled ? 'bg-laya-orange' : 'bg-surface-600'}"
			>
				<span class="inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform {$agentBudgetEnabled ? 'translate-x-4' : 'translate-x-0.5'}"></span>
			</button>
			<span class="text-laya-base text-surface-300">Enable agent usage limits</span>
		</div>

		{#if $agentBudgetEnabled}
			{#each agentBackends.filter((b) => b.available) as b}
				{@const c = $agentBudgetAgents[b.agent_id]}
				{@const st = agentStatusFor($agentBudgetStatus, b.agent_id)}
				{#if c}
					<div class="rounded-lg border border-surface-700 bg-surface-900/50 p-4">
						<div class="mb-2 flex items-center justify-between">
							<span class="text-laya-base text-surface-200">{agentLabels[b.agent_id] || b.agent_id}</span>
							{#if st?.rate_limit?.status}
								<span class="text-laya-micro text-surface-500">
									live limit: {st.rate_limit.status}{#if st.rate_limit.resets_at} · resets {new Date(st.rate_limit.resets_at * 1000).toLocaleTimeString()}{/if}
								</span>
							{/if}
						</div>
						<div class="grid grid-cols-3 gap-3">
							<label class="text-laya-micro text-surface-500">
								Token budget
								<input type="number" min="0" step="100000" placeholder="e.g. 5000000"
									bind:value={c.window_token_limit} oninput={debounceSaveAgentBudget}
									class="mt-1 w-full rounded-md border border-surface-600 bg-surface-700 px-2 py-1.5 text-laya-base text-surface-200 placeholder:text-surface-500" />
							</label>
							<label class="text-laya-micro text-surface-500">
								Window (hours)
								<input type="number" min="1" step="1"
									bind:value={c.window_hours} oninput={debounceSaveAgentBudget}
									class="mt-1 w-full rounded-md border border-surface-600 bg-surface-700 px-2 py-1.5 text-laya-base text-surface-200" />
							</label>
							<label class="text-laya-micro text-surface-500">
								Pause at %
								<input type="number" min="1" max="100"
									bind:value={c.pause_at_percent} oninput={debounceSaveAgentBudget}
									class="mt-1 w-full rounded-md border border-surface-600 bg-surface-700 px-2 py-1.5 text-laya-base text-surface-200" />
							</label>
						</div>
						{#if st && st.window_token_limit > 0}
							<div class="mt-3">
								<div class="mb-1 flex justify-between text-laya-micro text-surface-500">
									<span>{fmtTokensShort(st.tokens_used)} / {fmtTokensShort(st.window_token_limit)} tokens · last {st.window_hours}h</span>
									<span>{st.percent != null ? st.percent.toFixed(0) : 0}%</span>
								</div>
								<div class="h-2 w-full overflow-hidden rounded-full bg-surface-700">
									<div
										class="h-full rounded-full transition-all duration-500 {(st.percent ?? 0) >= 100 ? 'bg-red-500' : (st.percent ?? 0) >= 75 ? 'bg-amber-500' : 'bg-green-500'}"
										style="width: {Math.min(st.percent ?? 0, 100)}%"
									></div>
								</div>
							</div>
						{/if}
					</div>
				{/if}
			{/each}
			<p class="text-laya-micro text-surface-500">Tip: set the token budget to match your plan’s window (e.g. Claude Code’s 5-hour window). Claude Code also reports its live limit above and resumes exactly at its reset.</p>
		{/if}
	</div>
</div>
