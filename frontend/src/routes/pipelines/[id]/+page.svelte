<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '$lib/api';
	import Field from '$lib/components/Field.svelte';
	import Money from '$lib/components/Money.svelte';
	import PipelineForm from '$lib/components/PipelineForm.svelte';
	import VideoCard from '$lib/components/VideoCard.svelte';
	import { fetchEstimate, type CostEstimate } from '$lib/estimate';
	import type { Pipeline, PipelineInput, Video } from '$lib/types';
	import { onMount } from 'svelte';

	const pipelineId = $derived(page.params.id ?? '');

	let pipeline = $state<Pipeline | null>(null);
	let videos = $state<Video[]>([]);
	let formData = $state<PipelineInput | null>(null);
	let scheduleEstimate = $state<CostEstimate | null>(null);
	let loading = $state(true);
	let loadError = $state('');
	let notice = $state('');
	let actionError = $state('');
	let saveError = $state('');
	let saving = $state(false);
	let busyAction = $state('');
	let testCount = $state('1');

	function inputOf(source: Pipeline): PipelineInput {
		return {
			name: source.name,
			niche: source.niche,
			objective: source.objective,
			audience: source.audience,
			region_notes: source.region_notes,
			genre: source.genre,
			art_style: source.art_style,
			target_seconds: source.target_seconds,
			every_days: source.every_days,
			videos_per_run: source.videos_per_run,
			approval_mode: source.approval_mode,
			auto_approve_score: source.auto_approve_score,
			visibility: source.visibility,
			extra_notes: source.extra_notes
		};
	}

	async function load(silent = false) {
		if (!pipelineId) return;
		if (!silent) loading = true;
		try {
			const [nextPipeline, nextVideos] = await Promise.all([
				api.get<Pipeline>(`/pipelines/${pipelineId}`),
				api.get<Video[]>(`/videos?pipeline_id=${encodeURIComponent(pipelineId)}`)
			]);
			pipeline = nextPipeline;
			videos = nextVideos;
			void fetchEstimate(
				nextPipeline.target_seconds,
				nextPipeline.every_days,
				nextPipeline.videos_per_run
			)
				.then((estimate) => (scheduleEstimate = estimate))
				.catch(() => (scheduleEstimate = null));
			// The form is only filled once, so a background refresh never
			// wipes words the person is halfway through changing.
			if (formData === null) formData = inputOf(nextPipeline);
			loadError = '';
		} catch (caught) {
			if (!silent) {
				loadError =
					caught instanceof Error ? caught.message : 'This recipe could not be loaded. Try again.';
			}
		} finally {
			loading = false;
		}
	}

	async function run(count: number, isTest: boolean, action: string) {
		if (busyAction) return;
		busyAction = action;
		actionError = '';
		notice = '';
		try {
			await api.post<Video[]>(`/pipelines/${pipelineId}/run`, { count, is_test: isTest });
			notice = isTest
				? `${count} test ${count === 1 ? 'video has' : 'videos have'} been started. Test videos never publish until you approve them.`
				: 'Your video has been started. Watch its progress under “Videos from this recipe”.';
			await load(true);
		} catch (caught) {
			actionError =
				caught instanceof Error ? caught.message : 'The video could not be started. Try again.';
		} finally {
			busyAction = '';
		}
	}

	async function setActive(active: boolean) {
		if (!pipeline || busyAction) return;
		busyAction = 'pause';
		actionError = '';
		notice = '';
		try {
			pipeline = await api.put<Pipeline>(`/pipelines/${pipelineId}`, {
				...inputOf(pipeline),
				active
			});
			notice = pipeline.active
				? 'The schedule is running. New videos will start on their own at this pace.'
				: 'This recipe is paused. It will not start new videos on its own.';
		} catch (caught) {
			actionError =
				caught instanceof Error ? caught.message : 'That could not be done just now. Try again.';
		} finally {
			busyAction = '';
		}
	}

	async function save() {
		if (!formData || saving) return;
		saving = true;
		saveError = '';
		notice = '';
		try {
			pipeline = await api.put<Pipeline>(`/pipelines/${pipelineId}`, formData);
			notice = 'Your changes have been saved.';
		} catch (caught) {
			saveError =
				caught instanceof Error ? caught.message : 'Your changes could not be saved. Try again.';
		} finally {
			saving = false;
		}
	}

	async function deleteRecipe() {
		if (!pipeline || busyAction) return;
		if (
			!confirm(
				`Delete the recipe “${pipeline.name}”? Its videos and the money spent on them are kept.`
			)
		) {
			return;
		}
		busyAction = 'delete';
		try {
			await api.del(`/pipelines/${pipelineId}`);
			await goto('/pipelines');
		} catch (caught) {
			actionError =
				caught instanceof Error ? caught.message : 'The recipe could not be deleted. Try again.';
			busyAction = '';
		}
	}

	onMount(() => {
		void load();
		const timer = setInterval(() => void load(true), 5000);
		return () => clearInterval(timer);
	});
