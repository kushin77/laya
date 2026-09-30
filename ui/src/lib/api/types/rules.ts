// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0


/** Simple rule condition */
export interface SimpleCondition {
	field: string;
	operator: 'equals' | 'not_equals' | 'contains' | 'starts_with' | 'ends_with' | 'in';
	value: string | string[];
}

/** Compound "all" condition */
export interface AllCondition {
	all: RuleCondition[];
}

/** Compound "any" condition */
export interface AnyCondition {
	any: RuleCondition[];
}

/** Union of condition types */
export type RuleCondition = SimpleCondition | AllCondition | AnyCondition;

/** A single filter rule */
export interface Rule {
	name: string;
	enabled: boolean;
	condition: RuleCondition;
	action: 'drop' | 'allow';
}

/** rules.json structure */
export interface RulesConfig {
	rules: Rule[];
}

/** A user-defined classification rule (natural language) */
export interface ClassificationRule {
	id: number;
	space_id: string | null;
	field: string | null;
	rule_text: string;
	source: 'manual' | 'learned';
	active: boolean;
	created_at: string;
	updated_at: string;
}

/** A context-grouping rule (learned from link/unlink actions, or manual). */
export interface ContextRule {
	id: number;
	space_id: string | null;
	rule_text: string;
	source: 'manual' | 'learned';
	active: boolean;
	created_at: string;
	updated_at: string;
}

export interface ContextRuleListResponse {
	rules: ContextRule[];
	total: number;
	limit: number;
	offset: number;
}

/** Processing rule condition types (extended operators) */
export type ProcessingRuleOperator =
	| 'equals' | 'not_equals' | 'contains' | 'not_contains'
	| 'starts_with' | 'ends_with' | 'in' | 'not_in'
	| 'matches' | 'gt' | 'gte' | 'lt' | 'lte'
	| 'exists' | 'not_exists';

export interface ProcessingSimpleCondition {
	field: string;
	operator: ProcessingRuleOperator;
	value?: string | string[] | number | boolean | null;
}

export interface ProcessingAllCondition {
	all: ProcessingCondition[];
}

export interface ProcessingAnyCondition {
	any: ProcessingCondition[];
}

export interface ProcessingNotCondition {
	not: ProcessingCondition;
}

export type ProcessingCondition =
	| ProcessingSimpleCondition
	| ProcessingAllCondition
	| ProcessingAnyCondition
	| ProcessingNotCondition;

/** Processing rule action types */
export type ProcessingRuleAction =
	| { type: 'set_status'; status: 'dismissed' | 'archived' | 'done'; reason?: string }
	| { type: 'set_priority'; priority: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' }
	| { type: 'bookmark' }
	| { type: 'run_entity_agent'; prompt_template?: string }
	| { type: 'execute_egress'; platform: string; action_type: string; payload_template: Record<string, string>; connection_id?: string }
	| { type: 'send_notification'; title_template: string; body_template: string }
	| { type: 'add_tag'; tag_name: string; create_if_missing?: boolean };

/** A processing rule (automated event→action) */
export interface ProcessingRule {
	id: number;
	name: string;
	description: string | null;
	space_id: string | null;
	enabled: boolean;
	position: number;
	condition: ProcessingCondition;
	actions: ProcessingRuleAction[];
	rate_limit: number;
	cooldown_secs: number;
	max_daily: number;
	last_fired_at: string | null;
	fire_count: number;
	error_count: number;
	last_error: string | null;
	created_at: string;
	updated_at: string;
}

/** Processing rule firing history entry */
export interface ProcessingRuleFiring {
	id: number;
	card_id: string;
	entity_id: string | null;
	event_id: string | null;
	fired_at: string;
	actions: ProcessingRuleAction[];
	results: Array<{ success: boolean; error?: string }>;
	error: string | null;
}

/** A single result object inside a firing (one per executed action). */
export interface ProcessingRuleFiringResult {
	success: boolean;
	skipped?: boolean;
	reason?: string;
	error?: string;
	[key: string]: unknown;
}

/** Enriched cross-rule firing-log entry (Settings → Rules → Activity). */
export interface ProcessingRuleFiringEntry {
	id: number;
	rule_id: number;
	rule_name: string | null;
	fired_at: string;
	card_id: string;
	card_header: string | null;
	status: string | null;
	priority: string | null;
	entity_id: string | null;
	event_id: string | null;
	platform: string | null;
	outcome: 'success' | 'error' | 'skipped';
	action_types: string[];
	results: ProcessingRuleFiringResult[];
	error: string | null;
	skip_reason: string | null;
}

export interface ProcessingRuleFiringResponse {
	entries: ProcessingRuleFiringEntry[];
	total: number;
	limit: number;
	offset: number;
}

