// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0

// Network + Tauri logic extracted out of RunAgentModal.svelte so the
// component only deals with presentation. Everything here goes through the
// engineApi boundary and the tauri wrapper — no raw fetch()/invoke() calls.

import { engineApi } from '$lib/api/engine';
import { invokeSafe, getWindow } from '$lib/tauri';

export interface UploadedFile {
	path: string;
	filename: string;
	previewUrl: string | null;
	contentType: string;
	isImage: boolean;
}

export async function browseAddDir(title = 'Select additional directory'): Promise<string | null> {
	return invokeSafe<string>('pick_folder', { title });
}

export async function uploadFile(file: File): Promise<UploadedFile> {
	const result = await engineApi.uploadAgentFile(file);
	const contentType: string = result.content_type || file.type || '';
	const isImage = contentType.startsWith('image/');
	const previewUrl = isImage ? URL.createObjectURL(file) : null;
	return {
		path: result.path,
		filename: result.filename,
		previewUrl,
		contentType,
		isImage
	};
}

// In Tauri on macOS, WKWebView does not emit HTML5 drop events for OS
// file drops. We receive the paths from Tauri's native drag-drop event
// and send them to a path-based upload endpoint; since the engine is
// local, it reads from that path directly.
export async function uploadFileByPath(path: string): Promise<UploadedFile> {
	const result = await engineApi.uploadAgentFileByPath(path);
	const contentType: string = result.content_type || '';
	const isImage = contentType.startsWith('image/');
	return {
		path: result.path,
		filename: result.filename,
		previewUrl: null,
		contentType,
		isImage
	};
}

export function deleteStagedFile(path: string): void {
	// Fire-and-forget — UI doesn't need to wait, and the 24h sweep is a
	// backstop if this ever fails.
	engineApi.deleteAgentStagingFile(path).catch(() => {
		// Ignore — sweep will clean up eventually.
	});
}

export interface DragDropHandlers {
	onDragOver: () => void;
	onDrop: (paths: string[]) => void;
	onLeave: () => void;
}

// Tauri native drag-drop — required for file drops on macOS WKWebView.
// Returns an unlisten function, or undefined when not running inside Tauri
// (e.g. Vite dev in a browser) — the caller's HTML5 drop handlers cover that case.
export async function subscribeTauriDragDrop(handlers: DragDropHandlers): Promise<(() => void) | undefined> {
	const w = await getWindow();
	if (!w) return undefined;
	return w.onDragDropEvent((event) => {
		const p = event.payload;
		if (p.type === 'enter' || p.type === 'over') {
			handlers.onDragOver();
		} else if (p.type === 'drop') {
			handlers.onDrop(p.paths);
		} else {
			handlers.onLeave();
		}
	});
}

export interface RunAgentParams {
	prompt: string;
	directory?: string;
	add_dirs?: string[];
	agent_type?: string;
	mode?: string;
	space_id?: string;
	files?: string[];
}

export function runAgent(params: RunAgentParams) {
	return engineApi.runAgent(params);
}
