<script lang="ts">
	import { api } from '$lib/api';
	import Field from '$lib/components/Field.svelte';
	import Money from '$lib/components/Money.svelte';
	import { plainDate, timeAgo } from '$lib/format';
	import type { InsightsResponse, Lesson, Pipeline } from '$lib/types';
	import { onMount } from 'svelte';

	let pipelines = $state<Pipeline[]>([]);
	let selectedRecipe = $state('');
	let insights = $state<InsightsResponse | null>(null);
	let loading = $state(true);
	let unavailable = $state('');
	let notice = $state('');
	let actionError = $state('');
	let busyLessonId = $state<number | null>(null);

	function recipeName(pipelineId: number): string {
		return pipelines.find((pipeline) => pipeline.id === pipelineId)?.name ?? 'A recipe';
	}

	async function loadInsights() {
		loading = true;
		const path = selectedRecipe
			? `/insights?pipeline_id=${encodeURIComponent(selectedRecipe)}`
			: '/insights';
		try {
			const data = await api.get<InsightsResponse>(path);
			insights = { lessons: data.lessons ?? [], videos: data.videos ?? [] };
			unavailable = '';
		} catch {
			insights = null;
			unavailable =
				'Lessons could not be loaded just now. They appear here once videos have been published and their viewer numbers studied, and from notes you leave on videos.';
		} finally {
			loading = false;
		}
	}

	async function setActive(lesson: Lesson, active: boolean) {
		if (busyLessonId !== null) return;
		busyLessonId = lesson.id;
		actionError = '';
		notice = '';
		try {
			await api.put(`/lessons/${lesson.id}`, { active });
			notice = active
				? 'That lesson is in use again.'
				: 'That lesson is switched off and will not be read when planning.';
			await loadInsights();
		} catch (caught) {
			actionError =
				caught instanceof Error
					? caught.message
					: 'That lesson could not be changed just now. Try again in a moment.';
		} finally {
			busyLessonId = null;
		}
	}

	async function deleteLesson(lesson: Lesson) {
		if (busyLessonId !== null) return;
		if (!confirm('Delete this lesson for good?')) return;
		busyLessonId = lesson.id;
		actionError = '';
		notice = '';
		try {
			await api.del(`/lessons/${lesson.id}`);
			notice = 'That lesson has been deleted.';
			await loadInsights();
		} catch (caught) {
			actionError =
				caught instanceof Error
					? caught.message
					: 'That lesson could not be deleted just now. Try again in a moment.';
		} finally {
			busyLessonId = null;
		}
	}

	$effect(() => {
		void selectedRecipe;
		void loadInsights();
	});

	onMount(() => {
		void api
			.get<Pipeline[]>('/pipelines')
			.then((loaded) => (pipelines = loaded))
			.catch(() => {});
	});
</script>

<div class="container stack">
	<div>
		<h1>Lessons</h1>
		<p class="lede">
			Short sentences Shortsmith has learned — from your words and from viewer numbers. They are
			read every time a new video is planned.
		</p>
	</div>

	<section class="card">
		<Field
			label="Show one recipe"
			help="Lessons belong to a recipe and shape its future videos. Choose “All recipes” to see everything together."
			inputId="insights-recipe"
		>
			<select id="insights-recipe" bind:value={selectedRecipe}>
				<option value="">All recipes</option>
				{#each pipelines as pipeline (pipeline.id)}
					<option value={String(pipeline.id)}>{pipeline.name}</option>
				{/each}
			</select>
		</Field>
	</section>

	{#if notice}
		<div class="notice"><p>{notice}</p></div>
	{/if}
	{#if actionError}
		<div class="error-box"><p>{actionError}</p></div>
	{/if}
	{#if loading}
		<p class="muted">Loading…</p>
	{/if}
	{#if unavailable}
		<div class="card"><p>{unavailable}</p></div>
	{/if}

	{#if insights}
		<section id="lessons" class="stack">
			<h2>What has been learned</h2>
			{#if insights.lessons.length === 0}
				<div class="card">
					<p>
						No lessons yet. Leave a note on a video — your exact words become a lesson straight
						away. Lessons from viewer numbers appear once published videos are a few days old.
					</p>
				</div>
			{:else}
				{#each insights.lessons as lesson (lesson.id)}
					<article class="card stack">
						<p class="lesson-text">“{lesson.text}”</p>
						<p class="muted small">
							{lesson.source === 'you' ? 'From your words' : 'From viewer numbers'} ·
							{recipeName(lesson.pipeline_id)} · learned {timeAgo(lesson.created_at)} ·
							{lesson.active ? 'in use' : 'switched off'}
						</p>
						<p class="row">
							{#if lesson.active}
								<button
									class="btn btn-small"
									disabled={busyLessonId !== null}
									onclick={() => setActive(lesson, false)}
								>
									Switch off
								</button>
							{:else}
								<button
									class="btn btn-small"
									disabled={busyLessonId !== null}
									onclick={() => setActive(lesson, true)}
								>
									Switch on
								</button>
							{/if}
							<button
								class="btn btn-small btn-danger"
								disabled={busyLessonId !== null}
								onclick={() => deleteLesson(lesson)}
							>
								Delete
							</button>
						</p>
					</article>
				{/each}
				<p class="muted small">At most ten lessons are in use for each recipe at a time.</p>
			{/if}
		</section>

		<section id="performance" class="stack">
			<h2>How published videos did</h2>
			{#if insights.videos.length === 0}
				<div class="card">
					<p>
						No published videos to measure yet. Numbers are collected after 1 hour, 6 hours, a
						day, two days, three days, a week and four weeks.
					</p>
				</div>
			{:else}
				<div class="table-scroll card">
					<table class="data">
						<thead>
							<tr>
								<th>Video</th>
								<th>Published</th>
								<th>Views</th>
								<th>Likes</th>
								<th>Comments</th>
								<th>How much watched</th>
								<th>Cost</th>
							</tr>
						</thead>
						<tbody>
							{#each insights.videos as row (row.id)}
								<tr>
									<td><a href="/videos/{row.id}">{row.title || `Video ${row.id}`}</a></td>
									<td>{row.published_at ? plainDate(row.published_at) : '—'}</td>
									<td>{row.views}</td>
									<td>{row.likes}</td>
									<td>{row.comments}</td>
									<td>
										{row.avg_view_percent !== null
											? `${Math.round(row.avg_view_percent)}% on average`
											: 'Not yet known'}
									</td>
									<td><Money usd={row.cost_usd} /></td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				<p class="muted small">
					“How much watched” takes two to three days to appear, because YouTube works it out
					slowly.
				</p>
			{/if}
		</section>
	{/if}
</div>

<style>
	.lesson-text {
		font-size: 1.1rem;
		font-weight: 600;
		margin: 0;
	}
</style>
