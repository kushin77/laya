<!-- Copyright 2026 Aayush Chawla -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
	import { onMount } from 'svelte';
	import { engineApi } from '$lib/api/engine';
	import type { ProviderModels, CustomProvider, PipelineSettings, AgentBackend } from '$lib/api/types';
	import { loadBudget } from '$lib/stores/budget';
	import { loadAgentBudget } from '$lib/stores/agentBudget';
	import { parseAgentModel } from '$lib/utils/agentModel';
	import { CODING_AGENTS } from '$lib/config';
	import ApiKeysSection from './model-config/ApiKeysSection.svelte';
	import LocalProvidersSection from './model-config/LocalProvidersSection.svelte';
	import ModelSelectionSection from './model-config/ModelSelectionSection.svelte';
	import AgentUsageLimitsSection from './model-config/AgentUsageLimitsSection.svelte';
	import CostControlSection from './model-config/CostControlSection.svelte';
	import AdvancedPipelineSection from './model-config/AdvancedPipelineSection.svelte';

	const AGENT_ROLES = ['router', 'stager', 'omni'];
	const AGENT_LABELS: Record<string, string> = Object.fromEntries(
		CODING_AGENTS.filter((a) => a.value !== 'none').map((a) => [a.value, a.label])
	);

	let models = $state<Record<string, string>>({
		router: 'claude-haiku-4-5',
		stager: 'claude-sonnet-4-6',
		chat: 'claude-sonnet-4-6',
		trace: 'claude-sonnet-4-6',
		omni: 'claude-sonnet-4-6',
		local: 'ollama/llama3'
	});

	let apiKeys = $state<Record<string, boolean>>({
		anthropic: false,
		openai: false,
		google: false,
		openrouter: false
	});

	let loaded = $state(false);
	let availableModels = $state<ProviderModels[]>([]);
	let modelsLoading = $state(false);
	let customProviders = $state<CustomProvider[]>([]);

	// --- Agent inference backend (use an installed CLI agent as the LLM) ---
	let agentMode = $state(false);
	let selectedAgent = $state('claude_code');
	let agentBackends = $state<AgentBackend[]>([]);
	let providerBackup = $state<Record<string, string>>({});

	let pipeline = $state<PipelineSettings>({
		model_timeout: 120,
		llm_retries: 3,
		max_retry_attempts: 5,
		max_concurrent_events: 5,
		queue_poll_interval: 2
	});

	onMount(async () => {
		try {
			const [settings, providersResp] = await Promise.all([
				engineApi.getSettings(),
				engineApi.getCustomProviders()
			]);
			models = { ...models, ...settings.models };
			apiKeys = { ...apiKeys, ...settings.api_keys };
			if (settings.pipeline) pipeline = { ...pipeline, ...settings.pipeline };
			customProviders = providersResp.providers;
			loaded = true;
			// Infer agent-backend mode from the saved structured-role values.
			const inferred = AGENT_ROLES.map((r) => parseAgentModel(models[r])).find((p) => p);
			if (inferred) {
				agentMode = true;
				if (inferred.agentId) selectedAgent = inferred.agentId;
			}
			try {
				const backendsResp = await engineApi.getAgentBackends();
				agentBackends = backendsResp.backends;
			} catch (e) {
				console.error('Failed to load agent backends:', e);
			}
			await Promise.all([fetchModels(), loadBudget(), loadAgentBudget()]);
		} catch (e) {
			console.error('Failed to load settings:', e);
		}
	});

	async function fetchModels(refresh = false) {
		modelsLoading = true;
		try {
			const resp = await engineApi.getAvailableModels(refresh);
			availableModels = resp.providers;
		} catch (e) {
			console.error('Failed to fetch available models:', e);
		} finally {
			modelsLoading = false;
		}
	}
</script>

{#if !loaded}
	<div class="flex items-center justify-center py-12 text-surface-400">Loading settings...</div>
{:else}
	<div class="space-y-8">
		<ApiKeysSection bind:apiKeys onKeysChanged={() => fetchModels()} />

		<LocalProvidersSection bind:customProviders {fetchModels} />

		<ModelSelectionSection
			bind:models
			{availableModels}
			{modelsLoading}
			{fetchModels}
			bind:agentMode
			bind:selectedAgent
			{agentBackends}
			bind:providerBackup
		/>

		{#if agentMode}
			<AgentUsageLimitsSection {agentBackends} agentLabels={AGENT_LABELS} />
		{/if}

		<CostControlSection />

		<AdvancedPipelineSection bind:pipeline />
	</div>
{/if}
