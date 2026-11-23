// Shapes that come back from the server. The backend table classes
// are the source of truth; these mirror them for the browser.

export type ApprovalMode = 'manual' | 'auto';
export type Visibility = 'private' | 'unlisted' | 'public';
export type VideoStatus =
	| 'queued'
	| 'generating'
	| 'reviewing'
	| 'awaiting_approval'
	| 'approved'
	| 'publishing'
	| 'published'
	| 'rejected'
	| 'failed'
	| 'archived';

export interface PipelineInput {
	name: string;
	niche: string;
	objective: string;
	audience: string;
	region_notes: string;
	genre: string;
	art_style: string;
	target_seconds: number;
	every_days: number;
	videos_per_run: number;
	approval_mode: ApprovalMode;
	auto_approve_score: number;
	visibility: Visibility;
	extra_notes: string;
	video_resolution: VideoResolution;
	clip_seconds: number;
	clip_buffer_pct: number;
}

export type VideoResolution = '360p' | '720p' | '1080p' | '4k';

export interface Pipeline extends PipelineInput {
	id: number;
	created_at: string;
	active: boolean;
	last_run_at: string | null;
}

export interface Settings {
	id: number | null;
	created_at: string;
	monthly_budget_usd: number;
	per_video_cap_usd: number;
	retention_days: number;
	max_storage_gb: number;
	practice_mode: boolean;
	onboarding_done: boolean;
	planner_model: string;
	planner_effort: string;
	reviewer_model: string;
	reviewer_effort: string;
	analyst_model: string;
	analyst_effort: string;
	helper_model: string;
	helper_effort: string;
	video_model: string;
	image_model: string;
}

export interface SystemCheck {
	name: string;
	ok: boolean;
	message: string;
}

export interface StatusResponse {
	checks: SystemCheck[];
	onboarding_done: boolean;
	practice_mode: boolean;
}

export interface VideoPlan {
	title?: string;
	hook?: string;
	description?: string;
	tags?: string[];
	style_bible?: string;
	thumbnail_prompt?: string;
	scenes?: { prompt?: string; seconds?: number; narration?: string }[];
}

export interface VideoReview {
	score?: number;
	summary?: string;
	bad_clips?: { index?: number; problem?: string; better_prompt?: string }[];
}

export interface Video {
	id: number;
	created_at: string;
	pipeline_id: number;
	status: VideoStatus;
	is_test: boolean;
	title: string;
	plan: VideoPlan | null;
	review: VideoReview | null;
	review_rounds: number;
	error: string | null;
	failed_status: VideoStatus | null;
	youtube_id: string | null;
	published_at: string | null;
	rating: number;
	media_deleted_at: string | null;
}

export interface Clip {
	id: number;
	created_at: string;
	video_id: number;
	index: number;
	prompt: string;
	seconds: number;
	storage_key: string | null;
}

export interface CostEvent {
	id: number;
	created_at: string;
	pipeline_id: number | null;
	video_id: number | null;
	stage: string;
	model: string;
	input_tokens: number;
	output_tokens: number;
	units: number;
	unit_kind: string;
	cost_usd: number;
	reason: string;
}

export interface Snapshot {
	id: number;
	created_at: string;
	video_id: number;
	checkpoint_hours: number;
	views: number;
	likes: number;
	comments: number;
	avg_view_seconds: number | null;
	avg_view_percent: number | null;
	shares: number | null;
	subscribers_gained: number | null;
}

export interface VideoDetail extends Video {
	clips: Clip[];
	cost_events: CostEvent[];
	snapshots: Snapshot[];
}

export interface CostsSummary {
	total_usd: number;
	by_stage: Record<string, number>;
	by_pipeline: { pipeline_id: number | null; name: string | null; usd: number }[];
	by_day: { day: string; usd: number }[];
	by_video: { video_id: number; title: string | null; usd: number }[];
	cost_per_view: number | null;
	month: { spent_usd: number; budget_usd: number; projected_usd: number };
}

export interface Lesson {
	id: number;
	created_at: string;
	pipeline_id: number;
	video_id: number | null;
	text: string;
	source: 'analytics' | 'you' | string;
	active: boolean;
}

export interface InsightVideo {
	id: number;
	title: string;
	published_at: string | null;
	views: number;
	likes: number;
	comments: number;
	avg_view_percent: number | null;
	cost_usd: number;
}

export interface InsightsResponse {
	lessons: Lesson[];
	videos: InsightVideo[];
}

export interface YoutubeStatus {
	connected: boolean;
	channel_title: string | null;
	needs_reconnect: boolean;
}
