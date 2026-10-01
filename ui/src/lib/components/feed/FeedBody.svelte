<!-- Copyright 2026 Aayush Chawla -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
	// View-switch branching: timeline / list / card rendering, loading/error/empty
	// states, and the "load more" footer. Rendered INSIDE the page's `containerEl`
	// div (bind:this stays in the parent — it's the FLIP/ResizeObserver target and
	// its [data-entity-id] children must stay in the same DOM subtree, which they
	// do: this component only replaces the div's children, not the div itself).
	import type { ActionCard, CardGroup, DayEventsResponse } from '$lib/api/types';
	import CardGroupComponent from './CardGroup.svelte';
	import ActionCardComponent from './ActionCard.svelte';
	import ListRow from './ListRow.svelte';
	import ListGroupComponent from './ListGroup.svelte';
	import TimelineView from './timeline/TimelineView.svelte';

	let {
		viewMode,
		groups,
		filteredGroups,
		dayEvents,
		loading,
		error,
		feedDate,
		feedPrevDate,
		isToday,
		selectedCard,
		selectedEntityId,
		hasAnySelection,
		hasMoreGroups,
		loadingMoreGroups,
		totalGroups,
		searchActive,
		searchQuery,
		showRelated,
		relatedSourceHeader,
		showBookmarked,
		sections,
		collapsedSections,
		toColumns,
		columns,
		exitingCardIds,
		scrollToCardId,
		detailPanelOpen,
		bulkSelectedIds,
		lastViewedCardId,
		lastViewedEntityId,
		formatDateLabel,
		onSelectCard,
		onSelectGroup,
		onDelete,
		onLinkCard,
		onLinkGroup,
		onBulkToggle,
		onBulkToggleGroup,
		onToggleSection,
		onLoadMore,
		onClearRelated,
		onClearSearch,
		onDismissError,
		onGotoPrevDate
	}: {
		viewMode: 'card' | 'list' | 'timeline';
		groups: CardGroup[];
		filteredGroups: CardGroup[];
		dayEvents: DayEventsResponse | null;
		loading: boolean;
		error: string | null;
		feedDate: string;
		feedPrevDate: string | null;
		isToday: boolean;
		selectedCard: ActionCard | null;
		selectedEntityId: string;
		hasAnySelection: boolean;
		hasMoreGroups: boolean;
		loadingMoreGroups: boolean;
		totalGroups: number;
		searchActive: boolean;
		searchQuery: string;
		showRelated: boolean;
		relatedSourceHeader: string;
		showBookmarked: boolean;
		sections: [string, CardGroup[]][] | null;
		collapsedSections: Set<string>;
		toColumns: (items: CardGroup[]) => CardGroup[][];
		columns: CardGroup[][];
		exitingCardIds: Set<string>;
		scrollToCardId: string | null;
		detailPanelOpen: boolean;
		bulkSelectedIds: Set<string>;
		lastViewedCardId: string | null;
		lastViewedEntityId: string | null;
		formatDateLabel: (dateStr: string) => string;
		onSelectCard: (card: ActionCard) => void;
		onSelectGroup: (group: CardGroup) => void;
		onDelete: (cardId: string) => void;
		onLinkCard: (card: ActionCard) => void;
		onLinkGroup: (group: CardGroup) => void;
		onBulkToggle: (cardId: string, event: MouseEvent) => void;
		onBulkToggleGroup: (cardIds: string[], selected: boolean) => void;
		onToggleSection: (key: string) => void;
		onLoadMore: () => void;
		onClearRelated: () => void;
		onClearSearch: () => void;
		onDismissError: () => void;
		onGotoPrevDate: () => void;
	} = $props();
</script>

