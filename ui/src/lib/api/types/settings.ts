// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0


/** Model configuration from settings.json */
export interface ModelSettings {
	router: string;
	stager: string;
	chat: string;
	trace: string;
	local: string;
}

/** API key presence indicators (never exposes actual keys) */
export interface ApiKeyStatus {
	anthropic: boolean;
	openai: boolean;
	google: boolean;
	openrouter: boolean;
	n8n: boolean;
}

/** A single model option returned by the available-models endpoint */
export interface ModelOption {
	id: string;
	name: string;
}

/** A provider group in the available-models response */
export interface ProviderModels {
	provider: string;
	label: string;
	models: ModelOption[];
}

/** Response from GET /settings/available-models */
export interface AvailableModelsResponse {
	providers: ProviderModels[];
}

/** An installed CLI agent usable as the inference backend (GET /settings/agent-backends) */
export interface AgentBackend {
	agent_id: string;
	available: boolean;
	path: string;
	/** 'native' = the CLI enforces the JSON schema; 'best_effort' = inject schema + validate/retry */
	tier: 'native' | 'best_effort';
	hint: string;
}

/** Response from GET /settings/agent-backends */
export interface AgentBackendsResponse {
	backends: AgentBackend[];
}

/** Native usage-limit signal scraped from an agent (Claude Code's rate_limit_event) */
export interface AgentRateLimit {
	status: string | null;
	resets_at: number | null;
	rate_limit_type: string | null;
}

/** Per-agent window usage + limit (from GET /agent-budget) */
export interface AgentBudgetAgentStatus {
	agent_id: string;
	window_hours: number;
	window_token_limit: number;
	pause_at_percent: number;
	tokens_used: number;
	calls: number;
	percent: number | null;
	rate_limit: AgentRateLimit | null;
}

/** Agent inference backend usage-limit budget status (GET /agent-budget) */
export interface AgentBudgetStatus {
	enabled: boolean;
	agents: AgentBudgetAgentStatus[];
	is_paused: boolean;
	paused_until: string | null;
	paused_reason: string | null;
	paused_workflow_count: number;
}

/** Per-agent budget config sent on PUT /agent-budget */
export interface AgentBudgetConfigInput {
	window_token_limit: number;
	window_hours: number;
	pause_at_percent: number;
}

/** n8n integration settings */
export interface N8nSettings {
	base_url: string;
	webhooks: Record<string, string>;
}

/** n8n connection test result */
export interface N8nTestResult {
	base_url: string;
	health: string;
	webhook: {
		path: string;
		status_code?: number;
		reachable: boolean;
		error?: string;
	} | null;
}

/** Feed filter/sort preferences persisted to settings */
export interface FeedPreferences {
	statusFilters: string[];
	priorityFilters: string[];
	sortBy: string;
	showArchived: boolean;
	showBookmarked: boolean;
	spaceFilter: string[];
}

/** Pipeline processing settings (advanced) */
export interface PipelineSettings {
	model_timeout: number;
	llm_retries: number;
	max_retry_attempts: number;
	max_concurrent_events: number;
	queue_poll_interval: number;
}

/** Full settings response from GET /settings */
export interface Settings {
	models: ModelSettings;
	api_keys: ApiKeyStatus;
	coding_agent: string;
	agent_paths: Record<string, string>;
	privacy: {
		tier3_sources: string[];
		tier3_processing: string;
	};
	briefing: {
		enabled: boolean;
		time: string;
		timezone: string;
		per_space?: boolean;
	};
	notifications: {
		enabled: boolean;
		min_priority: string;
	};
	retention?: {
		card_retention_days: number;
		chat_retention_days: number;
		audit_retention_days: number;
		omni_retention_days: number;
		ingestion_errors_retention_days: number;
		firing_log_retention_days: number;
	};
	omni?: {
		enabled: boolean;
		resynthesis_time: string;
		density: string;
		timezone: string;
		rolling_interval_hours: number;
		event_threshold: number;
	};
	n8n?: N8nSettings;
	feed_preferences?: FeedPreferences;
	pipeline?: PipelineSettings;
	setup_complete?: boolean;
	smart_grouping?: {
		context_association: boolean;
		smart_display: boolean;
		strictness: 'strict' | 'balanced' | 'lenient' | 'custom';
		confidence_threshold: number;
		auto_confirm_threshold: number;
		centroid_threshold: number;
		cross_platform_required: boolean;
		entity_ref_overlap_mode: 'hard_gate' | 'soft_boost' | 'disabled';
		always_llm: boolean;
	};
	group_summaries?: {
		enabled: boolean;
	};
	mcp?: {
		tool_scopes: McpToolScopes;
		auth_mode: McpAuthMode;
	};
	logging?: {
		level?: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR';
	};
}

export type McpAuthMode = 'bearer' | 'none';

export interface McpToolScopes {
	read: boolean;
	write: boolean;
	egress: boolean;
}

export interface McpExternalServerConfig {
	enabled: boolean;
	command: string;
}

export interface McpExternalServers {
	codeidx: McpExternalServerConfig;
}

export interface McpConfig {
	tool_scopes: McpToolScopes;
	auth_mode: McpAuthMode;
	has_token: boolean;
	token_prefix: string | null;
	url: string;
	sse_url: string;
	external_servers: McpExternalServers;
}

export interface McpConfigUpdate {
	tool_scopes?: McpToolScopes;
	auth_mode?: McpAuthMode;
	external_servers?: McpExternalServers;
}

export interface McpToken {
	token: string;
}

/** A custom local model provider (LMStudio, Ollama, etc.) */
export interface CustomProvider {
	id: string;
	name: string;
	base_url: string;
	provider_type: 'lmstudio' | 'ollama' | 'openai_compatible';
	default_timeout: number;
	api_key_ref?: string;
	capabilities_override?: {
		supports_tool_calling?: boolean;
		supports_structured_output?: boolean;
	};
}

/** Result from testing a custom provider's connectivity */
export interface CustomProviderTestResult {
	provider_id: string;
	reachable: boolean;
	models_count: number;
	llm_count: number;
	embedding_count: number;
	inference_ok: boolean;
	latency_ms: number;
	error: string | null;
}

/** A model discovered from a custom provider */
export interface DiscoveredModel {
	id: string;
	name: string;
	type: string;
	max_context_length: number | null;
	supports_tool_calling: boolean;
	supports_structured_output: boolean;
	supports_vision: boolean;
	params: string | null;
	quantization: string | null;
	loaded: boolean;
}

