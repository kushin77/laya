<!-- Copyright 2026 Aayush Chawla -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
	import { engineApi } from '$lib/api/engine';
	import { glassTheme } from '$lib/stores/glassTheme';
	import type { ProviderModels, AgentBackend } from '$lib/api/types';
	import { portal } from '$lib/actions/portal';
	import { CODING_AGENTS } from '$lib/config';
	import { agentModelString, applyAgentMode, applySelectAgent } from '$lib/utils/agentModel';
	import ModelSelect from '../ModelSelect.svelte';

	let {
		models = $bindable(),
		availableModels,
		modelsLoading,
		fetchModels,
		agentMode = $bindable(),
		selectedAgent = $bindable(),
		agentBackends,
		providerBackup = $bindable()
	}: {
		models: Record<string, string>;
		availableModels: ProviderModels[];
		modelsLoading: boolean;
		fetchModels: (refresh?: boolean) => Promise<void>;
		agentMode: boolean;
		selectedAgent: string;
		agentBackends: AgentBackend[];
		providerBackup: Record<string, string>;
	} = $props();

	const roles = [
		{ id: 'router', label: 'Router', hint: 'Classifies incoming events',
			guide: 'Classifies each incoming event by persona (Engineer/Comms/Ops) and priority. Output is structured JSON, not prose. A small, fast model works well here.' },
		{ id: 'stager', label: 'Stager', hint: 'Synthesises action cards',
			guide: 'Reads the classified event and writes the action card: headline, summary, suggested actions, and draft replies. Quality of card content scales directly with model capability — use a stronger model if you want richer summaries.' },
		{ id: 'chat', label: 'Chat', hint: 'Conversational responses',
			guide: 'Powers the chat panel where you ask questions about your cards, events, and workspace. A capable model gives better conversational and reasoning quality.' },
		{ id: 'trace', label: 'Coherence', hint: 'Generates trace narratives',
			guide: 'Generates narrative summaries when you search for related activity across platforms. The heavy lifting is semantic search — the model just synthesises results into prose. A smaller model is usually sufficient.' },
		{ id: 'omni', label: 'Omni', hint: 'Resynthesises rolling summaries',
			guide: 'Periodically compresses your rolling cross-platform summary into a concise digest. Needs to merge and deduplicate information across many events. A mid-tier model balances cost and coherence well.' }
	];

	// Only the structured, non-streaming roles can run on an agent. Chat + Coherence need
	// a streaming tool-loop the agents can't run for us, so they stay on a model/local
	// provider (keep their dropdowns) even when the agent backend is selected.
	const AGENT_ROLES = ['router', 'stager', 'omni'];
	const DEFAULT_MODELS: Record<string, string> = {
		router: 'claude-haiku-4-5', stager: 'claude-sonnet-4-6', omni: 'claude-sonnet-4-6'
	};
	const AGENT_LABELS: Record<string, string> = Object.fromEntries(
		CODING_AGENTS.filter((a) => a.value !== 'none').map((a) => [a.value, a.label])
	);
	const AGENT_MODEL_PLACEHOLDERS: Record<string, string> = {
		claude_code: 'e.g. claude-sonnet-4-6 — blank uses Claude Code’s default',
		codex_cli: 'e.g. gpt-5-codex — blank uses Codex’s default',
		gemini_cli: 'e.g. gemini-2.5-pro — blank uses Gemini’s default',
		pi_cli: 'e.g. lmstudio/qwen3.6-35b-a3b — blank uses Pi’s default'
	};

	let selectedBackend = $derived(agentBackends.find((b) => b.agent_id === selectedAgent));

	let saving = $state(false);
	let guideTooltip = $state<{ text: string; top: number; left: number } | null>(null);

	function showGuide(e: MouseEvent, text: string) {
		const el = e.currentTarget as HTMLElement;
		const r = el.getBoundingClientRect();
		guideTooltip = { text, top: r.bottom + 8, left: r.left + r.width / 2 };
	}
	function hideGuide() { guideTooltip = null; }

	async function saveModels() {
		saving = true;
		try {
			await engineApi.updateSettings({ models } as any);
		} catch (e) {
			console.error('Failed to save models:', e);
		} finally {
			saving = false;
		}
	}

	function handleModelChange(role: string) {
		return (value: string) => {
			models[role] = value;
			saveModels();
		};
	}

	function setAgentMode(on: boolean) {
		if (on === agentMode) return;
		const result = applyAgentMode(models, providerBackup, on, selectedAgent, AGENT_ROLES, DEFAULT_MODELS);
		models = result.models;
		providerBackup = result.providerBackup;
		agentMode = on;
		saveModels();
	}

	function selectAgent(agentId: string) {
		selectedAgent = agentId;
		models = applySelectAgent(models, agentId, AGENT_ROLES);
		saveModels();
	}

	function handleAgentModelInput(role: string) {
		return (e: Event) => {
			const typed = (e.target as HTMLInputElement).value.trim();
			models[role] = typed ? `agent/${selectedAgent}/${typed}` : `agent/${selectedAgent}`;
			saveModels();
		};
	}
</script>

