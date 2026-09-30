import type { SpaceSummary, DaySummary } from '$lib/api/types';

export function mergeSpaceSummaries(summaries: SpaceSummary[]): { merged: DaySummary; updatedAt: string | null } {
	const merged: DaySummary = { events_and_meetings: [], action_items: [], key_updates: [] };
	let latest: string | null = null;
	for (const ss of summaries) {
		if (!ss.summary) continue;
		if (ss.updated_at && (!latest || ss.updated_at > latest)) latest = ss.updated_at;
		for (const section of ['events_and_meetings', 'action_items', 'key_updates'] as const) {
			for (const item of ss.summary[section]) {
				merged[section].push({
					...item,
					space_id: ss.space_id,
					space_name: ss.space_name,
					space_color: ss.space_color,
				});
			}
		}
	}
	return { merged, updatedAt: latest };
}
