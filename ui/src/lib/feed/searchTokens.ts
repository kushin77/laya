export function getCurrentWord(input: HTMLInputElement): string {
	const pos = input.selectionStart ?? input.value.length;
	const before = input.value.slice(0, pos);
	const match = before.match(/(\S+)$/);
	return match ? match[1] : '';
}

// Splits a raw search query into text search tokens and `#tag` tokens for the
// backend all-days search (`/cards/grouped?search=&tags=`). Bare '#' is a
// half-typed tag, not a search for a literal '#', so it's dropped from both.
export function splitSearchTokens(query: string): { textTokens: string[]; tagTokens: string[] } {
	const tagTokens: string[] = [];
	const textTokens: string[] = [];
	for (const token of query.trim().split(/\s+/)) {
		if (token.startsWith('#')) {
			if (token.length > 1) tagTokens.push(token.slice(1));
		} else if (token) {
			textTokens.push(token);
		}
	}
	return { textTokens, tagTokens };
}

// The autocomplete query is the last whitespace-delimited token, but only when
// it's a half-typed `#tag` — otherwise there's nothing to suggest against.
export function tagAutocompleteQueryFor(searchQuery: string, showTagAutocomplete: boolean): string {
	if (!showTagAutocomplete) return '';
	const tokens = searchQuery.trim().split(/\s+/);
	const last = tokens[tokens.length - 1] || '';
	if (last.startsWith('#')) return last.slice(1).toLowerCase();
	return '';
}