<div class="{$glassTheme ? 'glass-section' : 'rounded-lg border border-surface-700 bg-surface-800'} p-5">
	<div class="mb-4 flex items-center justify-between">
		<div>
			<h3 class="mb-1 text-laya-heading font-medium">Model Selection</h3>
			<p class="text-laya-secondary text-surface-500">Choose a model for each pipeline stage, or switch the backend to an installed CLI agent.</p>
		</div>
		<div class="flex items-center gap-3">
			{#if saving}
				<span class="text-laya-micro text-laya-orange">Saving…</span>
			{/if}
		<button
			onclick={() => fetchModels(true)}
			disabled={modelsLoading}
			class="rounded-md border border-surface-600 px-2.5 py-1.5 text-laya-secondary text-surface-400 transition-colors hover:border-surface-500 hover:text-surface-300 disabled:opacity-50"
			title="Refresh model list"
		>
			{#if modelsLoading}
				<svg class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
					<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
					<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
				</svg>
			{:else}
				Refresh
			{/if}
		</button>
		</div>
	</div>
	<!-- Inference backend: model provider (dropdowns) vs installed agent (typed model strings) -->
	<div class="mb-4 rounded-lg border {$glassTheme ? 'border-white/10' : 'border-surface-700'} p-3">
		<div class="inline-flex rounded-md border {$glassTheme ? 'border-white/15' : 'border-surface-600'} p-0.5">
			<button
				type="button"
				onclick={() => setAgentMode(false)}
				class="rounded px-3 py-1.5 text-laya-base transition-colors {!agentMode ? 'bg-laya-orange/15 text-laya-orange' : 'text-surface-400 hover:text-surface-300'}"
			>Model provider</button>
			<button
				type="button"
				onclick={() => setAgentMode(true)}
				class="flex items-center gap-1.5 rounded px-3 py-1.5 text-laya-base transition-colors {agentMode ? 'bg-laya-orange/15 text-laya-orange' : 'text-surface-400 hover:text-surface-300'}"
			>Installed agent
				<span class="rounded bg-laya-gold/25 px-1 text-laya-micro font-semibold uppercase tracking-wide text-laya-amber">Beta</span>
			</button>
		</div>
		<p class="mt-2 text-laya-micro text-surface-500">
			{#if agentMode}
				Structured stages run through an installed CLI agent on its own subscription — no API key or local VRAM. Chat &amp; Coherence keep using a model provider.
			{:else}
				Use cloud or local-provider models for every stage.
			{/if}
		</p>

		{#if agentMode}
			<div class="mt-3 flex flex-wrap gap-2">
				{#each agentBackends as b}
					<button
						type="button"
						onclick={() => b.available && selectAgent(b.agent_id)}
						disabled={!b.available}
						title={b.hint}
						class="flex items-center gap-2 rounded-md border px-3 py-1.5 text-laya-base transition-colors {selectedAgent === b.agent_id ? 'border-laya-orange/40 bg-laya-orange/10 text-laya-orange' : 'border-surface-600 text-surface-300 hover:border-surface-500'} {!b.available ? 'cursor-not-allowed opacity-50' : ''}"
					>
						{AGENT_LABELS[b.agent_id] || b.agent_id}
						<span class="rounded px-1.5 py-0.5 text-laya-micro {b.tier === 'native' ? 'bg-laya-gold/25 text-laya-amber' : 'bg-surface-700 text-surface-400'}">
							{b.tier === 'native' ? 'native schema' : 'best-effort'}
						</span>
						{#if !b.available}
							<span class="text-laya-micro text-surface-500">not detected</span>
						{/if}
					</button>
				{/each}
			</div>
			{#if selectedBackend?.hint}
				<p class="mt-2 text-laya-micro text-surface-500">{selectedBackend.hint}</p>
			{/if}
		{/if}
	</div>

	<div class="space-y-4">
		{#each roles as role}
			<div class="grid grid-cols-[140px_auto_1fr] items-center gap-2">
				<div>
					<label for="{role.id}-model" class="text-laya-base text-surface-400">{role.label}</label>
					<p class="text-laya-micro text-surface-500">{role.hint}</p>
				</div>
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<div
					class="cursor-help"
					onmouseenter={(e) => showGuide(e, role.guide)}
					onmouseleave={hideGuide}
				>
					<svg class="h-3.5 w-3.5 shrink-0 text-surface-600 transition-colors hover:text-laya-orange" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01" />
						<circle cx="12" cy="12" r="10" stroke-width="2" />
					</svg>
				</div>
				{#if agentMode && AGENT_ROLES.includes(role.id)}
					<input
						id="{role.id}-model"
						type="text"
						value={agentModelString(models[role.id])}
						onchange={handleAgentModelInput(role.id)}
						placeholder={AGENT_MODEL_PLACEHOLDERS[selectedAgent] || 'Model string (blank = agent default)'}
						spellcheck="false"
						autocapitalize="off"
						class="w-full rounded-md border px-3 py-2 font-mono text-laya-base text-surface-100 placeholder:text-surface-500 focus:outline-none {$glassTheme ? 'glass-input' : 'border-surface-600 bg-surface-700 focus:border-surface-500'}"
					/>
				{:else}
					<ModelSelect
						id="{role.id}-model"
						bind:value={models[role.id]}
						providers={availableModels}
						onchange={handleModelChange(role.id)}
					/>
				{/if}
			</div>
		{/each}
	</div>
</div>

{#if guideTooltip}
	<div
		use:portal
		class="pointer-events-none fixed z-[100] w-64 -translate-x-1/2 rounded-lg border border-transparent glass-tooltip px-3 py-2.5 text-laya-secondary leading-relaxed shadow-lg"
		style="top: {guideTooltip.top}px; left: {guideTooltip.left}px;"
	>
		{guideTooltip.text}
	</div>
{/if}
