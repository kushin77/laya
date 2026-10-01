// Recomputes the related-entity-id set after an unlink, shared by the single-card
// and bulk unlink handlers (previously near-duplicated in +page.svelte). Returns
// `{ clear: true }` when the related filter should be dropped entirely — no source
// card, the fetch failed, or the source itself no longer has any related cards.
export async function recomputeRelatedEntityIds(
	sourceCardId: string,
	sourceEntityId: string,
	getRelatedCards: (cardId: string) => Promise<{ total_related_cards: number; related_cards: { entity_id: string }[] }>
): Promise<{ clear: true } | { clear: false; entityIds: string[] }> {
	if (!sourceCardId) return { clear: true };
	try {
		const data = await getRelatedCards(sourceCardId);
		if (data.total_related_cards === 0) return { clear: true };
		const entityIds = [...new Set([
			sourceEntityId,
			...data.related_cards.map((r) => r.entity_id)
		].filter(Boolean))] as string[];
		return { clear: false, entityIds };
	} catch {
		return { clear: true };
	}
}
