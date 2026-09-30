<!-- Copyright 2026 Aayush Chawla -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
	List/card view-switch branching extracted from routes/feed/+page.svelte
	(issue #28). This component owns ONLY the pure rendering branch that picks
	between list-view rows/groups and card-view grid/groups (including the
	sort-sections variants of each), plus the trailing "load more" control.

	It intentionally does NOT own:
	  - the timeline view (TimelineView is already a separate component)
	  - loading/error/empty states (still handled by +page.svelte, which decides
	    whether this component even mounts)
	  - FLIP animation orchestration, column-count math, or any $effect/state
	    tied to containerEl — all of that stays in +page.svelte since it reaches
	    across the whole layout (detail panel, recent drawer, resize observer)
	    and is too tangled to safely split out in this pass.

	Every prop below is either a plain value/derived snapshot from +page.svelte
	or a callback that mutates +page.svelte's own state — no new reactive state
	is introduced here beyond what ListRow/ListGroup/ActionCard/CardGroup already
	manage internally.
-->
<script lang="ts">
	import type { CardGroup, ActionCard } from '$lib/api/types';
	import ActionCardComponent from './ActionCard.svelte';
	import CardGroupComponent from './CardGroup.svelte';
	import ListRow from './ListRow.svelte';
	import ListGroupComponent from './ListGroup.svelte';

	let {
		viewMode,
		filteredGroups,
		sections,
		columns,
		toColumns,
		collapsedSections,
		ontogglesection,
		exitingCardIds,
		selectedCardId = '',
		selectedEntityId = '',
		scrollToCardId = null,
		bulkSelectedIds,
		hasSelection = false,
		lastViewedCardId = '',
		lastViewedEntityId = '',
		detailPanelOpen = false,
		onselect,
		onselectgroup,
		ondelete,
		onlinkgroup,
		onlinkcard,
		onbulktoggle,
		onbulktogglegroup,
		hasMoreGroups = false,
		loadingMoreGroups = false,
		remainingCount = 0,
		onloadmore
	}: {
		viewMode: 'list' | 'card';
		filteredGroups: CardGroup[];
		sections: [string, CardGroup[]][] | null;
		columns: CardGroup[][];
		toColumns: (items: CardGroup[]) => CardGroup[][];
		collapsedSections: Set<string>;
		ontogglesection: (key: string) => void;
		exitingCardIds: Set<string>;
		selectedCardId?: string;
		selectedEntityId?: string;
		scrollToCardId?: string | null;
		bulkSelectedIds?: Set<string>;
		hasSelection?: boolean;
		lastViewedCardId?: string;
		lastViewedEntityId?: string;
		detailPanelOpen?: boolean;
		onselect: (card: ActionCard) => void;
		onselectgroup: (group: CardGroup) => void;
		ondelete: (cardId: string) => void;
		onlinkgroup: (group: CardGroup) => void;
		onlinkcard: (card: ActionCard) => void;
		onbulktoggle: (cardId: string, event: MouseEvent) => void;
		onbulktogglegroup: (cardIds: string[], selected: boolean) => void;
		hasMoreGroups?: boolean;
		loadingMoreGroups?: boolean;
		remainingCount?: number;
		onloadmore: () => void;
	} = $props();
</script>

{#if viewMode === 'list'}
	{#if sections}
		<!-- Sorted list view with section separators -->
		{#each sections as [sectionTitle, sectionGroups], si}
			{@const isCollapsed = collapsedSections.has(sectionTitle)}
			<div
				class="flex cursor-pointer items-center gap-3 pr-3 {si > 0 ? 'mt-5' : ''} mb-2 select-none"
				role="button"
				tabindex="0"
				onclick={() => ontogglesection(sectionTitle)}
				onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); ontogglesection(sectionTitle); } }}
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
							<ListRow card={group.cards[0]} onselect={onselect} ondelete={ondelete} selectedCardId={selectedCardId} bulkSelected={bulkSelectedIds?.has(group.cards[0].card_id) ?? false} onbulktoggle={onbulktoggle} hasSelection={hasSelection} lastViewedCardId={lastViewedCardId} />
						{:else}
							<ListGroupComponent {group} onselect={onselect} onselectgroup={onselectgroup} ondelete={ondelete} onlink={onlinkgroup} selectedCardId={selectedCardId} {selectedEntityId} {scrollToCardId} bulkSelectedIds={bulkSelectedIds} onbulktoggle={onbulktoggle} onbulktogglegroup={onbulktogglegroup} hasSelection={hasSelection} lastViewedCardId={lastViewedCardId} lastViewedEntityId={lastViewedEntityId} />
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
					<ListRow card={group.cards[0]} onselect={onselect} ondelete={ondelete} selectedCardId={selectedCardId} bulkSelected={bulkSelectedIds?.has(group.cards[0].card_id) ?? false} onbulktoggle={onbulktoggle} hasSelection={hasSelection} lastViewedCardId={lastViewedCardId} />
				{:else}
					<ListGroupComponent {group} onselect={onselect} onselectgroup={onselectgroup} ondelete={ondelete} onlink={onlinkgroup} selectedCardId={selectedCardId} {selectedEntityId} {scrollToCardId} bulkSelectedIds={bulkSelectedIds} onbulktoggle={onbulktoggle} onbulktogglegroup={onbulktogglegroup} hasSelection={hasSelection} lastViewedCardId={lastViewedCardId} lastViewedEntityId={lastViewedEntityId} />
				{/if}
				</div>
			{/each}
		</div>
	{/if}
{:else if sections}
	<!-- Sorted view with section separators (card view) -->
	{#each sections as [sectionTitle, sectionGroups], si}
		{@const isCollapsed = collapsedSections.has(sectionTitle)}
		<div
			class="flex cursor-pointer items-center gap-3 pr-3 {si > 0 ? 'mt-5' : ''} mb-3 select-none"
			role="button"
			tabindex="0"
			onclick={() => ontogglesection(sectionTitle)}
			onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); ontogglesection(sectionTitle); } }}
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
								<ActionCardComponent card={group.cards[0]} onselect={onselect} ondelete={ondelete} onlink={onlinkcard} selectedCardId={selectedCardId} hasSelection={hasSelection} lastViewedCardId={lastViewedCardId} />
							{:else}
								<CardGroupComponent {group} onselect={onselect} onselectgroup={onselectgroup} ondelete={ondelete} onlink={onlinkgroup} selectedCardId={selectedCardId} {selectedEntityId} hasSelection={hasSelection} lastViewedCardId={lastViewedCardId} lastViewedEntityId={lastViewedEntityId} {scrollToCardId} {detailPanelOpen} />
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
							<ActionCardComponent card={group.cards[0]} onselect={onselect} ondelete={ondelete} onlink={onlinkcard} selectedCardId={selectedCardId} hasSelection={hasSelection} lastViewedCardId={lastViewedCardId} />
						{:else}
							<CardGroupComponent {group} onselect={onselect} onselectgroup={onselectgroup} ondelete={ondelete} onlink={onlinkgroup} selectedCardId={selectedCardId} {selectedEntityId} hasSelection={hasSelection} lastViewedCardId={lastViewedCardId} lastViewedEntityId={lastViewedEntityId} {scrollToCardId} {detailPanelOpen} />
						{/if}
					</div>
				{/each}
			</div>
		{/each}
	</div>
{/if}
{#if hasMoreGroups}
	<!-- Group pagination: load the next page of groups (P4-9). Sits below
	     both list and card views; the timeline carries its own control in
	     the control strip (it has no scroll room below the lanes). -->
	<div class="flex w-full justify-center py-6">
		<button
			class="rounded-lg border border-surface-600 bg-surface-800 px-6 py-2.5 text-laya-base font-medium text-surface-200 transition-colors hover:border-laya-orange/40 hover:bg-surface-700 disabled:cursor-not-allowed disabled:opacity-60"
			onclick={onloadmore}
			disabled={loadingMoreGroups}
		>
			{loadingMoreGroups ? 'Loading…' : `Load more (${remainingCount} more)`}
		</button>
	</div>
{/if}
