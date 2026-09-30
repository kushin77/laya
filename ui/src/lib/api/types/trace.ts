// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0


import type { ActionCard } from './cards';

// Trace (semantic cross-platform entity search)
export interface TraceEntity {
	entity_id: string;
	title: string;
	url?: string;
	platform: string;
}

export interface TraceChapter {
	label: string;
	timestamp: string;
	card_ids: string[];
}

export interface TraceStatusSummary {
	current_state: string;
	platforms_involved: string[];
	total_cards: number;
	date_range: { from: string; to: string };
	pending_actions: number;
}

export interface TraceCluster {
	cluster_id: string;
	primary_entity: TraceEntity;
	linked_entities: TraceEntity[];
	narrative?: string;
	chapters: TraceChapter[];
	timeline: ActionCard[];
	status_summary: TraceStatusSummary;
}

export interface TraceSearchMetadata {
	semantic_hits: number;
	fuzzy_hits: number;
	entity_hits: number;
	expansion_cards: number;
	elapsed_ms: number;
	fuzzy_search: boolean;
	enable_semantic?: boolean;
	enable_text?: boolean;
	enable_llm_filter?: boolean;
}

export interface TraceResponse {
	trace_id: string;
	query: string;
	clusters: TraceCluster[];
	search_metadata: TraceSearchMetadata;
	created_at: string;
	summary?: string | null;
}

export interface TraceListItem {
	trace_id: string;
	query: string;
	created_at: string;
	total_cards: number;
	platforms: string[];
	fuzzy_search: boolean;
	enable_semantic: boolean;
	enable_text: boolean;
	enable_llm_filter: boolean;
}

