<script lang="ts">
	// Read-only: what this one video cost, by stage and line by line (C4).
	import BarList from '$lib/components/BarList.svelte';
	import Money from '$lib/components/Money.svelte';
	import { timeAgo } from '$lib/format';
	import { stageLabel } from '$lib/status';
	import type { VideoDetail } from '$lib/types';

	let { video }: { video: VideoDetail } = $props();

	const totalCost = $derived(
		video.cost_events.reduce((sum, event) => sum + event.cost_usd, 0)
	);
	const costByStage = $derived.by(() => {
		const totals = new Map<string, number>();
		for (const event of video.cost_events) {
			totals.set(event.stage, (totals.get(event.stage) ?? 0) + event.cost_usd);
		}
		return [...totals.entries()]
			.map(([stage, usd]) => ({ id: stage, label: stageLabel(stage), usd }))
			.sort((a, b) => b.usd - a.usd);
	});
</script>

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
