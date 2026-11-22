<script lang="ts">
	import { statusLabel } from '$lib/status';

	let { status, youtubeId }: { status: string; youtubeId?: string | null } = $props();

	// A finished practice run was never uploaded, so it is never “Published”.
	const practiceComplete = $derived(
		status === 'published' && (youtubeId?.startsWith('practice-') ?? false)
	);

	const tone = $derived(
		status === 'awaiting_approval'
			? 'badge-needs'
			: status === 'published'
				? 'badge-ok'
				: status === 'failed' || status === 'rejected'
					? 'badge-bad'
					: ['queued', 'generating', 'reviewing', 'approved', 'publishing'].includes(status)
						? 'badge-busy'
						: ''
	);
</script>

<span class="badge {tone}">{practiceComplete ? 'Practice complete' : statusLabel(status)}</span>
