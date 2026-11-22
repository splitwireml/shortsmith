<script lang="ts">
	import { formatMoney } from '$lib/format';

	let { usd }: { usd: number } = $props();
</script>

<span>{formatMoney(usd)}</span>
