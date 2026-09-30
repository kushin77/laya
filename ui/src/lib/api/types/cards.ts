// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0


/** Request to update a card's classification */
export interface UpdateClassificationRequest {
	priority?: string;
	persona?: string;
	rule_text?: string;
}

/** A configured repository */
export interface Repo {
	name: string;
	path: string;
	platform: string;
	remote_id: string;
	/** Git remote host; "" or bitbucket.org/github.com ⇒ cloud, else self-hosted/on-prem */
	host?: string;
}

/** repos.json structure */
export interface ReposConfig {
	repos: Repo[];
}

/** Workspace session */
export interface WorkspaceSession {
	session_id: string;
	agent_type: string;
	status: string;
	repo_path?: string;
	add_dirs?: string[];
	started_at?: string;
	updated_at?: string;
	completed_at?: string;
	findings?: Record<string, unknown>;
	error_message?: string;
	session_type?: 'code' | 'research';
	permission_mode?: string;
}

/** Workspace event */
export interface WorkspaceEvent {
	event_id: string;
	timestamp: string;
	event_type: string;
	actor: string;
	content: Record<string, unknown>;
	requires_input: boolean;
	agent_message_id?: string | null;
}

/** Workspace response from GET /cards/:card_id/workspace */
export interface WorkspaceResponse {
	card_id: string;
	session: WorkspaceSession | null;
	events: WorkspaceEvent[];
	context: Record<string, unknown>;
}

/** Staged output attached to an action card */
export interface StagedOutput {
	type: 'draft_reply' | 'code_fix' | 'briefing' | 'summary' | 'agent_result' | 'agent_plan';
	content: string;
}

/** A suggested action the user can approve */
export interface SuggestedAction {
	action_id: string;
	label: string;
	action_type: string;
	target_platform: string;
	payload: Record<string, unknown>;
}

/** Full action card from the engine */
/** A tag definition */
export interface Tag {
	tag_id: number;
	name: string;
	color?: string;
	is_system: boolean;
	created_at?: string;
}

/** A tag applied to a card, entity group, or context group */
export interface TagAssignment {
	tag_id: number;
	tag_name: string;
	color?: string;
	is_system: boolean;
	assigned_by: string;
}

export interface ActionCard {
	card_id: string;
	event_id: string;
	created_at?: string;
	priority: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
	persona: 'ENGINEER' | 'COMMS' | 'OPS' | 'SALES' | 'HR' | 'FINANCE';
	category: string;
	header: string;
	summary: string;
	intelligence?: string[];
	staged_output?: StagedOutput;
	suggested_actions?: SuggestedAction[];
	status:
		| 'pending'
		| 'ready'
		| 'executing'
		| 'done'
		| 'failed'
		| 'dismissed'
		| 'archived'
		| 'agent_running'
		| 'awaiting_input';
	privacy_tier: number;
	has_workspace: boolean;
	resolved_at?: string;
	user_feedback?: string;
	feedback_type?: string;
	confidence?: number;
	router_model?: string;
	stager_model?: string;
	updated_at?: string;
	entity_id?: string;
	source_ref?: string;
	source_url?: string;
	selected_action_id?: string;
	actor_name?: string;
	actor_email?: string;
	space_id?: string;
	space_name?: string;
	space_color?: string;
	bookmarked_at?: string;
	read_at?: string;
	group_active_at?: string;
	context_id?: string;
	last_error?: string;
	source_context?: string;
	tags?: TagAssignment[];
}

/** The original ingested event behind a card — raw body + platform metadata. */
export interface SourceEvent {
	event_id: string;
	platform: string;
	raw_event_type: string;
	timestamp?: string;
	actor_name?: string;
	actor_email?: string;
	actor_handle?: string;
	subject_type?: string;
	subject_id?: string;
	subject_title?: string;
	subject_url?: string;
	body?: string;
	metadata: Record<string, unknown>;
}

/** A structured key event with separate timestamp */
export interface KeyEvent {
	event: string;
	timestamp?: string;
}

/** Rolling LLM-generated summary for an entity group */
export interface GroupSummary {
	entity_id: string;
	headline: string;
	summary: string;
	key_events?: (string | KeyEvent)[];
	current_status?: string;
	pending_actions?: string[];
	card_count: number;
	card_ids: string[];
	updated_at?: string;
}

/** A group of cards sharing the same entity or semantic context */
export interface CardGroup {
	entity_id: string;
	entity_title: string;
	entity_url?: string;
	platform: string;
	card_count: number;
	top_priority: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
	latest_at: string;
	has_pending: boolean;
	unread_count: number;
	cards: ActionCard[];
	sort_key?: string;
	context_id?: string;
	context_label?: string;
	platforms?: string[];
	group_summary?: GroupSummary;
	tags?: TagAssignment[];
	sub_groups?: CardGroup[];
}

/** Response from GET /cards/grouped */
export interface GroupedCardsResponse {
	groups: CardGroup[];
	total_groups: number;
	has_more?: boolean;
	date?: string;
	prev_date?: string;
	next_date?: string;
	space_id?: string;
}

/** Paginated cards list from GET /cards */
export interface CardsListResponse {
	cards: ActionCard[];
	total: number;
	limit: number;
	offset: number;
}

/** Request body for POST /actions/execute */
export interface ExecuteActionRequest {
	card_id: string;
	action_id: string;
	modifications?: Record<string, unknown>;
}

/** Response body from POST /actions/execute */
export interface ExecuteActionResponse {
	card_id: string;
	action_id: string;
	status: string;
	result_url?: string;
	error?: string;
}

