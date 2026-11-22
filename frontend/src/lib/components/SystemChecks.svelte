<script lang="ts">
	import type { SystemCheck } from '$lib/types';

	let { checks }: { checks: SystemCheck[] } = $props();

	const labels: Record<string, string> = {
		gemini: 'Key for making videos',
		youtube: 'YouTube connection',
		ffmpeg: 'Clip-joining tool',
		disk: 'Space on this laptop'
	};
</script>

<div class="stack">
	{#each checks as check (check.name)}
		<p class="check-row">
			<span class="badge {check.ok ? 'badge-ok' : 'badge-bad'}">
				{check.ok ? '✓ Working' : 'Needs attention'}
			</span>
			<span><strong>{labels[check.name] ?? check.name}.</strong> {check.message}</span>
		</p>
	{/each}
</div>

<style>
	.check-row {
		display: flex;
		gap: 0.7rem;
		align-items: flex-start;
		margin: 0;
	}
</style>
