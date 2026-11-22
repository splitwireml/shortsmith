// Plain words for the server's status and stage names.

import type { VideoStatus } from './types';

const LABELS: Record<VideoStatus, string> = {
	queued: 'Planning',
	generating: 'Making clips',
	reviewing: 'Checking quality',
	awaiting_approval: 'Needs you',
	approved: 'Approved',
	publishing: 'Publishing',
	published: 'Published',
	rejected: 'Rejected',
	failed: 'Stopped',
	archived: 'Archived'
};

const EXPLANATIONS: Record<VideoStatus, string> = {
	queued:
		'Waiting to start. This can take about 30 seconds. Then Shortsmith writes the plan: the idea, the words and the scenes.',
	generating: 'The clips and the thumbnail picture are being made and joined together.',
	reviewing: 'The finished video is being watched and scored. A clip that looks wrong is made again once.',
	awaiting_approval: 'Watch the video, then approve it to publish or reject it to throw it away.',
	approved: 'You approved this video. It will be uploaded to YouTube in a moment.',
	publishing: 'The video is being uploaded to YouTube now.',
	published: 'This video is on YouTube. Its viewer numbers are collected over the next few weeks.',
	rejected: 'You rejected this video, so it was not published.',
	failed: 'Something stopped this video. The reason is below, and nothing more will be spent until you press Retry.',
	archived: 'The video files were cleaned up to save space. The notes and money spent are still kept.'
};

export function statusLabel(status: string): string {
	return LABELS[status as VideoStatus] ?? status;
}

export function statusExplanation(status: string): string {
	return EXPLANATIONS[status as VideoStatus] ?? '';
}

export const IN_PROGRESS: VideoStatus[] = [
	'queued',
	'generating',
	'reviewing',
	'approved',
	'publishing'
];

const STAGE_LABELS: Record<string, string> = {
	planning: 'Planning',
	video: 'Making clips',
	thumbnail: 'Thumbnail picture',
	review: 'Checking quality',
	analytics: 'Learning from results',
	help: 'Help answers'
};

export function stageLabel(stage: string): string {
	return STAGE_LABELS[stage] ?? stage;
}

export const STAGE_WHY: Record<string, string> = {
	planning: 'Writing the idea, the title and the scene-by-scene plan. This costs a few cents.',
	video: 'Making the moving clips, charged for every second of video. This is nearly all of the cost.',
	thumbnail: 'Making the still picture viewers see first. A few cents each.',
	review: 'Watching the finished video and scoring it. A few cents.',
	analytics: 'Studying viewer numbers and writing short lessons. A few cents, at most once a day.',
	help: 'Answering your questions in the help drawer. A few cents a question.'
};
