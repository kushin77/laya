// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0


import type { GroupSummary } from './cards';

/** Embedding backend info from health endpoint */
export interface EmbeddingInfo {
	backend: string;
	model: string;
	dimensions: string;
	status: string; // "active" | "fallback" | "not_initialized"
}

/** Health check response from GET /health */
export interface HealthResponse {
	engine: string;
	sqlite: string;
	chromadb?: string; // "healthy" | "starting" | "unhealthy"
	n8n: string;
	uptime_seconds: number;
	embeddings?: EmbeddingInfo;
}

/** WebSocket message from the engine */
export interface WsMessage {
	type:
		| 'card_created' | 'card_updated' | 'card_deleted'
		| 'action_payload_updated'
		| 'group_carried_forward' | 'group_summary_updated'
		| 'context_group_merged' | 'context_group_unlinked'
		| 'summary_updated'
		| 'budget_status'
		| 'agent_budget_status'
		| 'omni_updated'
		| 'settings_changed'
		| 'rules_changed' | 'tags_changed'
		| 'open_compose'
		| 'processing_rule_auto_disabled'
		| 'push_notification'
		| 'audit_failure'
		| 'connection_status'
		| (string & {});
	event_id?: string;
	card_id?: string;
	entity_id?: string;
	session_id?: string;
	summary?: GroupSummary;
	payload: Record<string, unknown>;
}

/** Team member from team.json */
export interface TeamMember {
	name: string;
	email: string;
	role: 'self' | 'manager' | 'teammate' | 'external' | 'bot';
	notes: string;
	aliases: string[];
	accounts: string[];
}

/** team.json structure */
export interface TeamConfig {
	members: TeamMember[];
}

