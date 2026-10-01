// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0

export type MenuPos = { top: number; right: number };

/** Shared state + behavior for a button-triggered dropdown menu that is
 *  positioned relative to its trigger and dismissed on an outside click.
 *  Replaces the near-identical header/overflow/move menu implementations
 *  that each re-wrote this boilerplate (card-detail split, #62). */
export function createPositionedMenu(opts: { placement?: 'above' | 'below' } = {}) {
	let open = $state(false);
	let btnEl: HTMLElement | undefined = $state();
	let menuEl: HTMLElement | undefined = $state();
	let pos = $state<MenuPos>({ top: 0, right: 0 });

	function toggle() {
		if (open) { open = false; return; }
		if (!btnEl) return;
		const rect = btnEl.getBoundingClientRect();
		pos = opts.placement === 'below'
			? { top: rect.bottom + 4, right: window.innerWidth - rect.right }
			: { top: rect.top - 4, right: window.innerWidth - rect.right };
		open = true;
	}

	$effect(() => {
		if (!open) return;
		function handleClick(e: MouseEvent) {
			const target = e.target as HTMLElement;
			if (!menuEl?.contains(target) && !btnEl?.contains(target)) {
				open = false;
			}
		}
		document.addEventListener('click', handleClick, true);
		return () => document.removeEventListener('click', handleClick, true);
	});

	return {
		get open() { return open; },
		set open(v: boolean) { open = v; },
		get pos() { return pos; },
		get btnEl() { return btnEl; },
		set btnEl(v: HTMLElement | undefined) { btnEl = v; },
		get menuEl() { return menuEl; },
		set menuEl(v: HTMLElement | undefined) { menuEl = v; },
		toggle,
	};
}
