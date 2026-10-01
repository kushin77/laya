// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0

// Settings-panel state for the Agent Usage Limits section — structurally the
// same shape as the Cost Control state in `budget.ts`, but window/token based
// rather than $/month based (agents bill against usage limits, not dollars).

import { writable, get } from 'svelte/store';
import { engineApi } from '$lib/api/engine';
import type { AgentBudgetStatus } from '$lib/api/types';
import { agentBudgetPaused, loadAgentBudgetStatus } from './budget';

export type AgentBudgetAgentConfig = {
	window_token_limit: number | null;
	window_hours: number;
	pause_at_percent: number;
};

export const agentBudgetEnabled = writable(false);
export const agentBudgetAgents = writable<Record<string, AgentBudgetAgentConfig>>({});
export const agentBudgetStatus = writable<AgentBudgetStatus | null>(null);
export const savingAgentBudget = writable(false);
export const resumingAgentBudget = writable(false);

export async function loadAgentBudget() {
	try {
		const data = await engineApi.getAgentBudget();
		agentBudgetStatus.set(data);
		agentBudgetEnabled.set(data.enabled);
		agentBudgetAgents.update((agents) => {
			const next = { ...agents };
			for (const a of data.agents) {
				next[a.agent_id] = {
					window_token_limit: a.window_token_limit || null,
					window_hours: a.window_hours,
					pause_at_percent: a.pause_at_percent
				};
			}
			return next;
		});
	} catch (e) {
		console.error('Failed to load agent budget:', e);
	}
}

export async function saveAgentBudget() {
	savingAgentBudget.set(true);
	try {
		const agents: Record<string, { window_token_limit: number; window_hours: number; pause_at_percent: number }> = {};
		for (const [id, c] of Object.entries(get(agentBudgetAgents))) {
			if (c.window_token_limit && c.window_token_limit > 0) {
				agents[id] = {
					window_token_limit: Math.round(c.window_token_limit),
					window_hours: c.window_hours || 5,
					pause_at_percent: c.pause_at_percent || 85
				};
			}
		}
		await engineApi.updateAgentBudget({ enabled: get(agentBudgetEnabled), agents });
		await loadAgentBudget();
		loadAgentBudgetStatus();
	} catch (e) {
		console.error('Failed to save agent budget:', e);
	} finally {
		savingAgentBudget.set(false);
	}
}

let _agentBudgetTimer: ReturnType<typeof setTimeout> | null = null;
export function debounceSaveAgentBudget() {
	if (_agentBudgetTimer) clearTimeout(_agentBudgetTimer);
	_agentBudgetTimer = setTimeout(saveAgentBudget, 600);
}

export async function handleResumeAgent() {
	resumingAgentBudget.set(true);
	try {
		await engineApi.resumeAgentBudget();
		await loadAgentBudget();
		loadAgentBudgetStatus();
	} catch (e) {
		console.error('Failed to resume agent budget:', e);
	} finally {
		resumingAgentBudget.set(false);
	}
}

export function fmtTokensShort(n: number): string {
	if (n >= 1_000_000) return (n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1) + 'M';
	if (n >= 1_000) return Math.round(n / 1_000) + 'K';
	return '' + n;
}

export function agentStatusFor(status: AgentBudgetStatus | null, agentId: string) {
	return status?.agents.find((a) => a.agent_id === agentId) ?? null;
}

// re-export so callers only need one module for the paused flag mirrored from budget.ts
export { agentBudgetPaused };
