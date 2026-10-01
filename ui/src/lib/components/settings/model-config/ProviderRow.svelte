<!-- Copyright 2026 Aayush Chawla -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
	import { slide } from 'svelte/transition';
	import { reducedMotion } from '$lib/stores/reducedMotion';
	import type { CustomProvider, CustomProviderTestResult, DiscoveredModel } from '$lib/api/types';

	let {
		provider,
		typeLabel,
		testResult,
		testing,
		deleting,
		expanded,
		models,
		onTest,
		onDelete,
		onToggleExpand,
		onSave
	}: {
		provider: CustomProvider;
		typeLabel: string;
		testResult: CustomProviderTestResult | undefined;
		testing: boolean;
		deleting: boolean;
		expanded: boolean;
		models: DiscoveredModel[] | undefined;
		onTest: () => void;
		onDelete: () => void;
		onToggleExpand: () => void;
		onSave: (updates: { name?: string; base_url?: string; api_key?: string }) => Promise<void>;
	} = $props();

	let editing = $state(false);
	let editForm = $state({ name: '', base_url: '', api_key: '' });
	let editSaving = $state(false);

	function startEdit() {
		editing = true;
		editForm = { name: provider.name, base_url: provider.base_url, api_key: '' };
	}

	async function saveEdit() {
		editSaving = true;
		try {
			const updates: Record<string, string> = {};
			if (editForm.name.trim()) updates.name = editForm.name.trim();
			if (editForm.base_url.trim()) updates.base_url = editForm.base_url.trim();
			if (editForm.api_key.trim()) updates.api_key = editForm.api_key.trim();
			await onSave(updates);
			editing = false;
		} finally {
			editSaving = false;
		}
	}
</script>

