<script lang="ts">
	import { api } from '$lib/api';
	import { timeAgo } from '$lib/format';
	import type { Pipeline, Video } from '$lib/types';
	import { onMount } from 'svelte';

	let pipelines = $state<Pipeline[]>([]);
	let loading = $state(true);
	let error = $state('');
	let notice = $state('');
	let busyId = $state<number | null>(null);

	async function load() {
		loading = true;
		try {
			pipelines = await api.get<Pipeline[]>('/pipelines');
			error = '';
		} catch (caught) {
			error =
				caught instanceof Error ? caught.message : 'Your recipes could not be loaded. Try again.';
		} finally {
			loading = false;
		}
	}

	async function makeNow(pipeline: Pipeline) {
		if (busyId !== null) return;
		busyId = pipeline.id;
		notice = '';
		error = '';
		try {
			await api.post<Video[]>(`/pipelines/${pipeline.id}/run`, { count: 1, is_test: false });
			notice = `A new video from “${pipeline.name}” has been started. See it under Videos.`;
		} catch (caught) {
			error =
				caught instanceof Error ? caught.message : 'The video could not be started. Try again.';
		} finally {
			busyId = null;
		}
	}

	onMount(load);
</script>

<div class="container stack">
	<div class="row-between">
		<div>
			<h1>Channel recipes</h1>
			<p class="lede">
				A recipe is your saved instructions for one kind of video. Every video is made from a
				recipe.
			</p>
		</div>
		<a class="btn btn-primary" href="/pipelines/new">Create a new recipe</a>
	</div>

	{#if notice}
		<div class="notice"><p>{notice}</p></div>
	{/if}
	{#if error}
		<div class="error-box">
			<p>{error}</p>
			<p><button class="btn btn-small" onclick={load}>Try again</button></p>
		</div>
	{/if}
	{#if loading}
		<p class="muted">Loading…</p>
	{/if}

	<div id="recipes-list" class="stack">
		{#if !loading && pipelines.length === 0 && !error}
			<section class="card">
				<h2>No recipes yet</h2>
				<p>
					Start from a ready-made recipe like Animals or Facts, describe your idea in one
					sentence, or fill in the form yourself. It takes a couple of minutes.
				</p>
				<p><a class="btn" href="/pipelines/new">Create your first recipe</a></p>
				<p class="muted small">Or follow the <a href="/setup">setup guide</a> step by step.</p>
			</section>
		{/if}

		{#each pipelines as pipeline (pipeline.id)}
			<article class="card">
				<div class="row-between">
					<h2><a href="/pipelines/{pipeline.id}">{pipeline.name}</a></h2>
					<span class="badge {pipeline.active ? 'badge-ok' : ''}">
						{pipeline.active
							? 'Running on schedule'
							: pipeline.last_run_at
								? 'Paused'
								: 'Schedule not started'}
					</span>
				</div>
				<p>{pipeline.niche}</p>
				<p class="muted small">
					{pipeline.videos_per_run}
					{pipeline.videos_per_run === 1 ? 'video' : 'videos'} every {pipeline.every_days}
					{pipeline.every_days === 1 ? 'day' : 'days'} · about {pipeline.target_seconds} seconds
					each ·
					{#if pipeline.last_run_at}
						last started {timeAgo(pipeline.last_run_at)}
					{:else}
						has not made a video yet
					{/if}
				</p>
				{#if !pipeline.active}
					<p class="muted small">
						Saved paused: nothing is scheduled yet. Open the recipe to start its schedule when
						you are ready — making a video by hand works now.
					</p>
				{/if}
				<p class="row">
					<a class="btn btn-small" href="/pipelines/{pipeline.id}">Open recipe</a>
					<button
						class="btn btn-small"
						disabled={busyId !== null}
						onclick={() => makeNow(pipeline)}
					>
						{busyId === pipeline.id ? 'Starting…' : 'Make a video now'}
					</button>
				</p>
			</article>
		{/each}
	</div>
</div>
