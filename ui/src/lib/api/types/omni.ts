// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0


import type { ActionCard } from './cards';

// ---------------------------------------------------------------------------
// Omni — rolling cross-platform summary
// ---------------------------------------------------------------------------

export interface OmniItem {
	text: string;
	source_cards: string[];
	platforms: string[];
	priority: string;
	pinned: boolean;
	bookmarked: boolean;
	space_id?: string;
	/** Fusion key for recent-section items. */
	entity_id?: string | null;
	/**
	 * ALL contributing entities. This is the join key that survives across
	 * versions — source_cards don't, because a resolving event mints a NEW
	 * card_id on the same entity_id. Required by the Omni prompt on every item.
	 */
	entity_ids?: string[];
	/** sha1(section|sorted(entity_ids)) — stamped by the engine on read and write. */
	item_key?: string;
	live?: OmniItemLive;
}

/**
 * Current state of an item's source cards, decorated by GET /omni at read time.
 * `priority` above is frozen at synthesis time, so a since-merged CRITICAL still
 * reads CRITICAL; anything that must reflect NOW reads this instead.
 */
export interface OmniItemLive {
	max_priority: string | null;
	all_resolved: boolean;
	resolved_count: number;
	missing_count: number;
	oldest_created_at: string | null;
	platform_counts: Record<string, number>;
}

export type OmniSectionType = 'attention' | 'recent' | 'period' | 'milestone';

// --- Change summaries (the "What changed" rail + funnel fold annotations) ---

export interface OmniChangeAdded {
	item_key: string;
	section: OmniSectionType;
	text: string;
	source_count: number;
	platforms: string[];
	/** Version of the write that recorded this entry. Stamped by GET
	 *  /omni/changes only — absent on the summary embedded in snapshot rows. */
	version?: number;
}

export interface OmniChangeFolded {
	item_key: string;
	from_section: OmniSectionType;
	/** null = dropped by compression rather than promoted to a later layer. */
	to_section: OmniSectionType | null;
	from_text: string;
	to_text: string | null;
	/** Version of the write that recorded this entry. Stamped by GET
	 *  /omni/changes only — absent on the summary embedded in snapshot rows. */
	version?: number;
}

export interface OmniChangeResolved {
	item_key: string;
	section: OmniSectionType;
	text: string;
	entity_ids: string[];
	resolved_at: string | null;
	/** Version of the write that recorded this entry. Stamped by GET
	 *  /omni/changes only — absent on the summary embedded in snapshot rows. */
	version?: number;
}

export interface OmniChangeSummary {
	added: OmniChangeAdded[];
	folded: OmniChangeFolded[];
	resolved: OmniChangeResolved[];
	counts: { added: number; folded: number; resolved: number };
}

export interface OmniChangesResponse extends OmniChangeSummary {
	space_id: string;
	base_version: number;
	base_generated_at: string | null;
	base_snapshot_type: string | null;
	to_version: number;
	versions_compared: number;
	/** Versions written before migration 072 — their changes can't be reported. */
	unsummarized_versions: number[];
}

// --- Instrument data ---

export interface OmniVolumeResponse {
	space_id: string;
	days: number;
	series: Array<{ date: string; count: number }>;
	total: number;
	today: number;
	today_date: string;
	platforms: Record<string, number>;
}

export interface OmniResynthesisStatus {
	space_id: string;
	in_progress: boolean;
	next_scheduled_at: string | null;
	interval_hours: number;
	event_threshold: number;
	events_since_last: number;
	last_synthesis_at: string | null;
}

// --- Item page ---

export type OmniBucket = 'awaiting_you' | 'changes_requested' | 'resolved' | 'other';

/** An ActionCard plus the outcome bucket the engine assigned it. */
export interface OmniEvidenceCard extends ActionCard {
	bucket: OmniBucket;
	platform: string;
}

export interface OmniLineageStep {
	version: number;
	generated_at: string | null;
	snapshot_type: string;
	section: OmniSectionType;
	source_count: number;
}

export interface OmniLineage {
	first_version: number;
	first_seen_at: string | null;
	versions_carried: number;
	rewrite_count: number;
	/** The walk hit its 30-version cap, so `versions_carried` is a lower bound. */
	truncated: boolean;
	section_history: OmniLineageStep[];
	next_fold: { to_section: OmniSectionType; expected_at: string | null } | null;
}

export interface OmniItemResponse {
	item: OmniItem;
	section: OmniSectionType;
	version: number;
	generated_at: string | null;
	snapshot_type: string | null;
	/**
	 * Version whose snapshot the item state came from. Equals `version` normally;
	 * older when the item is gone from the displayed snapshot (resolved or
	 * compressed away) and the engine served its last live state instead.
	 */
	found_version: number;
	found_generated_at: string | null;
	is_historical: boolean;
	cards: OmniEvidenceCard[];
	/** Source cards the engine could not load — surfaced, never silently dropped. */
	missing_card_ids: string[];
	lineage: OmniLineage;
	share_of_day: { cards: number; day_events: number; ratio: number };
}

export interface OmniSection {
	type: OmniSectionType;
	label: string | null;
	items: OmniItem[];
}

export interface OmniStats {
	events_processed: number;
	cards_acted_on: number;
	compression_ratio: number;
}

export interface OmniSnapshot {
	snapshot_id: string | null;
	space_id: string;
	version: number;
	generated_at: string | null;
	snapshot_type: string | null;
	sections: OmniSection[];
	stats: OmniStats;
	card_ids: string[];
	/** What this specific write changed. null for pre-migration-072 snapshots. */
	change_summary: OmniChangeSummary | null;
}

export interface OmniHistoryEntry {
	snapshot_id: string;
	version: number;
	generated_at: string;
	snapshot_type: string;
	events_processed: number;
}

export interface OmniHistoryResponse {
	space_id: string;
	snapshots: OmniHistoryEntry[];
}

export interface TimelineEntry {
	snapshot_id: string;
	version: number;
	generated_at: string;
	snapshot_type: string;
	events_processed: number;
}

export type TimelineTier = 'today' | 'this_week' | 'earlier';

export interface TimelineSegment {
	tier: TimelineTier;
	label: string;
	range_start: string | null;
	range_end: string | null;
	entries: TimelineEntry[];
}

export interface OmniTimelineResponse {
	space_id: string;
	segments: TimelineSegment[];
}

export interface OmniPin {
	pin_id: string;
	space_id: string;
	item_text: string;
	source_card_ids: string[];
	platforms: string[];
	pinned_at: string;
}

export interface OmniPinsResponse {
	space_id: string;
	pins: OmniPin[];
}

