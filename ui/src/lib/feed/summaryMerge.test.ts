import { describe, it, expect } from 'vitest';
import { mergeSpaceSummaries } from './summaryMerge';
import type { SpaceSummary } from '$lib/api/types';

function summary(overrides: Partial<SpaceSummary>): SpaceSummary {
	return {
		space_id: 's1',
		space_name: 'Space 1',
		space_color: '#000',
		card_ids: [],
		updated_at: null,
		summary: {
			events_and_meetings: [],
			action_items: [],
			key_updates: []
		},
		...overrides
	};
}

describe('mergeSpaceSummaries', () => {
	it('returns empty sections and null updatedAt for no summaries', () => {
		const { merged, updatedAt } = mergeSpaceSummaries([]);
		expect(merged).toEqual({ events_and_meetings: [], action_items: [], key_updates: [] });
		expect(updatedAt).toBeNull();
	});

	it('skips space summaries with no summary payload', () => {
		const { merged } = mergeSpaceSummaries([summary({ summary: null as any })]);
		expect(merged.action_items).toEqual([]);
	});

	it('tags merged items with their source space', () => {
		const s = summary({
			space_id: 'sales',
			space_name: 'Sales',
			space_color: '#f00',
			summary: {
				events_and_meetings: [],
				action_items: [{ text: 'follow up' } as any],
				key_updates: []
			}
		});
		const { merged } = mergeSpaceSummaries([s]);
		expect(merged.action_items).toEqual([
			{ text: 'follow up', space_id: 'sales', space_name: 'Sales', space_color: '#f00' }
		]);
	});

	it('returns the latest updated_at across summaries', () => {
		const a = summary({ updated_at: '2026-01-01T00:00:00Z' });
		const b = summary({ updated_at: '2026-03-01T00:00:00Z' });
		const { updatedAt } = mergeSpaceSummaries([a, b]);
		expect(updatedAt).toBe('2026-03-01T00:00:00Z');
	});
});
