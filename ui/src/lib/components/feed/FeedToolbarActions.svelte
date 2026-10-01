<!-- Copyright 2026 Aayush Chawla -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
	// Responsive toolbar actions: inline buttons when there's room, collapsed
	// into a single overflow menu when the toolbar is too narrow. The parent
	// owns the ResizeObserver that decides `collapsed` (it measures the whole
	// toolbar, not just this slice) and the filter-popover's open state (the
	// popover itself is rendered outside this component in the page).
	let {
		collapsed,
		menuOpen = $bindable(false),
		hasActiveFilters,
		activeFilterCount,
		recentDrawerOpen,
		showBookmarked,
		summaryModalOpen,
		hasUnread,
		markingAllRead,
		onOpenFilters,
		onToggleRecent,
		onToggleBookmarked,
		onMarkAllRead,
		onOpenSummary
	}: {
		collapsed: boolean;
		menuOpen?: boolean;
		hasActiveFilters: boolean;
		activeFilterCount: number;
		recentDrawerOpen: boolean;
		showBookmarked: boolean;
		summaryModalOpen: boolean;
		hasUnread: boolean;
		markingAllRead: boolean;
		onOpenFilters: (pos: { top: number; left: number }) => void;
		onToggleRecent: () => void;
		onToggleBookmarked: () => void;
		onMarkAllRead: () => void;
		onOpenSummary: () => void;
	} = $props();
</script>

{#if collapsed}
	<!-- Overflow menu for narrow toolbar -->
	<div class="feed-overflow-menu relative">
		<button
			onclick={() => (menuOpen = !menuOpen)}
			class="flex items-center gap-1 rounded-lg border px-2 py-1 text-laya-secondary transition-colors
				{hasActiveFilters || showBookmarked || recentDrawerOpen || summaryModalOpen
					? 'border-laya-orange/30 bg-laya-orange/10 text-laya-orange'
					: 'border-surface-700 bg-surface-800/60 text-surface-400 hover:text-surface-200 hover:border-surface-600'}"
			aria-label="More actions"
		>
			<svg class="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 24 24">
				<circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/>
			</svg>
		</button>
		{#if menuOpen}
			<div class="absolute right-0 top-full z-[100] mt-1 flex flex-col rounded-lg border border-surface-600 bg-surface-800 py-1 shadow-lg min-w-[160px]">
				<button
					class="flex w-full items-center gap-2 whitespace-nowrap px-4 py-1.5 text-laya-secondary transition-colors hover:bg-surface-700
						{hasActiveFilters ? 'text-laya-orange' : 'text-surface-300'}"
					onclick={(e: MouseEvent) => {
						const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
						onOpenFilters({ top: r.top, left: r.left - 264 });
					}}
				>
					<svg class="h-3.5 w-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
					</svg>
					Filters
					{#if hasActiveFilters}
						<span class="flex h-4 w-4 items-center justify-center rounded-full bg-laya-orange text-laya-micro font-bold text-surface-900">{activeFilterCount}</span>
					{/if}
				</button>
				<button
					class="flex w-full items-center gap-2 whitespace-nowrap px-4 py-1.5 text-laya-secondary transition-colors hover:bg-surface-700
						{recentDrawerOpen ? 'text-laya-orange' : 'text-surface-300'}"
					onclick={() => { onToggleRecent(); menuOpen = false; }}
				>
					<svg class="h-3.5 w-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
					</svg>
					Recent
				</button>
				<button
					class="flex w-full items-center gap-2 whitespace-nowrap px-4 py-1.5 text-laya-secondary transition-colors hover:bg-surface-700
						{showBookmarked ? 'text-laya-orange' : 'text-surface-300'}"
					onclick={() => { onToggleBookmarked(); menuOpen = false; }}
				>
					<svg class="h-3.5 w-3.5 shrink-0" fill={showBookmarked ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
					</svg>
					Bookmarks
				</button>
				<div class="my-0.5 border-t border-surface-700"></div>
					<button
						class="flex w-full items-center gap-2 whitespace-nowrap px-4 py-1.5 text-laya-secondary transition-colors
							{hasUnread ? 'text-surface-300 hover:bg-surface-700' : 'text-surface-600 cursor-not-allowed'}"
						onclick={() => { onMarkAllRead(); menuOpen = false; }}
						disabled={markingAllRead || !hasUnread}
					>
						<svg class="h-3.5 w-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
						</svg>
						Mark all read
					</button>
				<div class="my-0.5 border-t border-surface-700"></div>
				<button
					class="flex w-full items-center gap-2 whitespace-nowrap px-4 py-1.5 text-laya-secondary transition-colors hover:bg-surface-700
						{summaryModalOpen ? 'text-laya-orange' : 'text-surface-300'}"
					onclick={() => { onOpenSummary(); menuOpen = false; }}
				>
					<svg class="h-3.5 w-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
					</svg>
					Summary
				</button>
			</div>
		{/if}
	</div>
{:else}
	<!-- Inline action buttons -->
	<div class="filter-dropdown relative">
		<button
			onclick={(e: MouseEvent) => {
				const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
				onOpenFilters({ top: r.bottom + 6, left: r.left });
			}}
			class="relative flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-laya-secondary transition-colors
				{hasActiveFilters
					? 'border-laya-orange/30 bg-laya-orange/10 text-laya-orange'
					: 'border-surface-700 bg-surface-800/60 text-surface-400 hover:text-surface-200 hover:border-surface-600'}"
		>
			<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
			</svg>
			Filters
			{#if hasActiveFilters}
				<span class="flex h-4 w-4 items-center justify-center rounded-full bg-laya-orange text-laya-micro font-bold text-surface-900">{activeFilterCount}</span>
			{/if}
		</button>
	</div>

	<button
		onclick={onToggleRecent}
		class="flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-laya-secondary transition-colors
			{recentDrawerOpen
				? 'border-laya-orange/30 bg-laya-orange/10 text-laya-orange'
				: 'border-surface-700 bg-surface-800/60 text-surface-400 hover:text-surface-200 hover:border-surface-600'}"
	>
		<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
		</svg>
		Recent
	</button>

	<button
		onclick={onToggleBookmarked}
		class="flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-laya-secondary transition-colors
			{showBookmarked
				? 'border-laya-orange/30 bg-laya-orange/10 text-laya-orange'
				: 'border-surface-700 bg-surface-800/60 text-surface-400 hover:text-surface-200 hover:border-surface-600'}"
	>
		<svg class="h-3.5 w-3.5" fill={showBookmarked ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
		</svg>
		Bookmarks
	</button>

	<div class="h-5 w-px bg-surface-700/60 mx-0.5"></div>

	<button
			onclick={onMarkAllRead}
			disabled={markingAllRead || !hasUnread}
			class="flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-laya-secondary transition-colors
				border-surface-700 bg-surface-800/60
				{hasUnread
					? 'text-surface-400 hover:text-surface-200 hover:border-surface-600'
					: 'text-surface-600 cursor-not-allowed'}
				disabled:opacity-40"
		>
			<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
			</svg>
			Mark all read
		</button>

	<div class="h-5 w-px bg-surface-700/60 mx-0.5"></div>

	<button
		onclick={onOpenSummary}
		class="flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-laya-secondary transition-colors
			{summaryModalOpen
				? 'border-laya-orange/30 bg-laya-orange/10 text-laya-orange'
				: 'border-surface-700 bg-surface-800/60 text-surface-400 hover:text-surface-200 hover:border-surface-600'}"
	>
		<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
		</svg>
		Summary
	</button>
{/if}
