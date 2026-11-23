<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '$lib/api';
	import Field from '$lib/components/Field.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import VideoCosts from '$lib/components/VideoCosts.svelte';
	import VideoNumbers from '$lib/components/VideoNumbers.svelte';
	import VideoPlan from '$lib/components/VideoPlan.svelte';
	import VideoReview from '$lib/components/VideoReview.svelte';
	import { plainDate, timeAgo } from '$lib/format';
	import { practiceState, refreshPractice } from '$lib/practice.svelte';
	import { statusExplanation } from '$lib/status';
	import type { Pipeline, Video, VideoDetail } from '$lib/types';
	import { onMount } from 'svelte';

	const videoId = $derived(page.params.id ?? '');

	let video = $state<VideoDetail | null>(null);
	let recipeName = $state('');
	let loading = $state(true);
	let loadError = $state('');
	let notice = $state('');
	let actionError = $state('');
	let busy = $state('');
	let rejectReason = $state('');
	let feedbackRating = $state(0);
	let feedbackNote = $state('');
	let feedbackReady = $state(false);
	let playerFailed = $state(false);
	let thumbFailed = $state(false);

	const playerStatuses = [
		'reviewing',
		'awaiting_approval',
		'approved',
		'publishing',
		'published',
		'rejected'
	];

	// A finished file can only exist once stitching finished, so a
	// failure during planning or making clips never asks for one.
	const playable = $derived.by(() => {
		if (!video) return false;
		if (playerStatuses.includes(video.status)) return true;
		return (
			video.status === 'failed' &&
			(video.failed_status === 'reviewing' ||
				video.failed_status === 'approved' ||
				video.failed_status === 'publishing')
		);
	});

	const showPlayer = $derived(
		video !== null && !video.media_deleted_at && playable && !playerFailed
	);

	const practiceUpload = $derived(video?.youtube_id?.startsWith('practice-') ?? false);
	const practiceNow = $derived(practiceState.on);
	const isPracticeVideo = $derived(video?.practice ?? false);
	// Mirrors the publish rule: this video is practice, or practice mode
	// is on now — either way approving never uploads it to YouTube.
	const finishesAsPractice = $derived(isPracticeVideo || practiceNow);
	const explanation = $derived.by(() => {
		if (!video) return '';
		if (practiceUpload) return 'Practice complete. Nothing was uploaded to YouTube.';
		if (finishesAsPractice && (video.status === 'approved' || video.status === 'publishing')) {
			return 'Approved. This finishes without uploading to YouTube.';
		}
		return statusExplanation(video.status);
	});

	async function load(silent = false) {
		if (!videoId) return;
		if (!silent) loading = true;
		try {
			const next = await api.get<VideoDetail>(`/videos/${videoId}`);
			video = next;
			if (!feedbackReady) {
				feedbackRating = next.rating;
				feedbackReady = true;
			}
			loadError = '';
			try {
				const recipe = await api.get<Pipeline>(`/pipelines/${next.pipeline_id}`);
				recipeName = recipe.name;
			} catch {
				recipeName = '';
			}
		} catch (caught) {
			if (!silent) {
				loadError =
					caught instanceof Error ? caught.message : 'This video could not be loaded. Try again.';
			}
		} finally {
			loading = false;
		}
	}

	async function act(action: string, run: () => Promise<unknown>, done: string) {
		if (busy) return;
		busy = action;
		actionError = '';
		notice = '';
		try {
			await run();
			notice = done;
			await load(true);
		} catch (caught) {
			actionError =
				caught instanceof Error ? caught.message : 'That could not be done just now. Try again.';
		} finally {
			busy = '';
		}
	}

	const approve = () =>
		act(
			'approve',
			() => api.post<Video>(`/videos/${videoId}/approve`),
			finishesAsPractice
				? 'Approved. This will finish without uploading to YouTube.'
				: 'Approved. It will be published in a moment.'
		);

	const reject = () =>
		act(
			'reject',
			() =>
				api.post<Video>(`/videos/${videoId}/reject`, {
					reason: rejectReason.trim() || undefined
				}),
			'Rejected. It will not be published.'
		);

	const retry = async () => {
		// A missing file earlier must not hide the player for good:
		// forget both media errors so the browser tries the files afresh
		// once the retried video reaches a playable stage.
		playerFailed = false;
		thumbFailed = false;
		await act(
			'retry',
			() => api.post<Video>(`/videos/${videoId}/retry`),
			'Started again from where it stopped. Work already paid for has been kept.'
		);
		playerFailed = false;
		thumbFailed = false;
	};

	const saveFeedback = () =>
		act(
			'feedback',
			() =>
				api.post<Video>(`/videos/${videoId}/feedback`, {
					rating: feedbackRating,
					note: feedbackNote.trim() || undefined
				}),
			feedbackNote.trim()
				? 'Thank you. Your words have been kept as a lesson for future videos.'
				: 'Thank you. Your mark has been saved.'
		);

	async function deleteVideo() {
		if (!video || busy) return;
		if (!confirm('Delete this video and its files? The record of money spent is kept.')) return;
		busy = 'delete';
		try {
			await api.del(`/videos/${videoId}`);
			await goto('/videos');
		} catch (caught) {
			actionError =
				caught instanceof Error ? caught.message : 'The video could not be deleted. Try again.';
			busy = '';
		}
	}

	onMount(() => {
		void refreshPractice();
		void load();
		const timer = setInterval(() => void load(true), 5000);
		return () => clearInterval(timer);
	});
