<script lang="ts">
	import type { Snippet } from 'svelte';

	type Props = {
		label: string;
		help: string;
		id?: string;
		inputId?: string;
		children: Snippet;
	};

	let { label, help, id, inputId, children }: Props = $props();
	let showHelp = $state(false);
</script>

<div class="field" {id}>
	<div class="field-head">
		{#if inputId}
			<label for={inputId}>{label}</label>
		{:else}
			<span class="label-text">{label}</span>
		{/if}
		<button
			type="button"
			class="linklike"
			aria-expanded={showHelp}
			onclick={() => (showHelp = !showHelp)}>What is this?</button
		>
	</div>
	{#if showHelp}
		<p class="field-help">{help}</p>
	{/if}
	{@render children()}
</div>

<style>
	.field {
		margin-bottom: 1rem;
	}

	.field-head {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem 0.8rem;
		align-items: baseline;
		margin-bottom: 0.3rem;
	}

	label,
	.label-text {
		font-weight: 700;
	}

	.field-help {
		background: var(--wash);
		border: 1px solid var(--line);
		border-radius: 8px;
		padding: 0.55rem 0.75rem;
		max-width: 34rem;
	}
</style>
