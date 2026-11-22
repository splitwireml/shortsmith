<script lang="ts">
	// Read-only: the quality check's score, summary and flagged clips.
	import type { VideoDetail } from '$lib/types';

	let { video }: { video: VideoDetail } = $props();
</script>

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
			<p class="muted small">
				A flagged clip is made again once, then the video is checked a final time.
			</p>
		{/if}
	{:else}
		<p class="muted">Not checked yet. The finished video is watched and scored out of 10.</p>
	{/if}
</section>

<style>
	.score {
		font-size: 1.4rem;
	}
</style>
