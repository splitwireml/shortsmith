<script lang="ts">
	import Money from './Money.svelte';

	type Item = { id: string; label: string; usd: number; href?: string; note?: string };

	let { items, emptyText = 'Nothing to show yet.' }: { items: Item[]; emptyText?: string } =
		$props();

	const max = $derived(Math.max(0, ...items.map((item) => item.usd)));
</script>

{#if items.length === 0}
	<p class="muted">{emptyText}</p>
{:else}
	<div class="stack">
		{#each items as item (item.id)}
			<div>
				<div class="bar-row">
					<span class="bar-label">
						{#if item.href}<a href={item.href}>{item.label}</a>{:else}{item.label}{/if}
					</span>
					<span class="bar-track">
						<span
							class="bar-fill"
							style="display: block; width: {max > 0 && item.usd > 0
								? Math.max(2, (item.usd / max) * 100)
								: 0}%"
						></span>
					</span>
					<strong><Money usd={item.usd} /></strong>
				</div>
				{#if item.note}
					<p class="muted small bar-note">{item.note}</p>
				{/if}
			</div>
		{/each}
	</div>
{/if}

<style>
	.bar-row {
		display: flex;
		align-items: center;
		gap: 0.7rem;
	}

	.bar-label {
		min-width: 8rem;
		max-width: 16rem;
		flex: 0 1 12rem;
	}

	.bar-note {
		margin: 0.2rem 0 0;
	}
</style>
