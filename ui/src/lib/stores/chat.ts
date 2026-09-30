// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0

import { writable } from 'svelte/store';
import type { ChatMessage, Conversation } from '$lib/api/types';

/** Whether the chat sidebar is shown at all. */
export const chatOpen = writable(false);

/** Whether the chat list panel is shown (vs the active chat view). */
export const chatListOpen = writable(true);

/** When true, the chat sidebar widens into a focused overlay. Session-only
 *  (not persisted) and reset on close, so reopening always starts in the
 *  default sidebar layout. */
export const chatExpanded = writable(false);

/** Card ID to navigate to in the feed (set by chat card links, consumed by feed page). */
export const pendingCardId = writable<string | null>(null);

/** All state describing the active chat conversation: its messages, the
 *  in-flight send/stream status, which conversation is selected, the list of
 *  conversations, and any pending card-context/preset for the next message.
 *  Consolidated into one store so invariants like "sending implies not idle"
 *  live in a single update instead of being reconstructed from a dozen
 *  independently-writable stores. */
export interface ChatSessionState {
	messages: ChatMessage[];
	/** Preset text to drop into the input (set by chat card links). */
	inputPreset: string;
	/** ID of the message currently being streamed (null when idle). */
	streamingMessageId: string | null;
	/** True from send() until the stream completes (or the WS drops). Store-backed
	 *  (not component state) so closing/reopening the sidebar can't orphan it, and
	 *  so the chatStream handler — which lives outside the component — can clear it.
	 *  Overall busy state = sending || streamingMessageId !== null. */
	sending: boolean;
	/** Tools currently being called by the assistant. */
	activeTools: string[];
	/** Active conversation ID (null = no conversation selected, show list). */
	activeConversationId: string | null;
	/** All conversations for the list view. */
	conversations: Conversation[];
	/** Card context string for system prompt injection (hidden from user input). */
	cardContext: string | null;
	/** Card IDs for conversation anchoring (used with card-context chats). */
	cardIds: string[] | null;
}

function initialChatSessionState(): ChatSessionState {
	return {
		messages: [],
		inputPreset: '',
		streamingMessageId: null,
		sending: false,
		activeTools: [],
		activeConversationId: null,
		conversations: [],
		cardContext: null,
		cardIds: null
	};
}

export const chatSession = writable<ChatSessionState>(initialChatSessionState());
