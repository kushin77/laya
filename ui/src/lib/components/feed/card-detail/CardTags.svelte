<!-- Copyright 2026 Aayush Chawla -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
	import type { ActionCard, Tag, TagAssignment } from '$lib/api/types';
	import { engineApi } from '$lib/api/engine';
	import { portal } from '$lib/actions/portal';
	import { glassTheme } from '$lib/stores/glassTheme';

	let { card }: { card: ActionCard } = $props();

	let cardTags = $state<TagAssignment[]>([]);
	let allTags = $state<Tag[]>([]);
	let tagInput = $state('');
	let showTagDropdown = $state(false);
	let addingTag = $state(false);
	let tagInputEl: HTMLInputElement | undefined = $state();
	let tagDropdownPos = $state({ top: 0, left: 0 });

	function updateTagDropdownPos() {
		if (tagInputEl) {
			const r = tagInputEl.getBoundingClientRect();
			tagDropdownPos = { top: r.bottom + 4, left: r.left };
		}
	}

	$effect(() => {
		if (!showTagDropdown || !tagInputEl) return;
		let raf: number;
		function tick() {
			updateTagDropdownPos();
			raf = requestAnimationFrame(tick);
		}
		raf = requestAnimationFrame(tick);
		return () => cancelAnimationFrame(raf);
	});

	const currentCardTags = $derived(card.tags ?? []);
	$effect(() => {
		cardTags = currentCardTags;
	});
	$effect(() => {
		engineApi.listTags().then(r => { allTags = r.tags; }).catch(() => {});
	});

	const filteredTags = $derived(
		tagInput.trim()
			? allTags.filter(t =>
				t.name.toLowerCase().includes(tagInput.toLowerCase()) &&
				!cardTags.some(ct => ct.tag_id === t.tag_id)
			).slice(0, 5)
			: allTags.filter(t => !cardTags.some(ct => ct.tag_id === t.tag_id)).slice(0, 5)
	);

	async function addTag(nameOrId: string | number) {
		addingTag = true;
		try {
			const result = await engineApi.assignTag({
				tag_name_or_id: nameOrId,
				target_type: 'card',
				target_id: card.card_id,
				create_if_missing: true
			});
			const matchedTag = allTags.find(t => t.tag_id === result.tag_id);
			cardTags = [...cardTags, {
				tag_id: result.tag_id,
				tag_name: result.tag_name,
				color: matchedTag?.color,
				is_system: matchedTag?.is_system ?? false,
				assigned_by: 'user'
			}];
			tagInput = '';
			showTagDropdown = false;
			// Refresh available tags in case a new one was created
			engineApi.listTags().then(r => { allTags = r.tags; }).catch(() => {});
		} catch { /* handled silently */ }
		addingTag = false;
	}

	async function removeTag(tagId: number) {
		try {
			await engineApi.removeTag({ tag_id: tagId, target_type: 'card', target_id: card.card_id });
			cardTags = cardTags.filter(t => t.tag_id !== tagId);
		} catch { /* handled silently */ }
	}
</script>

<div class="mb-5">
	<div class="flex flex-wrap items-center gap-1.5">
		{#each cardTags as tag}
			<span
				class="{tag.is_system ? 'tag-chip-system' : 'tag-chip-user'} inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
				style="--tag-color: {tag.color ?? (tag.is_system ? '#6B7280' : '#C4956B')}"
			>
				{tag.tag_name}
				{#if !tag.is_system}
					<button
						class="ml-0.5 hover:opacity-70 cursor-pointer"
						title="Remove tag"
						onclick={() => removeTag(tag.tag_id)}
					>
						<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
						</svg>
					</button>
				{/if}
			</span>
		{/each}
		<div class="relative">
			<input
				bind:this={tagInputEl}
				type="text"
				class="h-6 w-24 rounded-full border border-surface-600/50 bg-transparent px-2 text-xs text-surface-300 placeholder-surface-500 outline-none focus:border-laya-orange/50 focus:w-36 transition-all"
				placeholder="Add tag..."
				bind:value={tagInput}
				onfocus={() => { showTagDropdown = true; }}
				onblur={() => { setTimeout(() => { showTagDropdown = false; }, 150); }}
				onkeydown={(e) => {
					if (e.key === 'Enter' && tagInput.trim()) {
						e.preventDefault();
						addTag(tagInput.trim());
					}
				}}
				disabled={addingTag || cardTags.length >= 10}
			/>
		</div>
	</div>
</div>

{#if showTagDropdown && filteredTags.length > 0}
	<div
		use:portal
		class="fixed z-[100] w-48 rounded-lg border p-1 {$glassTheme ? 'glass-menu' : 'border-surface-600 bg-surface-900 shadow-xl shadow-black/50'}"
		style="top: {tagDropdownPos.top}px; left: {tagDropdownPos.left}px;"
		role="listbox"
	>
		{#each filteredTags as tag}
			<button
				class="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-xs text-surface-300 transition-colors hover:bg-surface-700/50 cursor-pointer"
				role="option"
				aria-selected={false}
				onmousedown={(e) => { e.preventDefault(); addTag(tag.tag_id); }}
			>
				{#if tag.color}
					<span class="h-2 w-2 rounded-full shrink-0" style="background-color: {tag.color}"></span>
				{/if}
				{tag.name}
			</button>
		{/each}
	</div>
{/if}
