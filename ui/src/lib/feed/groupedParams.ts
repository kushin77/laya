import type { FeedFilters } from '$lib/stores/feedFilters';
import { splitSearchTokens } from './searchTokens';

// Build the /cards/grouped query params shared by loadGroups and loadMoreGroups
// (minus limit/offset, which the caller sets).
//
// `searchQuery` must be read UNTRACKED at the call site (`untrack(() => searchQuery)`)
// before being passed in here. loadGroups() runs synchronously inside the
// $feedDate/$feedFilters reload effect, so a tracked read of searchQuery would
// silently make it a dependency of that effect — every keystroke would re-run
// it and fire a full GET /cards/grouped, defeating the 300ms search debounce
// (review §2 UI — P4-29). Backend search only applies in all-days mode (see the
// search/tags params below), which reloads via its own debounced effect;
// normal-mode search is filtered client-side.
export function buildGroupedParams(f: FeedFilters, date: string, searchQuery: string) {
	const { textTokens, tagTokens } = splitSearchTokens(searchQuery);
	const searchText = textTokens.join(' ');
	const isAllDays = f.showAllDaysSearch;
	return {
		status: f.statusFilters.length ? f.statusFilters.join(',') : undefined,
		priority: f.priorityFilters.length ? f.priorityFilters.join(',') : undefined,
		sort: f.sortBy,
		sort_asc: f.sortAsc || undefined,
		show_archived: f.showArchived || undefined,
		date: (f.showBookmarked || f.showRelated || isAllDays) ? undefined : date,
		space_id: f.spaceFilter.length ? f.spaceFilter.join(',') : undefined,
		bookmarked: f.showBookmarked || undefined,
		related_entity_ids: f.showRelated ? f.relatedEntityIds.join(',') : undefined,
		has_workspace: f.hasWorkspace || undefined,
		unread_only: f.showUnreadOnly || undefined,
		search: isAllDays && searchText ? searchText : undefined,
		tags: isAllDays && tagTokens.length ? tagTokens.join(',') : undefined
	};
}