</script>

<div class="container stack">
	<p><a href="/videos">← All videos</a></p>

	{#if loading}
		<p class="muted">Loading…</p>
	{/if}
	{#if loadError}
		<div class="error-box">
			<p>{loadError}</p>
			<p><a class="btn btn-small" href="/videos">Back to all videos</a></p>
		</div>
	{/if}
	{#if notice}
		<div class="notice"><p>{notice}</p></div>
	{/if}
	{#if actionError}
		<div class="error-box"><p>{actionError}</p></div>
	{/if}

	{#if video}
		<div class="row-between">
			<div>
				<h1>{video.title || 'A new video'}</h1>
				<p class="muted">
					{#if recipeName}From the recipe “{recipeName}” · {/if}started {timeAgo(video.created_at)}
					{#if video.is_test} · <span class="badge badge-needs">Test video</span>{/if}
				</p>
			</div>
			<StatusBadge status={video.status} youtubeId={video.youtube_id} />
		</div>
		<p class="lede">{explanation}</p>

		{#if isPracticeVideo}
			<div class="practice-notice">
				<p>
					<strong>This is a practice video.</strong> Its clips are plain coloured test clips, not
					real footage, and it will never be uploaded to YouTube. To make real videos, turn
					practice mode off in <a href="/settings">Settings</a>.
				</p>
			</div>
		{/if}

		{#if video.status === 'failed' && video.error}
			<section class="card stack">
				<h2>Why it stopped</h2>
				<p>{video.error}</p>
				<p>
					<button class="btn" id="retry-video" disabled={busy !== ''} onclick={retry}>
						{busy === 'retry' ? 'Starting again…' : 'Retry'}
					</button>
				</p>
				<p class="muted small">Finished clips are kept, so retrying never pays for them twice.</p>
			</section>
		{/if}

		<section class="card stack" id="video-player">
			<h2>Watch it</h2>
			{#if video.media_deleted_at}
				<p>
					The video files were cleaned up on {plainDate(video.media_deleted_at)} to save space.
					The written record below is still here.
				</p>
			{:else if showPlayer}
				<!-- Generated Shorts carry no caption track to point at. -->
				<!-- svelte-ignore a11y_media_has_caption -->
				<video
					class="player"
					controls
					src="/api/media/videos/{video.id}/final.mp4"
					poster={thumbFailed ? undefined : `/api/media/videos/${video.id}/thumb.png`}
					onerror={() => (playerFailed = true)}
				>
					Your browser cannot play this video here.
				</video>
				{#if !thumbFailed}
					<img
						class="thumb"
						src="/api/media/videos/{video.id}/thumb.png"
						alt="Thumbnail for this video"
						onerror={() => (thumbFailed = true)}
					/>
					<p class="muted small">The thumbnail picture viewers see first.</p>
				{/if}
			{:else if playerFailed}
				<p>The finished video file is not ready to watch yet.</p>
			{:else}
				<p>The finished video will appear here once the clips have been made and joined together.</p>
			{/if}
			{#if video.youtube_id}
				{#if video.youtube_id.startsWith('practice-')}
					<p>Practice complete. Nothing was uploaded to YouTube.</p>
				{:else}
					<p>
						On YouTube:
						<a
							href="https://www.youtube.com/shorts/{video.youtube_id}"
							target="_blank"
							rel="noreferrer">watch it there</a
						>
						{#if video.published_at} · published {timeAgo(video.published_at)}{/if}
					</p>
				{/if}
			{/if}
		</section>

		{#if video.status === 'awaiting_approval'}
			<section class="card card-primary stack">
				<h2>Your decision</h2>
				<p>
					{isPracticeVideo
						? 'Approving finishes this practice run and nothing is uploaded to YouTube. Reject throws it away.'
						: practiceNow
							? 'Practice mode is on: approving finishes this practice run and nothing is uploaded to YouTube. Reject throws it away.'
							: 'Approve publishes this video. Reject throws it away.'}
				</p>
				<p>
					<button
						class="btn btn-primary"
						id="approve-video"
						disabled={busy !== ''}
						onclick={approve}
					>
						{busy === 'approve'
							? 'Approving…'
							: isPracticeVideo
								? 'Approve practice video'
								: practiceNow
									? 'Approve (nothing uploaded)'
									: 'Approve and publish'}
					</button>
				</p>
				<div id="reject-video" class="stack">
					<Field
						label="Reason for rejecting (you may leave this empty)"
						help="Anything you write here is kept word for word as a lesson and read when the next video from this recipe is planned."
						inputId="input-reject-reason"
					>
						<textarea
							id="input-reject-reason"
							bind:value={rejectReason}
							placeholder="e.g. The opening was too slow"
						></textarea>
					</Field>
					<p>
						<button class="btn btn-danger" disabled={busy !== ''} onclick={reject}>
							{busy === 'reject' ? 'Rejecting…' : 'Reject this video'}
						</button>
					</p>
				</div>
			</section>
		{/if}

		<VideoPlan {video} />

		<VideoReview {video} />

		<section class="card stack" id="video-feedback">
			<h2>What did you think?</h2>
			<p class="row">
				<button
					class="btn {feedbackRating === 1 ? 'btn-primary' : ''}"
					aria-pressed={feedbackRating === 1}
					onclick={() => (feedbackRating = feedbackRating === 1 ? 0 : 1)}
				>
					Thumbs up
				</button>
				<button
					class="btn {feedbackRating === -1 ? 'btn-danger-solid' : ''}"
					aria-pressed={feedbackRating === -1}
					onclick={() => (feedbackRating = feedbackRating === -1 ? 0 : -1)}
				>
					Thumbs down
				</button>
			</p>
			<Field
				label="A note in your own words (you may leave this empty)"
				help="Your exact words become a lesson straight away and are read when future videos from this recipe are planned. Short and plain works best."
				inputId="input-feedback-note"
			>
				<textarea
					id="input-feedback-note"
					bind:value={feedbackNote}
					placeholder="e.g. Too slow to get going"
				></textarea>
			</Field>
			<p>
				<button class="btn" disabled={busy !== ''} onclick={saveFeedback}>
					{busy === 'feedback' ? 'Saving…' : 'Save my feedback'}
				</button>
			</p>
		</section>

		<VideoCosts {video} />

		<VideoNumbers {video} />

		<section class="card">
			<h2>Delete this video</h2>
			<p class="muted">Removes the video and its files. The money record stays.</p>
			<p>
				<button class="btn btn-danger" disabled={busy !== ''} onclick={deleteVideo}>
					{busy === 'delete' ? 'Deleting…' : 'Delete this video'}
				</button>
			</p>
		</section>
	{/if}
</div>

<style>
	.practice-notice {
		background: var(--amber-bg);
		border: 1px solid var(--amber-line);
		border-radius: 10px;
		color: var(--amber-ink);
		padding: 0.75rem 1rem;
	}

	.practice-notice p {
		margin: 0;
	}

	.player {
		width: min(22rem, 100%);
		aspect-ratio: 9 / 16;
		background: #000;
		border-radius: 10px;
	}

	.thumb {
		width: min(11rem, 60%);
		border-radius: 8px;
		border: 1px solid var(--line);
	}

</style>
