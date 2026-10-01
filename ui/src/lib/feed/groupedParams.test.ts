import { describe, it, expect } from 'vitest';
import { buildGroupedParams } from './groupedParams';
import type { FeedFilters } from '$lib/stores/feedFilters';

function filters(overrides: Partial<FeedFilters> = {}): FeedFilters {
	return {
		statusFilters: [],
		priorityFilters: [],
		sortBy: 'created_at',
		sortAsc: false,
		showArchived: false,
		showBookmarked: false,
		hasWorkspace: false,
		showUnreadOnly: false,
		spaceFilter: [],
		platformFilters: [],
		timeBrush: null,
		showRelated: false,
		relatedEntityIds: [],
		relatedSourceHeader: '',
		relatedSourceCardId: '',
		relatedSourceEntityId: '',
		showAllDaysSearch: false,
		...overrides
	};
}

describe('buildGroupedParams', () => {
	it('sends the date when not in bookmarked/related/all-days mode', () => {
		const params = buildGroupedParams(filters(), '2026-09-30', '');
		expect(params.date).toBe('2026-09-30');
		expect(params.search).toBeUndefined();
		expect(params.tags).toBeUndefined();
	});

	it('omits the date in bookmarked mode', () => {
		const params = buildGroupedParams(filters({ showBookmarked: true }), '2026-09-30', '');
		expect(params.date).toBeUndefined();
		expect(params.bookmarked).toBe(true);
	});

	it('only forwards search/tags in all-days mode', () => {
		const notAllDays = buildGroupedParams(filters(), '2026-09-30', 'hello #urgent');
		expect(notAllDays.search).toBeUndefined();
		expect(notAllDays.tags).toBeUndefined();

		const allDays = buildGroupedParams(filters({ showAllDaysSearch: true }), '2026-09-30', 'hello #urgent');
		expect(allDays.search).toBe('hello');
		expect(allDays.tags).toBe('urgent');
		expect(allDays.date).toBeUndefined();
	});

	it('joins array filters with commas', () => {
		const params = buildGroupedParams(
			filters({ statusFilters: ['pending', 'ready'], spaceFilter: ['s1', 's2'] }),
			'2026-09-30',
			''
		);
		expect(params.status).toBe('pending,ready');
		expect(params.space_id).toBe('s1,s2');
	});
});
