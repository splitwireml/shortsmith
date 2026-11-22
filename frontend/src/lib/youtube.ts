// Connecting YouTube starts the Google sign-in in the background;
// callers press Connect, then wait here until it lands.

import { api } from './api';
import type { YoutubeStatus } from './types';

export async function waitForYoutube(): Promise<YoutubeStatus | null> {
	let latest: YoutubeStatus | null = null;
	for (let attempt = 0; attempt < 15; attempt++) {
		await new Promise((resolve) => setTimeout(resolve, 2000));
		try {
			latest = await api.get<YoutubeStatus>('/youtube/status');
		} catch {
			return latest;
		}
		if (latest.connected && !latest.needs_reconnect) return latest;
	}
	return latest;
}
