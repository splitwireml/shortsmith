<script lang="ts">
	import { api } from '$lib/api';
	import Field from '$lib/components/Field.svelte';
	import Money from '$lib/components/Money.svelte';
	import SystemChecks from '$lib/components/SystemChecks.svelte';
	import VideoCard from '$lib/components/VideoCard.svelte';
	import { IN_PROGRESS } from '$lib/status';
	import type { CostsSummary, Pipeline, StatusResponse, Video } from '$lib/types';
	import { onMount } from 'svelte';

	let status = $state<StatusResponse | null>(null);
	let videos = $state<Video[]>([]);
	let pipelines = $state<Pipeline[]>([]);
	let summary = $state<CostsSummary | null>(null);
	let loading = $state(true);
	let error = $state('');
	let makePipelineId = $state('');
	let making = $state(false);
	let makeError = $state('');
	let notice = $state('');

	const needsYou = $derived(videos.filter((video) => video.status === 'awaiting_approval'));
	const inProgress = $derived(videos.filter((video) => IN_PROGRESS.includes(video.status)));
	const monthPercent = $derived(
		summary && summary.month.budget_usd > 0
			? Math.min(100, (summary.month.spent_usd / summary.month.budget_usd) * 100)
			: 0
	);

	function recipeName(pipelineId: number): string {
		return pipelines.find((pipeline) => pipeline.id === pipelineId)?.name ?? 'A recipe';
	}

	// Health (with its live Gemini lookup) is read once on arrival;
	// the video lists below poll on their own every few seconds and
	// never wait for it.
	async function loadHealth() {
		try {
			status = await api.get<StatusResponse>('/status');
		} catch {
			status = null;
		}
	}

	async function load(silent = false) {
		if (!silent) loading = true;
		try {
			const [nextVideos, nextPipelines] = await Promise.all([
				api.get<Video[]>('/videos'),
				api.get<Pipeline[]>('/pipelines')
			]);
			videos = nextVideos;
			pipelines = nextPipelines;
			if (!makePipelineId && nextPipelines.length > 0) {
				makePipelineId = String(nextPipelines[0].id);
			}
			error = '';
		} catch (caught) {
			if (!silent || videos.length === 0) {
				error =
					caught instanceof Error
						? caught.message
						: 'Shortsmith could not be reached. Check that the app is still running, then try again.';
			}
		} finally {
			loading = false;
		}
		try {
			summary = await api.get<CostsSummary>('/costs/summary');
		} catch {
			summary = null;
		}
	}

	async function makeVideo() {
		if (!makePipelineId || making) return;
		making = true;
		makeError = '';
		notice = '';
		try {
			await api.post<Video[]>(`/pipelines/${makePipelineId}/run`, { count: 1, is_test: false });
			notice = 'Your video has been started. It will appear under “Being made now” below.';
			await load(true);
		} catch (caught) {
			makeError =
				caught instanceof Error ? caught.message : 'The video could not be started. Try again.';
		} finally {
			making = false;
		}
	}

	onMount(() => {
		void loadHealth();
		void load();
		const timer = setInterval(() => void load(true), 5000);
		return () => clearInterval(timer);
	});
</script>

<div class="container stack">
	<div>
		<h1>Home</h1>
		<p class="lede">Make a video, check the ones waiting for you, and see what has been spent.</p>
	</div>

	{#if loading}
		<p class="muted">Loading…</p>
	{/if}

	{#if error}
		<div class="error-box">
			<p>{error}</p>
			<p>
				<button
					class="btn btn-small"
					onclick={() => {
						void load();
						void loadHealth();
					}}>Try again</button
				>
			</p>
		</div>
	{/if}

	{#if notice}
		<div class="notice"><p>{notice}</p></div>
	{/if}

	{#if status && !status.onboarding_done}
		<section class="card">
			<h2>New here? Finish setting up</h2>
			<p>
				The setup guide checks everything works, connects YouTube, makes your first recipe and a
				practice video. You can skip any step.
			</p>
			<p><a class="btn" href="/setup">Open the setup guide</a></p>
		</section>
	{/if}

	<section class="card card-primary" id="make-video">
		<h2>Make a video</h2>
		{#if pipelines.length === 0}
			<p>You need a channel recipe first — your saved instructions for one kind of video.</p>
			<p><a class="btn btn-primary" href="/pipelines/new">Create your first recipe</a></p>
		{:else}
			<Field
				label="Which recipe?"
				help="A channel recipe is your saved instructions for one kind of video. The new video follows this recipe."
				inputId="home-recipe"
			>
				<select id="home-recipe" bind:value={makePipelineId}>
					{#each pipelines as pipeline (pipeline.id)}
						<option value={String(pipeline.id)}>{pipeline.name}</option>
					{/each}
				</select>
			</Field>
			{#if makeError}
				<div class="error-box"><p>{makeError}</p></div>
			{/if}
			<p>
				<button class="btn btn-primary" disabled={making} onclick={makeVideo}>
					{making ? 'Starting…' : 'Make a video now'}
				</button>
			</p>
			<p class="muted small">
				Shortsmith plans it, makes the clips and checks it. It then waits for your approval unless
				the recipe says otherwise.
			</p>
		{/if}
	</section>

	<section id="needs-you">
		<h2>Needs you</h2>
		{#if needsYou.length === 0}
			<div class="card">
				<p>Nothing is waiting for you. Finished videos that need your approval will appear here.</p>
			</div>
		{:else}
			<p class="muted">Watch each video, then approve it to publish or reject it.</p>
			<div class="stack">
				{#each needsYou as video (video.id)}
					<VideoCard {video} recipeName={recipeName(video.pipeline_id)} />
				{/each}
			</div>
		{/if}
	</section>

	<section id="system-check">
		<h2>Is everything working?</h2>
		<div class="card stack">
			{#if status}
				<SystemChecks checks={status.checks} />
			{:else if !loading}
				<p class="muted">The checks could not be loaded just now.</p>
			{/if}
		</div>
	</section>

	<section id="in-progress">
		<h2>Being made now</h2>
		{#if inProgress.length === 0}
			<div class="card"><p>No videos are being made right now.</p></div>
		{:else}
			<div class="stack">
				{#each inProgress as video (video.id)}
					<VideoCard {video} recipeName={recipeName(video.pipeline_id)} />
				{/each}
			</div>
		{/if}
	</section>

	<section id="month-spend">
		<h2>Money spent this month</h2>
		<div class="card stack">
			{#if summary}
				<p>
					<strong><Money usd={summary.month.spent_usd} /></strong> of your
					<Money usd={summary.month.budget_usd} /> monthly budget. At this pace the month will end at
					about <Money usd={summary.month.projected_usd} />.
				</p>
				<div class="bar-track">
					<div class="bar-fill" style="width: {monthPercent}%"></div>
				</div>
				<p><a href="/costs">See where the money went</a></p>
			{:else}
				<p class="muted">Spending could not be loaded just now. <a href="/costs">Open Money spent</a></p>
			{/if}
		</div>
	</section>
</div>
