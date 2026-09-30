// Find the DOM element for a card. Prefers the individual ActionCard element
// over the group wrapper — the group wrapper also carries data-card-id for
// its topCard, but is ~11k px tall for large groups so scrolling to it
// centers the group, not the card. Falls back to the group wrapper when
// the group is collapsed (individual card not rendered).
export function findCardElement(cardId: string): Element | null {
	return document.querySelector(`[data-card-id="${cardId}"]:not([data-group-entity])`)
		?? document.querySelector(`[data-card-id="${cardId}"]`);
}

// Walk up the DOM to find the nearest scrollable ancestor (overflow auto/scroll
// with content that actually overflows). This avoids assuming which container
// scrolls — the layout has nested overflow-auto on both <main> and containerEl.
export function getScrollParent(el: Element): Element {
	let parent = el.parentElement;
	while (parent) {
		const { overflowY } = getComputedStyle(parent);
		if ((overflowY === 'auto' || overflowY === 'scroll') && parent.scrollHeight > parent.clientHeight) {
			return parent;
		}
		parent = parent.parentElement;
	}
	return document.documentElement;
}

// Scroll an element to the vertical center of its nearest scrollable ancestor.
// Uses manual scrollTo on the specific container to avoid scrollIntoView's
// nested scroll container bug (it scrolls ALL overflow ancestors unpredictably).
export function scrollElToCenter(el: Element, behavior: ScrollBehavior = 'smooth') {
	const scroller = getScrollParent(el);
	const scrollerRect = scroller.getBoundingClientRect();
	const elRect = el.getBoundingClientRect();
	const targetTop = scroller.scrollTop + (elRect.top - scrollerRect.top) - (scrollerRect.height - elRect.height) / 2;
	scroller.scrollTo({ top: targetTop, behavior });
}
