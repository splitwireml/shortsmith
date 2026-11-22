// The one practice-mode value the whole app reads. The layout banner,
// the video page wording and the settings writers all share it, so a
// successful save updates the banner without waiting for a page change.
// A failed refresh keeps the last confirmed value. The value comes
// from /settings (a plain database read) — never /status, whose
// health checks include a live Gemini lookup.

import { api } from './api';
import type { Settings } from './types';

export const practiceState = $state({ on: false, known: false });

export function setPractice(on: boolean) {
	practiceState.on = on;
	practiceState.known = true;
}

export async function refreshPractice() {
	try {
		const settings = await api.get<Settings>('/settings');
		setPractice(settings.practice_mode);
	} catch {
		// Keep the last confirmed value; pages report real problems themselves.
	}
}
