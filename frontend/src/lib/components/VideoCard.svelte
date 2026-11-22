<script lang="ts">
	import { timeAgo } from '$lib/format';
	import type { Video } from '$lib/types';
	import StatusBadge from './StatusBadge.svelte';

	let { video, recipeName }: { video: Video; recipeName?: string } = $props();
</script>

<article class="card">
	<div class="row-between">
		<h3>
			<a href="/videos/{video.id}">{video.title || 'A new video'}</a>
		</h3>
		<StatusBadge status={video.status} youtubeId={video.youtube_id} />
	</div>
	<p class="muted small">
		{#if recipeName}{recipeName} · {/if}started {timeAgo(video.created_at)}
		{#if video.is_test} · <span class="badge badge-needs">Test video</span>{/if}
	</p>
	{#if video.plan?.hook}
		<p>{video.plan.hook}</p>
	{/if}
	<p><a class="btn btn-small" href="/videos/{video.id}">Open this video</a></p>
</article>