{#if showRelated}
	<div class="mb-3 flex items-center gap-2 rounded-lg border border-laya-orange/30 bg-laya-orange/10 px-3 py-2">
		<svg class="h-4 w-4 shrink-0 text-laya-orange" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
		</svg>
		<span class="min-w-0 flex-1 truncate text-laya-secondary text-laya-orange">
			Related to "<span class="font-medium">{relatedSourceHeader}</span>"
		</span>
		<button
			onclick={onClearRelated}
			class="shrink-0 rounded p-0.5 text-laya-orange/70 transition-colors hover:bg-laya-orange/20 hover:text-laya-orange"
			aria-label="Clear related cards filter"
		>
			<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
			</svg>
		</button>
	</div>
{/if}
{#if viewMode === 'timeline'}
	<!-- ── TIMELINE VIEW ── -->
	{#if error}
		<div class="m-3 flex items-start gap-2 rounded-lg border border-red-800 bg-red-900/30 px-4 py-3 text-laya-base text-red-300">
			<span class="flex-1">{error}</span>
			<button class="shrink-0 text-red-400 hover:text-red-200" onclick={onDismissError} aria-label="Dismiss error">
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
			</button>
		</div>
	{/if}
	<TimelineView
		groups={filteredGroups}
		{dayEvents}
		{loading}
		date={feedDate}
		{isToday}
		selectedCardId={selectedCard?.card_id ?? ''}
		{selectedEntityId}
		{hasAnySelection}
		hasMore={hasMoreGroups}
		loadingMore={loadingMoreGroups}
		remaining={Math.max(0, totalGroups - groups.length)}
		onloadmore={onLoadMore}
		onselectcard={onSelectCard}
		onselectgroup={onSelectGroup}
		emptyLabel={searchActive
			? `No cards match "${searchQuery}"`
			: `No cards for ${formatDateLabel(feedDate)}`}
	/>
{:else if loading && groups.length === 0}
	<div class="py-12 text-center text-surface-400">Loading cards...</div>
{:else if error}
	<div class="flex items-start gap-2 rounded-lg border border-red-800 bg-red-900/30 px-4 py-3 text-laya-base text-red-300">
		<span class="flex-1">{error}</span>
		<button class="shrink-0 text-red-400 hover:text-red-200" onclick={onDismissError} aria-label="Dismiss error">
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
		</button>
	</div>
{:else if groups.length === 0}
	<div class="py-12 text-center text-surface-500">
		<p class="text-laya-heading">{showRelated ? 'No related cards found' : showBookmarked ? 'No bookmarked cards' : `No cards for ${formatDateLabel(feedDate)}`}</p>
		<p class="mt-1 text-laya-base">
			{#if showRelated}
				<button class="text-laya-orange hover:underline" onclick={onClearRelated}>Back to feed</button>
			{:else if showBookmarked}
				Bookmark cards to save them for later
			{:else if feedPrevDate}
				<button class="text-laya-orange hover:underline" onclick={onGotoPrevDate}>
					View {formatDateLabel(feedPrevDate)}
				</button>
			{:else}
				Cards will appear here as events are processed
			{/if}
		</p>

	</div>
{:else if filteredGroups.length === 0 && searchActive}
	<div class="py-12 text-center text-surface-500">
		<svg class="mx-auto mb-2 h-8 w-8 text-surface-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
		</svg>
		<p class="text-laya-base">No cards match "<span class="text-surface-300">{searchQuery}</span>"</p>
		<button class="mt-2 text-laya-secondary text-laya-orange hover:underline" onclick={onClearSearch}>Clear search</button>
	</div>
<!-- ── LIST VIEW ── -->
{:else if viewMode === 'list'}
	{#if sections}
		<!-- Sorted list view with section separators -->
		{#each sections as [sectionTitle, sectionGroups], si}
			{@const isCollapsed = collapsedSections.has(sectionTitle)}
			<div
				class="flex cursor-pointer items-center gap-3 pr-3 {si > 0 ? 'mt-5' : ''} mb-2 select-none"
				role="button"
				tabindex="0"
				onclick={() => onToggleSection(sectionTitle)}
				onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggleSection(sectionTitle); } }}
			>
				<svg class="h-3.5 w-3.5 shrink-0 text-surface-500 transition-transform {isCollapsed ? '-rotate-90' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
				</svg>
				<span class="text-laya-secondary font-semibold uppercase tracking-wider text-surface-400">{sectionTitle}</span>
				<div class="flex-1 border-t border-surface-700"></div>
				<span class="text-laya-micro text-surface-500">{sectionGroups.reduce((s, g) => s + g.card_count, 0)}</span>
			</div>
			{#if !isCollapsed}
				<div class="flex flex-col gap-1 mb-2">
					{#each sectionGroups as group (group.entity_id)}
						<div data-entity-id={group.entity_id} data-list-row>
						{#if group.card_count === 1}
							<ListRow card={group.cards[0]} onselect={onSelectCard} ondelete={onDelete} selectedCardId={selectedCard?.card_id ?? ''} bulkSelected={bulkSelectedIds.has(group.cards[0].card_id)} onbulktoggle={onBulkToggle} hasSelection={hasAnySelection} lastViewedCardId={lastViewedCardId ?? ''} />
						{:else}
							<ListGroupComponent {group} onselect={onSelectCard} onselectgroup={onSelectGroup} ondelete={onDelete} onlink={onLinkGroup} selectedCardId={selectedCard?.card_id ?? ''} {selectedEntityId} {scrollToCardId} {bulkSelectedIds} onbulktoggle={onBulkToggle} onbulktogglegroup={onBulkToggleGroup} hasSelection={hasAnySelection} lastViewedCardId={lastViewedCardId ?? ''} lastViewedEntityId={lastViewedEntityId ?? ''} />
						{/if}
						</div>
					{/each}
				</div>
			{/if}
		{/each}
	{:else}
		<!-- Default list view -->
		<div class="flex flex-col gap-1">
			{#each filteredGroups as group (group.entity_id)}
				<div data-entity-id={group.entity_id} data-list-row>
				{#if group.card_count === 1}
					<ListRow card={group.cards[0]} onselect={onSelectCard} ondelete={onDelete} selectedCardId={selectedCard?.card_id ?? ''} bulkSelected={bulkSelectedIds.has(group.cards[0].card_id)} onbulktoggle={onBulkToggle} hasSelection={hasAnySelection} lastViewedCardId={lastViewedCardId ?? ''} />
				{:else}
					<ListGroupComponent {group} onselect={onSelectCard} onselectgroup={onSelectGroup} ondelete={onDelete} onlink={onLinkGroup} selectedCardId={selectedCard?.card_id ?? ''} {selectedEntityId} {scrollToCardId} {bulkSelectedIds} onbulktoggle={onBulkToggle} onbulktogglegroup={onBulkToggleGroup} hasSelection={hasAnySelection} lastViewedCardId={lastViewedCardId ?? ''} lastViewedEntityId={lastViewedEntityId ?? ''} />
				{/if}
				</div>
			{/each}
		</div>
	{/if}
<!-- ── CARD VIEW ── -->
{:else if sections}
	<!-- Sorted view with section separators -->
	{#each sections as [sectionTitle, sectionGroups], si}
		{@const isCollapsed = collapsedSections.has(sectionTitle)}
		<div
			class="flex cursor-pointer items-center gap-3 pr-3 {si > 0 ? 'mt-5' : ''} mb-3 select-none"
			role="button"
			tabindex="0"
			onclick={() => onToggleSection(sectionTitle)}
			onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggleSection(sectionTitle); } }}
		>
			<svg class="h-3.5 w-3.5 shrink-0 text-surface-500 transition-transform {isCollapsed ? '-rotate-90' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
			</svg>
			<span class="text-laya-secondary font-semibold uppercase tracking-wider text-surface-400">{sectionTitle}</span>
			<div class="flex-1 border-t border-surface-700"></div>
			<span class="text-laya-micro text-surface-500">{sectionGroups.reduce((s, g) => s + g.card_count, 0)}</span>
		</div>
		{#if !isCollapsed}
			<div class="flex flex-wrap gap-4">
				{#each toColumns(sectionGroups) as col}
					<div class="flex w-[320px] flex-col gap-4">
						{#each col as group (group.entity_id)}
						{@const isGroupExiting = group.cards.every((c) => exitingCardIds.has(c.card_id))}
						<div data-entity-id={group.entity_id} class="card-exit-wrap {isGroupExiting ? 'card-exiting' : ''}">
							{#if group.card_count === 1}
								<ActionCardComponent card={group.cards[0]} onselect={onSelectCard} ondelete={onDelete} onlink={onLinkCard} selectedCardId={selectedCard?.card_id ?? ''} hasSelection={hasAnySelection} lastViewedCardId={lastViewedCardId ?? ''} />
							{:else}
								<CardGroupComponent {group} onselect={onSelectCard} onselectgroup={onSelectGroup} ondelete={onDelete} onlink={onLinkGroup} selectedCardId={selectedCard?.card_id ?? ''} {selectedEntityId} hasSelection={hasAnySelection} lastViewedCardId={lastViewedCardId ?? ''} lastViewedEntityId={lastViewedEntityId ?? ''} {scrollToCardId} {detailPanelOpen} />
							{/if}
						</div>
					{/each}
					</div>
				{/each}
			</div>
		{/if}
	{/each}
{:else}
	<!-- Default column layout (newest / oldest) -->
	<div class="flex flex-wrap gap-4">
		{#each columns as col}
			<div class="flex w-[320px] flex-col gap-4">
				{#each col as group (group.entity_id)}
					<div data-entity-id={group.entity_id}>
						{#if group.card_count === 1}
							<ActionCardComponent card={group.cards[0]} onselect={onSelectCard} ondelete={onDelete} onlink={onLinkCard} selectedCardId={selectedCard?.card_id ?? ''} hasSelection={hasAnySelection} lastViewedCardId={lastViewedCardId ?? ''} />
						{:else}
							<CardGroupComponent {group} onselect={onSelectCard} onselectgroup={onSelectGroup} ondelete={onDelete} onlink={onLinkGroup} selectedCardId={selectedCard?.card_id ?? ''} {selectedEntityId} hasSelection={hasAnySelection} lastViewedCardId={lastViewedCardId ?? ''} lastViewedEntityId={lastViewedEntityId ?? ''} {scrollToCardId} {detailPanelOpen} />
						{/if}
					</div>
				{/each}
			</div>
		{/each}
	</div>
{/if}
{#if hasMoreGroups && viewMode !== 'timeline'}
	<!-- Group pagination: load the next page of groups (P4-9). Sits below
	     both list and card views; the timeline carries its own control in
	     the control strip (it has no scroll room below the lanes). -->
	<div class="flex w-full justify-center py-6">
		<button
			class="rounded-lg border border-surface-600 bg-surface-800 px-6 py-2.5 text-laya-base font-medium text-surface-200 transition-colors hover:border-laya-orange/40 hover:bg-surface-700 disabled:cursor-not-allowed disabled:opacity-60"
			onclick={onLoadMore}
			disabled={loadingMoreGroups}
		>
			{loadingMoreGroups ? 'Loading…' : `Load more (${totalGroups - groups.length} more)`}
		</button>
	</div>
{/if}
