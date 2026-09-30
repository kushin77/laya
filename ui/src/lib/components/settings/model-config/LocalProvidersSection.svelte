<!-- Copyright 2026 Aayush Chawla -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
	import { slide } from 'svelte/transition';
	import { engineApi } from '$lib/api/engine';
	import { glassTheme } from '$lib/stores/glassTheme';
	import { reducedMotion } from '$lib/stores/reducedMotion';
	import type { CustomProvider, CustomProviderTestResult, DiscoveredModel } from '$lib/api/types';
	import ProviderRow from './ProviderRow.svelte';

	let { customProviders = $bindable(), fetchModels }: {
		customProviders: CustomProvider[];
		fetchModels: (refresh?: boolean) => Promise<void>;
	} = $props();

	const providerTypes = [
		{ id: 'lmstudio', label: 'LM Studio', defaultUrl: 'http://localhost:1234' },
		{ id: 'ollama', label: 'Ollama', defaultUrl: 'http://localhost:11434' },
		{ id: 'openai_compatible', label: 'OpenAI Compatible', defaultUrl: 'http://localhost:8080' }
	];

	let showAddProvider = $state(false);
	let newProvider = $state({ name: '', base_url: '', provider_type: 'lmstudio', api_key: '' });
	let addingProvider = $state(false);
	let addError = $state('');

	let testingProvider = $state<string | null>(null);
	let testResults = $state<Record<string, CustomProviderTestResult>>({});
	let providerModels = $state<Record<string, DiscoveredModel[]>>({});
	let expandedProvider = $state<string | null>(null);
	let deletingProvider = $state<string | null>(null);

	function handleProviderTypeChange(type: string) {
		newProvider.provider_type = type;
		const preset = providerTypes.find((p) => p.id === type);
		if (preset && !newProvider.base_url) {
			newProvider.base_url = preset.defaultUrl;
		}
	}

	async function addProvider() {
		if (!newProvider.name.trim() || !newProvider.base_url.trim()) return;
		addingProvider = true;
		addError = '';
		try {
			const resp = await engineApi.addCustomProvider({
				name: newProvider.name.trim(),
				base_url: newProvider.base_url.trim(),
				provider_type: newProvider.provider_type,
				api_key: newProvider.api_key.trim() || undefined
			});
			customProviders = [...customProviders, resp.provider];
			newProvider = { name: '', base_url: '', provider_type: 'lmstudio', api_key: '' };
			showAddProvider = false;
			// Refresh models to include models from new provider
			await fetchModels(true);
		} catch (e: any) {
			addError = e.message || 'Failed to add provider';
		} finally {
			addingProvider = false;
		}
	}

	async function deleteProvider(providerId: string) {
		deletingProvider = providerId;
		try {
			await engineApi.deleteCustomProvider(providerId);
			customProviders = customProviders.filter((p) => p.id !== providerId);
			delete testResults[providerId];
			delete providerModels[providerId];
			if (expandedProvider === providerId) expandedProvider = null;
			await fetchModels(true);
		} catch (e) {
			console.error('Failed to delete provider:', e);
		} finally {
			deletingProvider = null;
		}
	}

	async function testProvider(providerId: string) {
		testingProvider = providerId;
		try {
			const result = await engineApi.testCustomProvider(providerId);
			testResults[providerId] = result;
		} catch (e: any) {
			testResults[providerId] = {
				provider_id: providerId,
				reachable: false,
				models_count: 0,
				llm_count: 0,
				embedding_count: 0,
				inference_ok: false,
				latency_ms: 0,
				error: e.message || 'Connection failed'
			};
		} finally {
			testingProvider = null;
		}
	}

	async function toggleExpand(providerId: string) {
		if (expandedProvider === providerId) {
			expandedProvider = null;
			return;
		}
		expandedProvider = providerId;
		if (!providerModels[providerId]) {
			try {
				const resp = await engineApi.getProviderModels(providerId);
				providerModels[providerId] = resp.models;
			} catch (e) {
				console.error('Failed to fetch provider models:', e);
				providerModels[providerId] = [];
			}
		}
	}

	async function saveEdit(providerId: string, updates: Record<string, string>) {
		const resp = await engineApi.updateCustomProvider(providerId, updates);
		customProviders = customProviders.map((p) => (p.id === providerId ? resp.provider : p));
		// Clear cached models for this provider and refresh
		delete providerModels[providerId];
		delete testResults[providerId];
		await fetchModels(true);
	}

	function getTypeLabel(type: string) {
		return providerTypes.find((p) => p.id === type)?.label ?? type;
	}