</script>

<div class="container stack">
	<p><a href="/pipelines">← All recipes</a></p>

	{#if loading}
		<p class="muted">Loading…</p>
	{/if}
	{#if loadError}
		<div class="error-box">
			<p>{loadError}</p>
			<p><a class="btn btn-small" href="/pipelines">Back to all recipes</a></p>
		</div>
	{/if}
	{#if notice}
		<div class="notice"><p>{notice}</p></div>
	{/if}
	{#if actionError}
		<div class="error-box"><p>{actionError}</p></div>
	{/if}

	{#if pipeline}
		<div class="row-between">
			<div>
				<h1>{pipeline.name}</h1>
				<p class="lede">{pipeline.niche}</p>
			</div>
			<span class="badge {pipeline.active ? 'badge-ok' : ''}">
				{pipeline.active
					? 'Running on schedule'
					: pipeline.last_run_at
						? 'Paused'
						: 'Schedule not started'}
			</span>
		</div>

		<section class="card stack" id="schedule">
			<h2>{pipeline.active ? 'Schedule' : 'Start the schedule when you are ready'}</h2>
			<p>
				At this pace Shortsmith makes {pipeline.videos_per_run}
				{pipeline.videos_per_run === 1 ? 'video' : 'videos'} every {pipeline.every_days}
				{pipeline.every_days === 1 ? 'day' : 'days'} on its own{#if scheduleEstimate},
					about <strong><Money usd={scheduleEstimate.per_month_usd} /> a month</strong> in clips
					and thumbnails with practice mode off (planning and checking add a few cents a
					video){/if}.
			</p>
			{#if pipeline.active}
				<p class="row">
					<button
						class="btn"
						id="pause-recipe"
						disabled={busyAction !== ''}
						onclick={() => setActive(false)}
					>
						{busyAction === 'pause' ? 'Pausing…' : 'Pause this recipe'}
					</button>
					<span class="muted small">Pausing stops new videos starting on their own.</span>
				</p>
			{:else}
				<p class="muted">
					This recipe is paused, so saving it has spent nothing. Making a video by hand below
					works while paused.
				</p>
				<p>
					<button
						class="btn"
						id="start-schedule"
						disabled={busyAction !== ''}
						onclick={() => setActive(true)}
					>
						{busyAction === 'pause' ? 'Starting…' : 'Start the schedule'}
					</button>
				</p>
			{/if}
		</section>

		<section class="card stack">
			<h2>Make videos from this recipe</h2>
			<p>
				<button
					class="btn btn-primary"
					id="make-video-now"
					disabled={busyAction !== ''}
					onclick={() => run(1, false, 'run')}
				>
					{busyAction === 'run' ? 'Starting…' : 'Make a video now'}
				</button>
			</p>
			<div id="make-test-batch" class="stack">
				<Field
					label="Make a test batch"
					help="Starts one to three test videos from this recipe. Test videos never publish until you approve them yourself, even if this recipe usually publishes on its own."
					inputId="input-test-count"
				>
					<select id="input-test-count" bind:value={testCount}>
						<option value="1">1 test video</option>
						<option value="2">2 test videos</option>
						<option value="3">3 test videos</option>
					</select>
				</Field>
				<p>
					<button
						class="btn"
						disabled={busyAction !== ''}
						onclick={() => run(Number(testCount), true, 'test')}
					>
						{busyAction === 'test' ? 'Starting…' : 'Make a test batch'}
					</button>
				</p>
			</div>
		</section>

		<section>
			<h2>Videos from this recipe</h2>
			{#if videos.length === 0}
				<div class="card">
					<p>No videos yet. Press “Make a video now” above to start the first one.</p>
				</div>
			{:else}
				<div class="stack">
					{#each videos as video (video.id)}
						<VideoCard {video} />
					{/each}
				</div>
			{/if}
		</section>

		<section class="card">
			<h2>Change this recipe</h2>
			{#if saveError}
				<div class="error-box"><p>{saveError}</p></div>
			{/if}
			{#if formData}
				<PipelineForm
					bind:value={formData}
					submitLabel="Save changes"
					busy={saving}
					onSubmit={save}
				/>
			{/if}
		</section>

		<section class="card">
			<h2>Delete this recipe</h2>
			<p class="muted">
				The recipe leaves your list and makes no new videos. Videos already made, and the record
				of money spent on them, are kept.
			</p>
			<p>
				<button
					class="btn btn-danger"
					id="delete-recipe"
					disabled={busyAction !== ''}
					onclick={deleteRecipe}
				>
					{busyAction === 'delete' ? 'Deleting…' : 'Delete this recipe'}
				</button>
			</p>
		</section>
	{/if}
</div>
