import { describe, it, expect } from 'vitest';
import { splitSearchTokens, tagAutocompleteQueryFor } from './searchTokens';

describe('splitSearchTokens', () => {
	it('splits plain text into text tokens', () => {
		expect(splitSearchTokens('hello world')).toEqual({ textTokens: ['hello', 'world'], tagTokens: [] });
	});

	it('splits #tag tokens into tagTokens', () => {
		expect(splitSearchTokens('hello #urgent world #reviewer')).toEqual({
			textTokens: ['hello', 'world'],
			tagTokens: ['urgent', 'reviewer']
		});
	});

	it('drops a bare half-typed #', () => {
		expect(splitSearchTokens('hello #')).toEqual({ textTokens: ['hello'], tagTokens: [] });
	});

	it('returns empty arrays for an empty query', () => {
		expect(splitSearchTokens('')).toEqual({ textTokens: [], tagTokens: [] });
	});
});

describe('tagAutocompleteQueryFor', () => {
	it('returns empty string when autocomplete is not open', () => {
		expect(tagAutocompleteQueryFor('#rev', false)).toBe('');
	});

	it('returns the lowercased partial tag when open', () => {
		expect(tagAutocompleteQueryFor('hello #Rev', true)).toBe('rev');
	});

	it('returns empty string when the last token is not a tag', () => {
		expect(tagAutocompleteQueryFor('hello world', true)).toBe('');
	});
});
