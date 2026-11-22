<script lang="ts">
	// Read-only: the plan a video was made from, with each scene's
	// clip progress shown beside the scene itself.
	import type { VideoDetail } from '$lib/types';

	let { video }: { video: VideoDetail } = $props();

	function clipState(index: number): string {
		const clip = video.clips.find((candidate) => candidate.index === index);
		if (!clip) return '';
		return clip.storage_key ? ' · clip made' : ' · clip still to make';
	}
</script>

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
							({scene.seconds} seconds){/if}: {scene.prompt ?? ''}<span class="muted"
							>{clipState(index)}</span
						>
						{#if scene.narration}<br /><span class="muted">Says: “{scene.narration}”</span>{/if}
					</li>
				{/each}
			</ol>
		{:else if video.clips.length > 0}
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
	{:else}
		<p class="muted">No plan yet. The plan is written as the first step.</p>
	{/if}
</section>

<style>
	.scene-list {
		margin: 0;
		padding-left: 1.4rem;
	}
</style>
