// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0

// A stage's stored value is `agent/<agentId>/<modelString>` (or `agent/<agentId>` for the
// agent's default model). Splitting keeps slugs with their own slashes (lmstudio/…) intact.
export function parseAgentModel(v: string): { agentId: string; modelString: string } | null {
	if (!v || !v.startsWith('agent/')) return null;
	const parts = v.split('/');
	return { agentId: parts[1] || '', modelString: parts.slice(2).join('/') };
}

export function agentModelString(value: string): string {
	const p = parseAgentModel(value);
	return p ? p.modelString : '';
}

export function agentModelValue(agentId: string, modelString: string): string {
	return modelString ? `agent/${agentId}/${modelString}` : `agent/${agentId}`;
}

/** Switch structured roles onto (or off) the agent backend, preserving/restoring
 *  each role's prior provider model in `providerBackup`. */
export function applyAgentMode(
	models: Record<string, string>,
	providerBackup: Record<string, string>,
	on: boolean,
	selectedAgent: string,
	agentRoles: string[],
	defaultModels: Record<string, string>
): { models: Record<string, string>; providerBackup: Record<string, string> } {
	const nextModels = { ...models };
	const nextBackup = { ...providerBackup };
	if (on) {
		for (const r of agentRoles) {
			if (!parseAgentModel(nextModels[r])) {
				nextBackup[r] = nextModels[r];
				nextModels[r] = agentModelValue(selectedAgent, '');
			}
		}
	} else {
		for (const r of agentRoles) {
			if (parseAgentModel(nextModels[r])) {
				nextModels[r] = nextBackup[r] || defaultModels[r];
			}
		}
	}
	return { models: nextModels, providerBackup: nextBackup };
}

/** Re-point every structured role at a newly-selected agent, preserving each
 *  role's typed model string. */
export function applySelectAgent(
	models: Record<string, string>,
	agentId: string,
	agentRoles: string[]
): Record<string, string> {
	const nextModels = { ...models };
	for (const r of agentRoles) {
		nextModels[r] = agentModelValue(agentId, agentModelString(nextModels[r]));
	}
	return nextModels;
}
