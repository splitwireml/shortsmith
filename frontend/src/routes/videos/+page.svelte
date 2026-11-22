<script lang="ts">
	import { api } from '$lib/api';
	import Field from '$lib/components/Field.svelte';
	import VideoCard from '$lib/components/VideoCard.svelte';
	import { statusLabel } from '$lib/status';
	import type { Pipeline, Video, VideoStatus } from '$lib/types';
	import { onMount } from 'svelte';

	let videos = $state<Video[]>([]);
	let pipelines = $state<Pipeline[]>([]);
	let recipeFilter = $state('');
	let stageFilter = $state('');
	let loading = $state(true);
	let error = $state('');

	const stages: VideoStatus[] = [
		'queued',
		'generating',
		'reviewing',
		'awaiting_approval',
		'approved',
		'publishing',
		'published',
		'rejected',
		'failed',
		'archived'
	];

	function recipeName(pipelineId: number): string {
		return pipelines.find((pipeline) => pipeline.id === pipelineId)?.name ?? 'A recipe';
	}

	async function loadVideos(silent = false) {
		if (!silent) loading = true;
		const params = new URLSearchParams();
		if (recipeFilter) params.set('pipeline_id', recipeFilter);
		if (stageFilter) params.set('status', stageFilter);
		const query = params.toString();
		try {
			videos = await api.get<Video[]>(`/videos${query ? `?${query}` : ''}`);
			error = '';
		} catch (caught) {
			if (!silent) {
				error =
					caught instanceof Error ? caught.message : 'Videos could not be loaded. Try again.';
			}
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		void recipeFilter;
		void stageFilter;
		void loadVideos();
	});

	onMount(() => {
		void api
			.get<Pipeline[]>('/pipelines')
			.then((loaded) => (pipelines = loaded))
			.catch(() => {});
		const timer = setInterval(() => void loadVideos(true), 5000);
		return () => clearInterval(timer);
	});
</script>

<div class="container stack">
	<div>
		<h1>Videos</h1>
		<p class="lede">Every video, at whatever step it has reached. Open one to watch it and decide.</p>
	</div>

	<section class="card">
		<div class="grid-2">
			<Field
				label="Show one recipe"
				help="Only show videos made from this recipe. Choose “All recipes” to see everything."
				inputId="filter-recipe"
			>
				<select id="filter-recipe" bind:value={recipeFilter}>
					<option value="">All recipes</option>
					{#each pipelines as pipeline (pipeline.id)}
						<option value={String(pipeline.id)}>{pipeline.name}</option>
					{/each}
				</select>
			</Field>
			<Field
				label="Show one step"
				help="Only show videos at this step, such as “Needs you” for videos waiting for your approval."
				inputId="filter-stage"
			>
				<select id="filter-stage" bind:value={stageFilter}>
					<option value="">All steps</option>
					{#each stages as stage (stage)}
						<option value={stage}>{statusLabel(stage)}</option>
					{/each}
				</select>
			</Field>
		</div>
	</section>

	{#if loading}
		<p class="muted">Loading…</p>
	{/if}
	{#if error}
		<div class="error-box">
			<p>{error}</p>
			<p><button class="btn btn-small" onclick={() => void loadVideos()}>Try again</button></p>
		</div>
	{/if}

	<div id="videos-list" class="stack">
		{#if !loading && videos.length === 0 && !error}
			<section class="card">
				<h2>Nothing to show</h2>
				<p>
					No videos match. Make one from a <a href="/pipelines">recipe</a>, or widen the choices
					above.
				</p>
			</section>
		{/if}
		{#each videos as video (video.id)}
			<VideoCard {video} recipeName={recipeName(video.pipeline_id)} />
		{/each}
	</div>
</div>
