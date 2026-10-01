<!-- Copyright 2026 Aayush Chawla -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		title = 'Delete permanently?',
		message,
		confirmLabel = 'Delete permanently',
		pendingLabel = 'Deleting...',
		deleting = false,
		onconfirm,
		oncancel,
	}: {
		title?: string;
		message: Snippet;
		confirmLabel?: string;
		pendingLabel?: string;
		deleting?: boolean;
		onconfirm: () => void;
		oncancel: () => void;
	} = $props();
</script>

<div
	class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
	role="dialog"
	aria-label="Confirm delete"
	tabindex="-1"
	onclick={(e) => { if (e.target === e.currentTarget) oncancel(); }}
	onkeydown={(e) => { if (e.key === 'Escape') oncancel(); }}
>
	<div class="mx-4 w-full max-w-sm rounded-xl border border-red-800/40 bg-surface-800 p-5 shadow-2xl">
		<div class="mb-3 flex items-start gap-3">
			<div class="mt-0.5 rounded-full bg-red-950/60 p-1.5">
				<svg class="h-4 w-4 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
				</svg>
			</div>
			<div>
				<h4 class="text-laya-base font-semibold text-surface-50">{title}</h4>
				<p class="mt-1 text-laya-secondary leading-relaxed text-surface-400">
					{@render message()}
				</p>
			</div>
		</div>
		<div class="flex justify-end gap-2">
			<button
				class="rounded-md px-3 py-1.5 text-laya-secondary text-surface-400 transition-colors hover:text-surface-200 disabled:opacity-50"
				onclick={oncancel}
				disabled={deleting}
			>
				Cancel
			</button>
			<button
				class="rounded-md bg-red-700 px-3 py-1.5 text-laya-secondary font-medium text-red-50 transition-colors hover:bg-red-600 disabled:opacity-50"
				onclick={onconfirm}
				disabled={deleting}
			>
				{deleting ? pendingLabel : confirmLabel}
			</button>
		</div>
	</div>
</div>
