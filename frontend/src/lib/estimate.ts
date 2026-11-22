// The recipe form's live estimate comes from the server, priced with
// the same table as the pre-spend budget check. The browser keeps no
// prices of its own.

import { api } from './api';

export interface CostEstimate {
	per_video_usd: number;
	per_month_usd: number;
}

export function fetchEstimate(
	seconds: number,
	everyDays: number,
	videosPerRun: number
): Promise<CostEstimate> {
	const params = new URLSearchParams({
		seconds: String(seconds),
		every_days: String(everyDays),
		videos_per_run: String(videosPerRun)
	});
	return api.get<CostEstimate>(`/costs/estimate?${params.toString()}`);
}
