<!-- Copyright 2026 Aayush Chawla -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
	import { slide } from 'svelte/transition';
	import { engineApi } from '$lib/api/engine';
	import { glassTheme } from '$lib/stores/glassTheme';
	import { reducedMotion } from '$lib/stores/reducedMotion';
	import type { PipelineSettings } from '$lib/api/types';

	let { pipeline = $bindable() }: { pipeline: PipelineSettings } = $props();

	let showAdvanced = $state(false);
	let savingPipeline = $state(false);
	let pipelineSaveTimer: ReturnType<typeof setTimeout> | null = null;

	function debounceSavePipeline() {
		if (pipelineSaveTimer) clearTimeout(pipelineSaveTimer);
		pipelineSaveTimer = setTimeout(savePipeline, 600);
	}

	async function savePipeline() {
		savingPipeline = true;
		try {
			await engineApi.updateSettings({ pipeline } as any);
		} catch (e) {
			console.error('Failed to save pipeline settings:', e);
		} finally {
			savingPipeline = false;
		}
	}
</script>

<div class="{$glassTheme ? 'glass-section' : 'rounded-lg border border-surface-700 bg-surface-800'}">
	<button
		onclick={() => { showAdvanced = !showAdvanced; }}
		class="flex w-full items-center justify-between p-5 text-left"
	>
		<div>
			<h3 class="text-laya-heading font-medium">Advanced</h3>
			<p class="text-laya-secondary text-surface-500">Model timeout, retry attempts, and request concurrency</p>
		</div>
		{#if savingPipeline}
			<span class="text-laya-micro text-laya-orange">Saving…</span>
		{/if}
		<svg
			class="h-5 w-5 shrink-0 text-surface-400 transition-transform {showAdvanced ? 'rotate-180' : ''}"
			fill="none" stroke="currentColor" viewBox="0 0 24 24"
		>
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
		</svg>
	</button>

	{#if showAdvanced}
		<div transition:slide={{ duration: $reducedMotion ? 0 : 200 }} class="border-t border-surface-700 p-5 space-y-5">
			<!-- Model Timeout -->
			<div class="grid grid-cols-[200px_1fr_auto] items-center gap-4">
				<div>
					<label for="model-timeout" class="text-laya-base text-surface-300">Model Timeout</label>
					<p class="text-laya-micro text-surface-500">Max seconds to wait for an LLM response. Increase for slow local models.</p>
				</div>
				<input
					id="model-timeout"
					type="range"
					min="30"
					max="900"
					step="30"
					bind:value={pipeline.model_timeout}
					oninput={debounceSavePipeline}
					class="w-full accent-laya-orange"
				/>
				<div class="flex items-center gap-1.5">
					<input
						type="number"
						min="30"
						max="900"
						bind:value={pipeline.model_timeout}
						oninput={debounceSavePipeline}
						class="w-16 rounded-md border border-surface-600 bg-surface-700 px-2 py-1 text-center text-laya-base text-surface-200"
					/>
					<span class="text-laya-secondary text-surface-500">sec</span>
				</div>
			</div>

			<!-- LLM Retries (per call) -->
			<div class="grid grid-cols-[200px_1fr_auto] items-center gap-4">
				<div>
					<label for="llm-retries" class="text-laya-base text-surface-300">LLM Retries</label>
					<p class="text-laya-micro text-surface-500">Retries per LLM call on timeout or transient error (fast, seconds apart).</p>
				</div>
				<input
					id="llm-retries"
					type="range"
					min="1"
					max="5"
					step="1"
					bind:value={pipeline.llm_retries}
					oninput={debounceSavePipeline}
					class="w-full accent-laya-orange"
				/>
				<div class="flex items-center gap-1.5">
					<input
						type="number"
						min="1"
						max="5"
						bind:value={pipeline.llm_retries}
						oninput={debounceSavePipeline}
						class="w-16 rounded-md border border-surface-600 bg-surface-700 px-2 py-1 text-center text-laya-base text-surface-200"
					/>
					<span class="text-laya-secondary text-surface-500">tries</span>
				</div>
			</div>

			<!-- Event Queue Retries -->
			<div class="grid grid-cols-[200px_1fr_auto] items-center gap-4">
				<div>
					<label for="max-retries" class="text-laya-base text-surface-300">Event Queue Retries</label>
					<p class="text-laya-micro text-surface-500">Times a failed event is re-queued with exponential backoff (slow, minutes apart).</p>
				</div>
				<input
					id="max-retries"
					type="range"
					min="1"
					max="10"
					step="1"
					bind:value={pipeline.max_retry_attempts}
					oninput={debounceSavePipeline}
					class="w-full accent-laya-orange"
				/>
				<div class="flex items-center gap-1.5">
					<input
						type="number"
						min="1"
						max="10"
						bind:value={pipeline.max_retry_attempts}
						oninput={debounceSavePipeline}
						class="w-16 rounded-md border border-surface-600 bg-surface-700 px-2 py-1 text-center text-laya-base text-surface-200"
					/>
					<span class="text-laya-secondary text-surface-500">tries</span>
				</div>
			</div>

			<!-- Request Concurrency -->
			<div class="grid grid-cols-[200px_1fr_auto] items-center gap-4">
				<div>
					<label for="max-concurrent" class="text-laya-base text-surface-300">Request Concurrency</label>
					<p class="text-laya-micro text-surface-500">Max events processed in parallel. Lower for local GPU models.</p>
				</div>
				<input
					id="max-concurrent"
					type="range"
					min="1"
					max="20"
					step="1"
					bind:value={pipeline.max_concurrent_events}
					oninput={debounceSavePipeline}
					class="w-full accent-laya-orange"
				/>
				<div class="flex items-center gap-1.5">
					<input
						type="number"
						min="1"
						max="20"
						bind:value={pipeline.max_concurrent_events}
						oninput={debounceSavePipeline}
						class="w-16 rounded-md border border-surface-600 bg-surface-700 px-2 py-1 text-center text-laya-base text-surface-200"
					/>
					<span class="text-laya-secondary text-surface-500">events</span>
				</div>
			</div>

		</div>
	{/if}
</div>