<div class="rounded-md border border-surface-600 bg-surface-700/30">
	<!-- Provider header -->
	<div class="flex items-center gap-3 px-4 py-3">
		<button onclick={onToggleExpand} class="flex flex-1 items-center gap-3 text-left">
			<svg
				class="h-4 w-4 shrink-0 text-surface-400 transition-transform {expanded ? 'rotate-90' : ''}"
				fill="none" stroke="currentColor" viewBox="0 0 24 24"
			>
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
			</svg>
			<div class="min-w-0 flex-1">
				<div class="flex items-center gap-2">
					<span class="text-laya-base font-medium text-surface-200">{provider.name}</span>
					<span class="rounded-full bg-surface-600 px-2 py-0.5 text-laya-micro text-surface-400">
						{typeLabel}
					</span>
					{#if testResult}
						<span class="h-2 w-2 rounded-full {testResult.reachable ? (testResult.inference_ok ? 'bg-green-500' : 'bg-yellow-500') : 'bg-red-500'}"></span>
					{/if}
				</div>
				<p class="mt-0.5 truncate text-laya-secondary text-surface-500">{provider.base_url}</p>
			</div>
		</button>

		<div class="flex items-center gap-1.5">
			<button
				onclick={onTest}
				disabled={testing}
				class="rounded px-2 py-1 text-laya-secondary text-surface-400 transition-colors hover:bg-surface-600 hover:text-surface-300 disabled:opacity-50"
				title="Test connection"
			>
				{#if testing}
					<svg class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
						<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
						<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
					</svg>
				{:else}
					Test
				{/if}
			</button>
			<button
				onclick={startEdit}
				class="rounded px-2 py-1 text-laya-secondary text-surface-400 transition-colors hover:bg-surface-600 hover:text-surface-300"
			>
				Edit
			</button>
			<button
				onclick={onDelete}
				disabled={deleting}
				class="rounded px-2 py-1 text-laya-secondary text-red-400/70 transition-colors hover:bg-red-500/10 hover:text-red-400 disabled:opacity-50"
			>
				{deleting ? '...' : 'Remove'}
			</button>
		</div>
	</div>

	<!-- Test result -->
	{#if testResult}
		<div class="border-t border-surface-600/50 px-4 py-2 text-laya-secondary">
			{#if testResult.reachable}
				<div class="flex items-center gap-4 text-surface-400">
					<span class="text-green-400">Connected</span>
					<span>{testResult.models_count} model{testResult.models_count !== 1 ? 's' : ''}</span>
					<span>Inference: <span class="{testResult.inference_ok ? 'text-green-400' : 'text-yellow-400'}">{testResult.inference_ok ? 'OK' : 'failed'}</span></span>
					<span>{testResult.latency_ms}ms</span>
				</div>
			{:else}
				<span class="text-red-400">{testResult.error || 'Unreachable'}</span>
			{/if}
		</div>
	{/if}

	<!-- Edit form -->
	{#if editing}
		<div class="border-t border-surface-600/50 px-4 py-3 space-y-3">
			<div class="grid grid-cols-2 gap-3">
				<input
					type="text"
					bind:value={editForm.name}
					placeholder="Display name"
					class="rounded-md border border-surface-600 bg-surface-700 px-3 py-1.5 text-laya-base text-surface-100 placeholder:text-surface-500"
				/>
				<input
					type="text"
					bind:value={editForm.base_url}
					placeholder="Base URL"
					class="rounded-md border border-surface-600 bg-surface-700 px-3 py-1.5 text-laya-base text-surface-100 placeholder:text-surface-500"
				/>
			</div>
			<input
				type="password"
				bind:value={editForm.api_key}
				placeholder="New API key (leave blank to keep current)"
				class="w-full rounded-md border border-surface-600 bg-surface-700 px-3 py-1.5 text-laya-base text-surface-100 placeholder:text-surface-500"
			/>
			<div class="flex justify-end gap-2">
				<button
					onclick={() => { editing = false; }}
					class="rounded-md px-3 py-1.5 text-laya-base text-surface-400 hover:text-surface-300"
				>
					Cancel
				</button>
				<button
					onclick={saveEdit}
					disabled={editSaving}
					class="rounded-md bg-laya-orange px-3 py-1.5 text-laya-base font-medium text-surface-900 transition-colors hover:bg-laya-gold disabled:opacity-50"
				>
					{editSaving ? 'Saving...' : 'Save'}
				</button>
			</div>
		</div>
	{/if}

	<!-- Expanded model list -->
	{#if expanded}
		<div transition:slide={{ duration: $reducedMotion ? 0 : 200 }} class="border-t border-surface-600/50 px-4 py-3">
			{#if !models}
				<p class="text-laya-secondary text-surface-500">Loading models...</p>
			{:else if models.length === 0}
				<p class="text-laya-secondary text-surface-500">No models found. Is the server running?</p>
			{:else}
				<div class="space-y-1.5">
					{#each models as model}
						<div class="flex items-center gap-3 rounded px-2 py-1.5 text-laya-secondary hover:bg-surface-700/50">
							<div class="flex items-center gap-1.5 min-w-0 flex-1">
								{#if model.loaded}
									<span class="h-1.5 w-1.5 shrink-0 rounded-full bg-green-500" title="Loaded"></span>
								{:else}
									<span class="h-1.5 w-1.5 shrink-0 rounded-full bg-surface-500" title="Not loaded"></span>
								{/if}
								<span class="truncate text-surface-200">{model.name}</span>
							</div>
							<div class="flex items-center gap-2 shrink-0 text-surface-500">
								{#if model.params}
									<span>{model.params}</span>
								{/if}
								{#if model.quantization}
									<span class="rounded bg-surface-600 px-1.5 py-0.5">{model.quantization}</span>
								{/if}
								{#if model.max_context_length}
									<span>{Math.round(model.max_context_length / 1024)}K ctx</span>
								{/if}
								{#if model.supports_tool_calling}
									<span class="rounded bg-blue-500/15 px-1.5 py-0.5 text-blue-400" title="Supports tool calling">tools</span>
								{/if}
								{#if model.supports_vision}
									<span class="rounded bg-purple-500/15 px-1.5 py-0.5 text-purple-400" title="Supports vision">vision</span>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	{/if}
</div>
