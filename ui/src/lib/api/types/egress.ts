// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0


// ---------------------------------------------------------------------------
// Egress types
// ---------------------------------------------------------------------------

/** Request to execute an egress action */
export interface EgressExecuteRequest {
	platform: string;
	action_type: string;
	payload: Record<string, unknown>;
	connection_id?: string;
	source_card_id?: string;
	source_event_id?: string;
	space_id?: string;
}

/** Request for AI-assisted draft generation */
export interface EgressAiAssistRequest {
	platform: string;
	action_type: string;
	context: Record<string, unknown>;
}

/** Response from AI-assisted draft generation */
export interface EgressAiAssistResponse {
	draft: Record<string, string>;
}

/** Response from egress execution */
export interface EgressExecuteResponse {
	status: string;
	result_url?: string;
	result_data?: Record<string, unknown>;
}

/** Response from egress preview */
export interface EgressPreviewResponse {
	platform: string;
	action_type: string;
	summary: string;
	details: Record<string, unknown>;
	warnings: string[];
	estimated_impact: string;
}

/** A platform capability */
export interface EgressCapability {
	action_type: string;
	label: string;
	requires_fields: string[];
	optional_fields: string[];
	description: string;
	confirmation_required: boolean;
}

/** Response from capabilities endpoint */
export interface EgressCapabilitiesResponse {
	platform: string;
	capabilities: EgressCapability[];
}

export interface ComposeFieldAutocomplete {
	scope: 'all' | 'platform';
	sources: string[];
}

export interface ComposeField {
	name: string;
	required: boolean;
	type: 'text' | 'email' | 'textarea' | 'select' | 'datetime-local';
	label: string;
	placeholder: string;
	options?: string[];
	autocomplete?: ComposeFieldAutocomplete;
}

export interface ComposeAction {
	action_type: string;
	label: string;
	fields: ComposeField[];
}

export interface ComposePlatform {
	id: string;
	label: string;
	icon: string;
	actions: ComposeAction[];
}

export interface ComposePlatformsResponse {
	platforms: ComposePlatform[];
}

export interface CardEgressAction {
	action_type: string;
	label: string;
	impact: 'low' | 'medium' | 'high';
}

export interface CardEgressContext {
	platform: string;
	actions: CardEgressAction[];
	prefill: Record<string, unknown>;
	event_id: string | null;
	connected: boolean;
	connection_id: string | null;
}

/** An egress connection */
export interface EgressConnection {
	connection_id: string;
	platform: string;
	name: string;
	status: 'connected' | 'error' | 'expired';
	capabilities: string[];
	space_id?: string;
	error_message?: string;
	last_validated_at?: string;
	created_at: string;
}

/** Response from egress connections list */
export interface EgressConnectionsResponse {
	connections: EgressConnection[];
}

/** Request to create an egress connection */
export interface EgressConnectRequest {
	platform: string;
	name?: string;
	credentials: Record<string, string | boolean>;
	space_id?: string;
}

/** Response from creating an egress connection */
export interface EgressConnectResponse {
	status: string;
	connection_id?: string;
	capabilities: string[];
}

/** WebSocket open_compose event data */
export interface OpenComposeEvent {
	type: 'open_compose';
	platform: string;
	action_type: 'reply' | 'compose' | 'comment' | 'forward';
	prefill: Record<string, unknown>;
	source_card_id?: string;
}

