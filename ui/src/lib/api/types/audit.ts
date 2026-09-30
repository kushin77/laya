// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0


/** Audit log entry */
export interface AuditLogEntry {
	log_id: string;
	timestamp: string;
	event_id?: string;
	card_id?: string;
	step: string;
	model_used?: string;
	input_tokens: number;
	output_tokens: number;
	latency_ms: number;
	success: boolean;
	error?: string;
}

/** Paginated audit log response */
export interface AuditLogResponse {
	entries: AuditLogEntry[];
	total: number;
	limit: number;
	offset: number;
}

/** Dead event — failed permanently after exhausting retries */
export interface DeadEvent {
	event_id: string;
	timestamp: string;
	source_platform: string;
	subject_type: string;
	subject_title: string;
	subject_url?: string;
	actor_name?: string;
	processing_attempts: number;
	manual_retries: number;
	last_error?: string;
	created_at: string;
}

/** Paginated dead events response */
export interface DeadEventsResponse {
	events: DeadEvent[];
	total: number;
	limit: number;
	offset: number;
}

/** Response from retrying dead events */
export interface RetryDeadEventsResponse {
	retried: number;
}

/** Event dropped by a filter rule — informational, not a failure */
export interface FilteredEvent {
	event_id: string;
	timestamp: string;
	source_platform: string;
	subject_type: string;
	subject_title?: string;
	subject_url?: string;
	actor_name?: string;
	filter_rule?: string;
	created_at: string;
}

/** Paginated filtered events response */
export interface FilteredEventsResponse {
	events: FilteredEvent[];
	total: number;
	limit: number;
	offset: number;
}

/** JSON export envelope (audit log / filtered events) */
export interface ExportEnvelope<T> {
	kind: string;
	exported_at: string;
	days: number;
	since: string | null;
	count: number;
	entries?: T[];
	events?: T[];
}

/** Event counts grouped by processing_status */
export interface EventCountsResponse {
	counts: Record<string, number>;
	total: number;
}

/** One calendar entry on the selected day (timeline view's calendar rail). */
export interface DayMeeting {
	event_id: string;
	platform: string;
	title: string;
	url?: string | null;
	/** ISO-8601 with offset, or a bare 'YYYY-MM-DD' when all_day. */
	start: string | null;
	end: string | null;
	all_day: boolean;
	cancelled: boolean;
	location?: string | null;
	attendee_count: number;
}

/** Raw event volume + meetings for one day — the timeline view's second data source. */
export interface DayEventsResponse {
	date: string;
	total: number;
	bucket_minutes: number;
	/** Event count per source platform, e.g. { github: 214, gmail: 388 }. */
	platforms: Record<string, number>;
	/** Density buckets keyed by minutes from local midnight. */
	buckets: { start_minute: number; count: number }[];
	meetings: DayMeeting[];
}

/** Outstanding failure counts driving the Audit/Settings red dot */
export interface AuditFailureSummary {
	dead_events: number;
	ingestion_errors: number;
	has_failures: boolean;
}

/** Ingestion error captured from n8n workflow failures */
export interface IngestionError {
	error_id: string;
	workflow_id: string;
	source_id?: string;
	space_id?: string;
	platform?: string;
	workflow_name?: string;
	node_name?: string;
	error_name?: string;
	error_message?: string;
	error_http_code?: number;
	occurrence_count: number;
	first_occurred_at: string;
	last_occurred_at: string;
	acknowledged_at?: string;
	resolved_at?: string;
	cleared_at?: string;
}

/** Ingestion errors list response */
export interface IngestionErrorsResponse {
	errors: IngestionError[];
}

/** Response from clearing ingestion errors */
export interface ClearIngestionErrorsResponse {
	cleared: number;
}

