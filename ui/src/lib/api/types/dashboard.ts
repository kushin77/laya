// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0


/** Dashboard stat counts */
export interface DashboardStats {
	events_processed: number;
	events_filtered: number;
	cards_generated: number;
	cards_pending: number;
	cards_approved: number;
	cards_dismissed: number;
	cards_edited: number;
	actions_executed: number;
	actions_completed: number;
	actions_failed: number;
}

export interface TimeSavedEstimate {
	total_minutes: number;
	by_action_type: Record<string, number>;
}

export interface LLMCostEstimate {
	total_cost_usd: number;
	by_model: Record<string, number>;
	by_feature: Record<string, number>;
	by_step: Record<string, number>;
	total_input_tokens: number;
	total_output_tokens: number;
}

export interface SourceBreakdown {
	source: string;
	count: number;
}

export interface PersonaApprovalRate {
	persona: string;
	total: number;
	approved: number;
	dismissed: number;
	rate: number;
}

export interface ResponseTimeStats {
	avg_ms: number;
	p50_ms: number;
	p95_ms: number;
}

export interface DashboardResponse {
	stats: DashboardStats;
	time_saved: TimeSavedEstimate;
	llm_costs: LLMCostEstimate;
	events_by_source: SourceBreakdown[];
	approval_by_persona: PersonaApprovalRate[];
	response_time: ResponseTimeStats;
	period_days: number;
}

/** One minute bucket of throughput + wait-time data */
export interface ThroughputBucket {
	minute: string;
	ingested: number;
	processed: number;
	failed: number;
	avg_wait_s: number;
	p95_wait_s: number;
}

/** Response from GET /dashboard/throughput */
export interface ThroughputResponse {
	buckets: ThroughputBucket[];
	window_minutes: number;
}

