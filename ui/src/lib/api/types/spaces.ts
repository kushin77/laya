// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0


/** Space for organizing event sources with model/key configs */
export interface Space {
	space_id: string;
	name: string;
	description?: string;
	icon: string;
	color: string;
	router_model?: string;
	stager_model?: string;
	chat_model?: string;
	trace_model?: string;
	omni_model?: string;
	coding_agent?: string;
	is_default: boolean;
	paused: boolean;
	position: number;
	source_count: number;
	created_at?: string;
	updated_at?: string;
}

/** Source: maps an n8n workflow to a space */
export interface Source {
	source_id: string;
	name: string;
	platform: string;
	workflow_id: string;
	space_id: string;
	space_name?: string;
	source_type?: string;
	webhook_path?: string;
	created_at?: string;
}

/** Available n8n workflow for source assignment */
export interface AvailableWorkflow {
	workflow_id: string;
	name: string;
	platform: string;
	source_type: string;
	active: boolean;
	registered: boolean;
	connection_id?: string;
}

/** Response from GET /spaces */
export interface SpacesResponse {
	spaces: Space[];
}

/** Response from GET /sources */
export interface SourcesResponse {
	sources: Source[];
}

/** Response from GET /sources/available-workflows */
export interface AvailableWorkflowsResponse {
	workflows: AvailableWorkflow[];
}

/** A repo assigned to a space */
export interface SpaceRepo {
	repo_name: string;
	position: number;
	path: string | null;
	platform: string;
	remote_id: string;
	exists: boolean;
}

/** Response from GET /spaces/:id/repos */
export interface SpaceReposResponse {
	repos: SpaceRepo[];
}

/** Response from GET /spaces/:id/api-keys */
export interface SpaceApiKeysResponse {
	providers: Record<string, { configured: boolean }>;
}

