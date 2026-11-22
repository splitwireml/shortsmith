// The one practice-mode value the whole app reads. The layout banner,
// the video page wording and the settings writers all share it, so a
// successful save updates the banner without waiting for a page change.
// A failed refresh keeps the last confirmed value.

import { api } from './api';
import type { StatusResponse } from './types';

export const practiceState = $state({ on: false, known: false });

export function setPractice(on: boolean) {
	practiceState.on = on;
	practiceState.known = true;
}

export async function refreshPractice() {
	try {
		const status = await api.get<StatusResponse>('/status');
		setPractice(status.practice_mode);
	} catch {
		// Keep the last confirmed value; pages report real problems themselves.
	}
}
