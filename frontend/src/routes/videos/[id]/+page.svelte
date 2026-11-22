<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '$lib/api';
	import BarList from '$lib/components/BarList.svelte';
	import Field from '$lib/components/Field.svelte';
	import Money from '$lib/components/Money.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import { plainDate, timeAgo } from '$lib/format';
	import { practiceState, refreshPractice } from '$lib/practice.svelte';
	import { stageLabel, statusExplanation } from '$lib/status';
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
	const explanation = $derived.by(() => {
		if (!video) return '';
		if (practiceUpload) return 'Practice complete. Nothing was uploaded to YouTube.';
		if (practiceNow && (video.status === 'approved' || video.status === 'publishing')) {
			return 'Approved. In practice mode this finishes without uploading to YouTube.';
		}
		return statusExplanation(video.status);
	});
	const totalCost = $derived(
		video ? video.cost_events.reduce((sum, event) => sum + event.cost_usd, 0) : 0
	);
	const costByStage = $derived.by(() => {
		if (!video) return [];
		const totals = new Map<string, number>();
		for (const event of video.cost_events) {
			totals.set(event.stage, (totals.get(event.stage) ?? 0) + event.cost_usd);
		}
		return [...totals.entries()]
			.map(([stage, usd]) => ({ id: stage, label: stageLabel(stage), usd }))
			.sort((a, b) => b.usd - a.usd);
	});

	function checkpointWords(hours: number): string {
		if (hours === 1) return '1 hour later';
		if (hours < 24) return `${hours} hours later`;
		if (hours === 24) return '1 day later';
		if (hours === 168) return '1 week later';
		if (hours === 672) return '4 weeks later';
		return `${Math.round(hours / 24)} days later`;
	}

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
			practiceNow
				? 'Approved. This practice video will finish without uploading to YouTube.'
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
					{practiceNow
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
							: practiceNow
								? 'Approve practice video'
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

		<section class="card stack">
			<h2>The plan it was made from</h2>
			{#if video.plan}
				{#if video.plan.hook}
					<p><strong>Opening hook:</strong> {video.plan.hook}</p>
				{/if}
				{#if video.plan.description}
					<p><strong>Words for YouTube:</strong> {video.plan.description}</p>
				{/if}
				{#if video.plan.tags && video.plan.tags.length > 0}
					<p><strong>Labels:</strong> {video.plan.tags.join(', ')}</p>
				{/if}
				{#if video.plan.style_bible}
					<p><strong>Look and feel:</strong> {video.plan.style_bible}</p>
				{/if}
				{#if video.plan.thumbnail_prompt}
					<p><strong>Thumbnail idea:</strong> {video.plan.thumbnail_prompt}</p>
				{/if}
				{#if video.plan.scenes && video.plan.scenes.length > 0}
					<h3>Scenes</h3>
					<ol class="scene-list">
						{#each video.plan.scenes as scene, index (index)}
							<li>
								<strong>Scene {index + 1}</strong>{#if scene.seconds}
									({scene.seconds} seconds){/if}: {scene.prompt ?? ''}
								{#if scene.narration}<br /><span class="muted">Says: “{scene.narration}”</span>{/if}
							</li>
						{/each}
					</ol>
				{/if}
			{:else}
				<p class="muted">No plan yet. The plan is written as the first step.</p>
			{/if}
			{#if video.clips.length > 0}
				<h3>Clips</h3>
				<ul>
					{#each video.clips as clip (clip.id)}
						<li>
							Clip {clip.index + 1} — {clip.seconds} seconds —
							{clip.storage_key ? 'made' : 'still to make'}
						</li>
					{/each}
				</ul>
			{/if}
		</section>

		<section class="card stack">
			<h2>Quality check</h2>
			{#if video.review}
				{#if typeof video.review.score === 'number'}
					<p><strong class="score">{video.review.score} out of 10</strong></p>
				{/if}
				{#if video.review.summary}
					<p>{video.review.summary}</p>
				{/if}
				{#if video.review.bad_clips && video.review.bad_clips.length > 0}
					<h3>Clips that were flagged</h3>
					<ul>
						{#each video.review.bad_clips as bad, index (index)}
							<li>Clip {(bad.index ?? index) + 1}: {bad.problem ?? 'something looked wrong'}</li>
						{/each}
					</ul>
					<p class="muted small">A flagged clip is made again once, then the video is checked a final time.</p>
				{/if}
			{:else}
				<p class="muted">Not checked yet. The finished video is watched and scored out of 10.</p>
			{/if}
		</section>

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

		<section class="card stack" id="video-cost">
			<h2>What this video cost</h2>
			<p>
				Total so far: <strong><Money usd={totalCost} /></strong>
			</p>
			<BarList items={costByStage} emptyText="Nothing has been spent on this video yet." />
			{#if video.cost_events.length > 0}
				<div class="table-scroll">
					<table class="data">
						<thead>
							<tr><th>Step</th><th>Why</th><th>When</th><th>Cost</th></tr>
						</thead>
						<tbody>
							{#each video.cost_events as event (event.id)}
								<tr>
									<td>{stageLabel(event.stage)}</td>
									<td>{event.reason || '—'}</td>
									<td>{timeAgo(event.created_at)}</td>
									<td><Money usd={event.cost_usd} /></td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</section>

		{#if video.snapshots.length > 0}
			<section class="card stack">
				<h2>Viewer numbers</h2>
				<div class="table-scroll">
					<table class="data">
						<thead>
							<tr>
								<th>When</th>
								<th>Views</th>
								<th>Likes</th>
								<th>Comments</th>
								<th>How much watched</th>
							</tr>
						</thead>
						<tbody>
							{#each video.snapshots as snapshot (snapshot.id)}
								<tr>
									<td>{checkpointWords(snapshot.checkpoint_hours)}</td>
									<td>{snapshot.views}</td>
									<td>{snapshot.likes}</td>
									<td>{snapshot.comments}</td>
									<td>
										{snapshot.avg_view_percent !== null
											? `${Math.round(snapshot.avg_view_percent)}% on average`
											: 'Not yet known'}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</section>
		{/if}

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

	.score {
		font-size: 1.4rem;
	}

	.scene-list {
		margin: 0;
		padding-left: 1.4rem;
	}
</style>