</script>

<div class="{$glassTheme ? 'glass-section' : 'rounded-lg border border-surface-700 bg-surface-800'} p-5">
	<div class="mb-4 flex items-center justify-between">
		<div>
			<h3 class="mb-1 text-laya-heading font-medium">Local Providers</h3>
			<p class="text-laya-secondary text-surface-500">Connect to LM Studio, Ollama, or any OpenAI-compatible server running on your machine.</p>
		</div>
		<button
			onclick={() => { showAddProvider = !showAddProvider; addError = ''; }}
			class="rounded-md border border-surface-600 px-3 py-1.5 text-laya-base text-surface-400 transition-colors hover:border-surface-500 hover:text-surface-300"
		>
			{showAddProvider ? 'Cancel' : '+ Add Provider'}
		</button>
	</div>

	<!-- Add Provider Form -->
	{#if showAddProvider}
		<div transition:slide={{ duration: $reducedMotion ? 0 : 200 }} class="mb-5 rounded-md border border-surface-600 bg-surface-700/50 p-4 space-y-3">
			<div class="grid grid-cols-3 gap-3">
				{#each providerTypes as pt}
					<button
						onclick={() => handleProviderTypeChange(pt.id)}
						class="rounded-md border px-3 py-2 text-laya-base transition-colors
							{newProvider.provider_type === pt.id
								? 'border-laya-orange/50 bg-laya-orange/10 text-laya-orange'
								: 'border-surface-600 text-surface-400 hover:border-surface-500 hover:text-surface-300'}"
					>
						{pt.label}
					</button>
				{/each}
			</div>
			<div class="grid grid-cols-2 gap-3">
				<input
					type="text"
					bind:value={newProvider.name}
					placeholder="Display name (e.g. My LM Studio)"
					class="rounded-md border border-surface-600 bg-surface-700 px-3 py-2 text-laya-base text-surface-100 placeholder:text-surface-500"
				/>
				<input
					type="text"
					bind:value={newProvider.base_url}
					placeholder={providerTypes.find((p) => p.id === newProvider.provider_type)?.defaultUrl ?? 'http://localhost:1234'}
					class="rounded-md border border-surface-600 bg-surface-700 px-3 py-2 text-laya-base text-surface-100 placeholder:text-surface-500"
				/>
			</div>
			<input
				type="password"
				bind:value={newProvider.api_key}
				placeholder="API key (optional — leave blank if not required)"
				class="w-full rounded-md border border-surface-600 bg-surface-700 px-3 py-2 text-laya-base text-surface-100 placeholder:text-surface-500"
			/>
			{#if addError}
				<p class="text-laya-base text-red-400">{addError}</p>
			{/if}
			<div class="flex justify-end">
				<button
					onclick={addProvider}
					disabled={!newProvider.name.trim() || !newProvider.base_url.trim() || addingProvider}
					class="rounded-md bg-laya-orange px-4 py-2 text-laya-base font-medium text-surface-900 transition-colors hover:bg-laya-gold disabled:opacity-50"
				>
					{addingProvider ? 'Adding...' : 'Add Provider'}
				</button>
			</div>
		</div>
	{/if}

	<!-- Provider List -->
	{#if customProviders.length === 0 && !showAddProvider}
		<div class="rounded-md border border-dashed border-surface-600 py-8 text-center">
			<p class="text-laya-base text-surface-500">No local providers configured</p>
			<p class="mt-1 text-laya-secondary text-surface-600">Add LM Studio, Ollama, or another local server to use local models</p>
		</div>
	{:else}
		<div class="space-y-3">
			{#each customProviders as provider (provider.id)}
				<ProviderRow
					{provider}
					typeLabel={getTypeLabel(provider.provider_type)}
					testResult={testResults[provider.id]}
					testing={testingProvider === provider.id}
					deleting={deletingProvider === provider.id}
					expanded={expandedProvider === provider.id}
					models={providerModels[provider.id]}
					onTest={() => testProvider(provider.id)}
					onDelete={() => deleteProvider(provider.id)}
					onToggleExpand={() => toggleExpand(provider.id)}
					onSave={(updates) => saveEdit(provider.id, updates)}
				/>
			{/each}
		</div>
	{/if}
</div>
