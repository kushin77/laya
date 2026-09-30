// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0


/** Field definition for a platform credential form */
export interface FieldDef {
	key: string;
	label: string;
	type: 'text' | 'password' | 'checkbox';
	placeholder?: string;
	help?: string;
}

/** Platform configuration from GET /connections/platforms */
export interface PlatformConfig {
	label: string;
	category: string;
	icon: string;
	n8n_type: string;
	n8n_node: string;
	oauth: boolean;
	fields: FieldDef[];
}

/** Response from POST /settings/n8n/bootstrap */
export interface N8nBootstrapResponse {
	status: string;
	message: string;
	has_api_key: boolean;
}

/** Platforms registry response */
export interface PlatformsResponse {
	platforms: Record<string, PlatformConfig>;
}

/** An n8n credential as returned by GET /connections */
export interface N8nConnection {
	id: string;
	name: string;
	type: string;
	platform: string | null;
	platform_label: string;
	created_at: string;
	updated_at: string;
}

/** Response from GET /connections */
export interface ConnectionsResponse {
	connections: N8nConnection[];
}

/** Request body for POST /connections */
export interface CreateConnectionRequest {
	platform: string;
	name: string;
	credentials: Record<string, string>;
}

/** Response from POST /connections */
export interface CreateConnectionResponse {
	status: string;
	id: string;
	name: string;
	platform: string;
}

/** Response from POST /connections/test */
export interface ConnectionTestResult {
	status: 'connected' | 'unauthorized' | 'unreachable' | 'timeout' | 'no_api_key' | 'error';
	message: string;
}

/** Email provider detection result */
export interface EmailProviderDetection {
	detected: boolean;
	provider: string;
	method: 'oauth' | 'app_password' | 'manual';
	redirect_platform?: string;
	smtp_host?: string;
	smtp_port?: number;
	imap_host?: string;
	imap_port?: number;
	use_tls?: boolean;
	note?: string;
}

/** OAuth flow start response */
export interface OAuthStartResponse {
	auth_url: string;
	state: string;
}

