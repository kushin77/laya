<!-- Copyright 2026 Aayush Chawla -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
	import { engineApi } from '$lib/api/engine';
	import { glassTheme } from '$lib/stores/glassTheme';

	let { apiKeys = $bindable(), onKeysChanged }: {
		apiKeys: Record<string, boolean>;
		onKeysChanged: () => void | Promise<void>;
	} = $props();

	const cloudProviders = [
		{ id: 'anthropic', label: 'Anthropic', envVar: 'ANTHROPIC_API_KEY' },
		{ id: 'openai', label: 'OpenAI', envVar: 'OPENAI_API_KEY' },
		{ id: 'google', label: 'Google', envVar: 'GOOGLE_API_KEY' },
		{ id: 'openrouter', label: 'OpenRouter', envVar: 'OPENROUTER_API_KEY' }
	];

	let keyInputs = $state<Record<string, string>>({
		anthropic: '',
		openai: '',
		google: '',
		openrouter: ''
	});

	let savingKey = $state<string | null>(null);

	async function saveApiKey(provider: string) {
		const key = keyInputs[provider];
		if (!key.trim()) return;
		savingKey = provider;
		try {
			await engineApi.setApiKey(provider, key.trim());
			apiKeys[provider] = true;
			keyInputs[provider] = '';
			await onKeysChanged();
		} catch (e) {
			console.error('Failed to save API key:', e);
		} finally {
			savingKey = null;
		}
	}

	async function removeApiKey(provider: string) {
		try {
			await engineApi.deleteApiKey(provider);
			apiKeys[provider] = false;
			await onKeysChanged();
		} catch (e) {
			console.error('Failed to remove API key:', e);
		}
	}
</script>

<div class="{$glassTheme ? 'glass-section' : 'rounded-lg border border-surface-700 bg-surface-800'} p-5">
	<h3 class="mb-4 text-laya-heading font-medium">API Keys</h3>
	<p class="mb-4 text-laya-base text-surface-400">
		Keys are stored securely in your OS keychain. They are never sent to the UI.
	</p>
	<div class="space-y-4">
		{#each cloudProviders as provider}
			<div class="flex items-center gap-3">
				<div class="flex w-28 items-center gap-2">
					<span
						class="h-2 w-2 rounded-full {apiKeys[provider.id]
							? 'bg-green-500'
							: 'bg-surface-500'}"
					></span>
					<span class="text-laya-base text-surface-300">{provider.label}</span>
				</div>

				{#if apiKeys[provider.id]}
					<span class="text-laya-base text-green-400">Configured</span>
					<button
						onclick={() => removeApiKey(provider.id)}
						class="ml-auto text-laya-base text-red-400 transition-colors hover:text-red-300"
					>
						Remove
					</button>
				{:else}
					<input
						type="password"
						bind:value={keyInputs[provider.id]}
						placeholder="Enter API key..."
						class="flex-1 rounded-md border border-surface-600 bg-surface-700 px-3 py-1.5 text-laya-base text-surface-100 placeholder:text-surface-500"
					/>
					<button
						onclick={() => saveApiKey(provider.id)}
						disabled={!keyInputs[provider.id].trim() || savingKey === provider.id}
						class="rounded-md bg-primary-600 px-3 py-1.5 text-laya-base font-medium text-white transition-colors hover:bg-primary-500 disabled:opacity-50"
					>
						{savingKey === provider.id ? 'Saving...' : 'Save'}
					</button>
				{/if}
			</div>
		{/each}
	</div>
</div>
