<script lang="ts">
	// Read-only: the viewer numbers collected after publishing.
	import type { VideoDetail } from '$lib/types';

	let { video }: { video: VideoDetail } = $props();

	function checkpointWords(hours: number): string {
		if (hours === 1) return '1 hour later';
		if (hours < 24) return `${hours} hours later`;
		if (hours === 24) return '1 day later';
		if (hours === 168) return '1 week later';
		if (hours === 672) return '4 weeks later';
		return `${Math.round(hours / 24)} days later`;
	}
</script>

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
