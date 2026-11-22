<script lang="ts">
	import { api } from '$lib/api';
	import BarList from '$lib/components/BarList.svelte';
	import Money from '$lib/components/Money.svelte';
	import { plainDate } from '$lib/format';
	import { practiceState, refreshPractice } from '$lib/practice.svelte';
	import { STAGE_WHY, stageLabel } from '$lib/status';
	import type { CostsSummary, Video } from '$lib/types';
	import { onMount } from 'svelte';

	let summary = $state<CostsSummary | null>(null);
	let videosById = $state<Map<number, Video>>(new Map());
	let loading = $state(true);
	let error = $state('');

	const monthPercent = $derived(
		summary && summary.month.budget_usd > 0
			? Math.min(100, (summary.month.spent_usd / summary.month.budget_usd) * 100)
			: 0
	);
	const stageItems = $derived(
		summary
			? Object.entries(summary.by_stage)
					.map(([stage, usd]) => ({
						id: stage,
						label: stageLabel(stage),
						usd,
						note: STAGE_WHY[stage]
					}))
					.sort((a, b) => b.usd - a.usd)
			: []
	);
	const pipelineItems = $derived(
		summary
			? summary.by_pipeline
					.map((row) => ({
						id: `pipeline-${row.pipeline_id ?? 'none'}`,
						label: row.name ?? 'No particular recipe',
						usd: row.usd,
						href: row.pipeline_id !== null ? `/pipelines/${row.pipeline_id}` : undefined
					}))
					.sort((a, b) => b.usd - a.usd)
			: []
	);
	const dayItems = $derived(
		summary
			? summary.by_day.map((row) => ({ id: row.day, label: plainDate(row.day), usd: row.usd }))
			: []
	);
	const videoItems = $derived(
		summary
			? [...summary.by_video]
					.sort((a, b) => b.usd - a.usd)
					.map((row) => {
						// Titles repeat, so say which video this is: when it
						// started, and whether it was a test video.
						const video = videosById.get(row.video_id);
						const bits = [row.title || `Video ${row.video_id}`];
						if (video) bits.push(plainDate(video.created_at));
						if (video?.is_test) bits.push('Test video');
						return {
							id: `video-${row.video_id}`,
							label: bits.join(' · '),
							usd: row.usd,
							href: `/videos/${row.video_id}`
						};
					})
			: []
	);

	async function load() {
		loading = true;
		try {
			summary = await api.get<CostsSummary>('/costs/summary');
			error = '';
			try {
				const videos = await api.get<Video[]>('/videos');
				videosById = new Map(videos.map((video) => [video.id, video]));
			} catch {
				videosById = new Map();
			}
		} catch (caught) {
			error =
				caught instanceof Error ? caught.message : 'Spending could not be loaded. Try again.';
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		void refreshPractice();
		void load();
	});
</script>

<div class="container stack">
	<div>
		<h1>Money spent</h1>
		<p class="lede">Every paid step is written down. This is the whole story of the money.</p>
	</div>

	{#if loading}
		<p class="muted">Loading…</p>
	{/if}
	{#if error}
		<div class="error-box">
			<p>{error}</p>
			<p><button class="btn btn-small" onclick={load}>Try again</button></p>
		</div>
	{/if}

	{#if summary}
		<section class="card stack" id="costs-month">
			<h2>This month</h2>
			<p>
				<strong class="big-money"><Money usd={summary.month.spent_usd} /></strong> spent of your
				<Money usd={summary.month.budget_usd} /> monthly budget.
			</p>
			<div class="bar-track">
				<div class="bar-fill" style="width: {monthPercent}%"></div>
			</div>
			<p>
				If spending carries on at this pace, the month will end at about
				<strong><Money usd={summary.month.projected_usd} /></strong>.
			</p>
			<p>
				Cost per view:
				{#if summary.cost_per_view !== null}
					<strong><Money usd={summary.cost_per_view} /></strong> for each view of a published video.
				{:else}
					not known yet — it appears once published videos have viewer numbers.
				{/if}
			</p>
			<p><a href="/settings">Change your budget in Settings</a></p>
		</section>

		<section class="card stack" id="costs-by-stage">
			<h2>Where the money goes, by step</h2>
			{#if practiceState.on}
				<p>
					Practice mode is on: making clips and the thumbnail picture are free, so those steps
					show $0.00. Writing the plan and checking quality can still cost a few cents.
				</p>
			{/if}
			<BarList items={stageItems} emptyText="Nothing has been spent yet." />
		</section>

		<section class="card stack" id="costs-by-recipe">
			<h2>By recipe</h2>
			<BarList items={pipelineItems} emptyText="Nothing has been spent yet." />
			<p class="muted small">
				“No particular recipe” covers things like help answers, which belong to no recipe.
			</p>
		</section>

		<section class="card stack">
			<h2>By day</h2>
			<BarList items={dayItems} emptyText="Nothing has been spent yet." />
		</section>

		<section class="card stack">
			<h2>Cost per video</h2>
			<BarList items={videoItems} emptyText="No video has cost anything yet." />
			<p class="muted small">Open a video to see every line that made up its total.</p>
		</section>
	{/if}
</div>

<style>
	.big-money {
		font-size: 1.5rem;
	}
</style>
