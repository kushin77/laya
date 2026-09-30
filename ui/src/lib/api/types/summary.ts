// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0


/** A single item in a daily summary section */
export interface SummaryItem {
	text: string;
	card_id: string;
	priority: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
	status: 'pending' | 'done' | 'dismissed' | 'archived';
	space_id?: string;
	space_name?: string;
	space_color?: string;
}

/** Structured daily summary */
export interface DaySummary {
	events_and_meetings: SummaryItem[];
	action_items: SummaryItem[];
	key_updates: SummaryItem[];
}

/** Per-space summary entry returned by GET /summary */
export interface SpaceSummary {
	space_id: string;
	space_name: string;
	space_color: string;
	summary: DaySummary | null;
	card_ids: string[];
	updated_at: string | null;
}

/** Response from GET /summary */
export interface DaySummaryResponse {
	date: string;
	space_summaries: SpaceSummary[];
}

