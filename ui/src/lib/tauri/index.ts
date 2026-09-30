// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0

// Single point of contact for Tauri APIs. Every call is a dynamic import so
// this module loads fine in a plain browser (Vite dev, tests) where the
// @tauri-apps packages aren't backed by a real webview — invokeSafe/getWindow
// just no-op instead of throwing.

let _isTauri: boolean | null = null;

export function isTauri(): boolean {
	if (_isTauri !== null) return _isTauri;
	_isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
	return _isTauri;
}

export async function invokeSafe<T>(cmd: string, args?: Record<string, unknown>): Promise<T | null> {
	try {
		const { invoke } = await import('@tauri-apps/api/core');
		return await invoke<T>(cmd, args);
	} catch {
		return null;
	}
}

export async function getWindow() {
	try {
		const { getCurrentWebviewWindow } = await import('@tauri-apps/api/webviewWindow');
		return getCurrentWebviewWindow();
	} catch {
		return null;
	}
}
