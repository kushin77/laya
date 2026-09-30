<!-- Copyright 2026 Aayush Chawla -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
	import { glassTheme } from '$lib/stores/glassTheme';
	import {
		fmtTokens,
		budgetEnabled,
		budgetLimit,
		budgetLimitInput,
		currentMonthCost,
		currentMonth,
		budgetByModel,
		budgetTokensByModel,
		budgetIsPaused,
		pausedWorkflowCount,
		savingBudget,
		resumingBudget,
		budgetHistory,
		historyLoading,
		debounceSaveBudget,
		handleResume,
		loadHistory
	} from '$lib/stores/budget';

	let showHistory = $state(false);

	const budgetPercent = $derived(
		$budgetLimit && $budgetLimit > 0 ? Math.min(($currentMonthCost / $budgetLimit) * 100, 100) : 0
	);
	const budgetBarColor = $derived(
		budgetPercent >= 100 ? 'bg-red-500' : budgetPercent >= 75 ? 'bg-amber-500' : 'bg-green-500'
	);

	function formatMonth(ym: string): string {
		const [y, m] = ym.split('-');
		const date = new Date(parseInt(y), parseInt(m) - 1);
		return date.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
	}
</script>

<div id="cost-control" class="{$glassTheme ? 'glass-section' : 'rounded-lg border border-surface-700 bg-surface-800'} p-5">
	<div class="mb-4">
		<div class="mb-1 flex items-center justify-between">
			<h3 class="text-laya-heading font-medium">Cost Control</h3>
			{#if $savingBudget}
				<span class="text-laya-micro text-laya-orange">Saving…</span>
			{/if}
		</div>
		<p class="text-laya-secondary text-surface-500">Set a monthly budget to automatically pause workflows when the limit is reached.</p>
	</div>

	<!-- Budget paused alert -->
	{#if $budgetIsPaused}
		<div class="mb-4 flex items-center justify-between rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3">
			<div class="flex items-center gap-2">
				<svg class="h-4 w-4 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
				</svg>
				<span class="text-laya-base text-red-300">
					Budget exceeded — {$pausedWorkflowCount} workflow{$pausedWorkflowCount !== 1 ? 's' : ''} paused
				</span>
			</div>
			<button
				onclick={handleResume}
				disabled={$resumingBudget}
				class="rounded-md bg-red-500/20 px-3 py-1.5 text-laya-secondary font-medium text-red-300 transition-colors hover:bg-red-500/30 disabled:opacity-50"
			>
				{$resumingBudget ? 'Resuming...' : 'Resume Workflows'}
			</button>
		</div>
	{/if}

	<!-- Enable toggle + limit input -->
	<div class="space-y-4">
		<div class="flex items-center gap-3">
			<button
				aria-label="Toggle monthly budget limit"
				onclick={() => { $budgetEnabled = !$budgetEnabled; debounceSaveBudget(); }}
				class="relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors {$budgetEnabled ? 'bg-laya-orange' : 'bg-surface-600'}"
			>
				<span class="inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform {$budgetEnabled ? 'translate-x-4' : 'translate-x-0.5'}"></span>
			</button>
			<span class="text-laya-base text-surface-300">Enable monthly budget limit</span>
		</div>

		{#if $budgetEnabled}
			<div class="grid grid-cols-[200px_1fr] items-center gap-4">
				<div>
					<label for="budget-limit" class="text-laya-base text-surface-300">Monthly Limit</label>
					<p class="text-laya-micro text-surface-500">Workflows pause when this amount is reached.</p>
				</div>
				<div class="flex items-center gap-2">
					<span class="text-laya-base text-surface-400">$</span>
					<input
						id="budget-limit"
						type="number"
						min="0.01"
						step="0.50"
						placeholder="e.g. 10.00"
						bind:value={$budgetLimitInput}
						oninput={debounceSaveBudget}
						class="w-32 rounded-md border border-surface-600 bg-surface-700 px-3 py-1.5 text-laya-base text-surface-200 placeholder:text-surface-500"
					/>
					<span class="text-laya-secondary text-surface-500">USD / month</span>
				</div>
			</div>

			<!-- Current month progress -->
			<div class="rounded-lg border border-surface-700 bg-surface-900/50 p-4">
				<div class="mb-2 flex items-center justify-between">
					<span class="text-[13px] leading-5 text-surface-400">
						{$currentMonth ? formatMonth($currentMonth) : 'Current Month'}
					</span>
					<span class="text-[13px] leading-5">
						<span class="font-semibold {budgetPercent >= 100 ? 'text-red-400' : budgetPercent >= 75 ? 'text-amber-400' : 'text-green-400'}">
							${$currentMonthCost.toFixed(2)}
						</span>
						{#if $budgetLimit}
							<span class="text-surface-500"> / ${$budgetLimit.toFixed(2)}</span>
						{/if}
					</span>
				</div>
				<!-- Progress bar -->
				{#if $budgetLimit}
					<div class="h-2 w-full overflow-hidden rounded-full bg-surface-700">
						<div
							class="h-full rounded-full transition-all duration-500 {budgetBarColor}"
							style="width: {budgetPercent}%"
						></div>
					</div>
					<div class="mt-1.5 text-right text-laya-micro text-surface-500">
						{budgetPercent.toFixed(0)}% used
					</div>
				{/if}

				<!-- Per-model breakdown: name | tokens | cost. The token column
				     keeps this meaningful on a local-model setup, where every
				     per-model cost is $0. Sort by tokens so the heaviest model
				     leads even when all costs are $0. -->
				{#if Object.keys($budgetByModel).length > 0}
					<div class="mt-3 space-y-1">
						{#each Object.entries($budgetByModel).sort((a, b) => ($budgetTokensByModel[b[0]] ?? 0) - ($budgetTokensByModel[a[0]] ?? 0)) as [model, cost]}
							<div class="flex items-center gap-3 text-laya-secondary">
								<span class="flex-1 truncate text-surface-400">{model}</span>
								<span class="w-16 shrink-0 text-right tabular-nums text-surface-500">{fmtTokens($budgetTokensByModel[model] ?? 0)}</span>
								<span class="w-20 shrink-0 text-right tabular-nums text-surface-300">${cost.toFixed(4)}</span>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		{/if}

		<!-- History accordion -->
		<div>
			<button
				onclick={() => { showHistory = !showHistory; if (showHistory) loadHistory(); }}
				class="flex items-center gap-1.5 text-laya-secondary text-surface-400 transition-colors hover:text-surface-300"
			>
				<svg
					class="h-3.5 w-3.5 transition-transform {showHistory ? 'rotate-90' : ''}"
					fill="none" stroke="currentColor" viewBox="0 0 24 24"
				>
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
				</svg>
				Monthly History
			</button>
			{#if showHistory}
				<div class="mt-2 space-y-1.5">
					{#if $historyLoading}
						<p class="text-laya-secondary text-surface-500">Loading...</p>
					{:else if $budgetHistory.length === 0}
						<p class="text-laya-secondary text-surface-500">No cost history yet. History is recorded at the end of each month.</p>
					{:else}
						{#each $budgetHistory as entry}
							<div class="flex items-center justify-between rounded-md border border-surface-700 bg-surface-900/30 px-3 py-2">
								<span class="text-laya-secondary text-surface-400">{formatMonth(entry.year_month)}</span>
								<span class="text-laya-secondary font-medium text-surface-200">${entry.total_cost_usd.toFixed(2)}</span>
							</div>
						{/each}
					{/if}
				</div>
			{/if}
		</div>
	</div>
</div>
