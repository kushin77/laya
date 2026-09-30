import { describe, it, expect, vi } from 'vitest';
import { recomputeRelatedEntityIds } from './relatedFilter';

describe('recomputeRelatedEntityIds', () => {
	it('clears when there is no source card id', async () => {
		const getRelatedCards = vi.fn();
		const result = await recomputeRelatedEntityIds('', 'e1', getRelatedCards);
		expect(result).toEqual({ clear: true });
		expect(getRelatedCards).not.toHaveBeenCalled();
	});

	it('clears when the source has no related cards left', async () => {
		const getRelatedCards = vi.fn().mockResolvedValue({ total_related_cards: 0, related_cards: [] });
		const result = await recomputeRelatedEntityIds('c1', 'e1', getRelatedCards);
		expect(result).toEqual({ clear: true });
	});

	it('clears when the fetch throws', async () => {
		const getRelatedCards = vi.fn().mockRejectedValue(new Error('boom'));
		const result = await recomputeRelatedEntityIds('c1', 'e1', getRelatedCards);
		expect(result).toEqual({ clear: true });
	});

	it('returns the deduped entity id set including the source entity', async () => {
		const getRelatedCards = vi.fn().mockResolvedValue({
			total_related_cards: 2,
			related_cards: [{ entity_id: 'e2' }, { entity_id: 'e1' }]
		});
		const result = await recomputeRelatedEntityIds('c1', 'e1', getRelatedCards);
		expect(result.clear).toBe(false);
		if (!result.clear) {
			expect(result.entityIds.sort()).toEqual(['e1', 'e2']);
		}
	});
});
