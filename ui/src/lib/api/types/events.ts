// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0


/** Inbound Laya Event (n8n -> Engine) */
export interface LayaEvent {
	event_id: string;
	timestamp: string;
	source: {
		platform: string;
		connection_id?: string;
		raw_event_type: string;
	};
	actor: {
		name: string;
		email: string;
		platform_handle?: string;
	};
	subject: {
		type: string;
		id: string;
		title: string;
		url?: string;
	};
	content: {
		body: string;
		attachments: string[];
		metadata: Record<string, unknown>;
	};
}

