// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0


/** Chat message */
export interface ChatMessage {
	message_id: string;
	timestamp: string;
	role: 'user' | 'assistant';
	content: string;
	referenced_cards: string[];
	referenced_events: string[];
	conversation_id?: string;
}

/** Chat response from POST /chat */
export interface ChatResponse {
	message: ChatMessage;
	referenced_cards: string[];
	referenced_events: string[];
}

/** Chat conversation */
export interface Conversation {
	conversation_id: string;
	title: string;
	space_id: string | null;
	created_at: string;
	updated_at: string;
	preview: string;
	message_count: number;
}

