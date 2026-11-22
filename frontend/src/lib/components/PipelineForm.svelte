<script lang="ts">
	import { api } from '$lib/api';
	import { fetchEstimate, type CostEstimate } from '$lib/estimate';
	import type { PipelineInput, Settings } from '$lib/types';
	import { onMount } from 'svelte';
	import Field from './Field.svelte';
	import Money from './Money.svelte';

	type Props = {
		value: PipelineInput;
		formId?: string;
		submitLabel: string;
		busy?: boolean;
		onSubmit: () => void;
	};

	let { value = $bindable(), formId, submitLabel, busy = false, onSubmit }: Props = $props();

	let estimate = $state<CostEstimate | null>(null);
	let estimateFailed = $state(false);
	let monthlyBudget = $state<number | null>(null);
	let estimateRun = 0;

	// Priced by the server with its own price table; refreshed (debounced)
	// whenever the length or pace changes.
	$effect(() => {
		const seconds = Number(value.target_seconds);
		const everyDays = Number(value.every_days);
		const perRun = Number(value.videos_per_run);
		if (!(seconds > 0 && everyDays >= 1 && perRun >= 1)) return;
		const run = ++estimateRun;
		const timer = setTimeout(() => {
			fetchEstimate(seconds, everyDays, perRun)
				.then((next) => {
					if (run !== estimateRun) return;
					estimate = next;
					estimateFailed = false;
				})
				.catch(() => {
					if (run === estimateRun) estimateFailed = true;
				});
		}, 350);
		return () => clearTimeout(timer);
	});

	onMount(() => {
		void api
			.get<Settings>('/settings')
			.then((settings) => (monthlyBudget = settings.monthly_budget_usd))
			.catch(() => {});
	});
</script>

<form
	id={formId}
	onsubmit={(event) => {
		event.preventDefault();
		onSubmit();
	}}
>
	<Field
		label="Recipe name"
		help="A short name so you can tell your recipes apart, such as “Cat facts”. Viewers never see it."
		id="field-name"
		inputId="input-name"
	>
		<input id="input-name" bind:value={value.name} required placeholder="e.g. Cat facts" />
	</Field>

	<Field
		label="What are the videos about?"
		help="The subject in a few words, such as “cute animal moments”. Every idea for this recipe stays on this subject."
		id="field-niche"
		inputId="input-niche"
	>
		<input id="input-niche" bind:value={value.niche} required placeholder="e.g. Cute animal moments" />
	</Field>

	<Field
		label="What should this achieve?"
		help="The aim in one sentence, such as “teach one surprising idea per video”. It keeps every video pulling in the same direction."
		id="field-objective"
		inputId="input-objective"
	>
		<textarea id="input-objective" bind:value={value.objective} required></textarea>
	</Field>

	<Field
		label="Who is it for?"
		help="The people you hope will watch, such as “families with young children”. Wording and pace are shaped to suit them."
		id="field-audience"
		inputId="input-audience"
	>
		<textarea id="input-audience" bind:value={value.audience} required></textarea>
	</Field>

	<Field
		label="Region and language notes"
		help="Anything about place or wording that matters, such as “plain international English” or “give sizes in metric and imperial”. Leave empty if nothing special applies."
		id="field-region-notes"
		inputId="input-region-notes"
	>
		<textarea id="input-region-notes" bind:value={value.region_notes}></textarea>
	</Field>

	<Field
		label="Kind of video and tone"
		help="The style of telling, such as “gentle explainer” or “silly comedy sketch”, and how it should feel: warm, calm, cheeky."
		id="field-genre"
		inputId="input-genre"
	>
		<input id="input-genre" bind:value={value.genre} required placeholder="e.g. Gentle explainer" />
	</Field>

	<Field
		label="How should it look?"
		help="A few words about the pictures, such as “soft friendly cartoon animals in bright colours”. The same look is used in every clip."
		id="field-art-style"
		inputId="input-art-style"
	>
		<textarea id="input-art-style" bind:value={value.art_style} required></textarea>
	</Field>

	<Field
		label="How long should each video be? (seconds, 15–60)"
		help="Between 15 and 60 seconds. Shorter is cheaper; longer fits a fuller story. The estimate below updates as you type."
		id="field-target-seconds"
		inputId="input-target-seconds"
	>
		<input
			id="input-target-seconds"
			type="number"
			min="15"
			max="60"
			step="1"
			required
			bind:value={value.target_seconds}
		/>
	</Field>

	<Field
		label="Make new videos every … days"
		help="How often Shortsmith starts a new batch for this recipe on its own. Every 2 days means about 15 batches a month."
		id="field-every-days"
		inputId="input-every-days"
	>
		<input id="input-every-days" type="number" min="1" step="1" required bind:value={value.every_days} />
	</Field>

	<Field
		label="Videos each time"
		help="How many videos to make in each batch. One is a gentle pace to start with."
		id="field-videos-per-run"
		inputId="input-videos-per-run"
	>
		<input
			id="input-videos-per-run"
			type="number"
			min="1"
			step="1"
			required
			bind:value={value.videos_per_run}
		/>
	</Field>

	<Field
		label="Who says yes before publishing?"
		help="“I check every video myself” means nothing is published until you approve it. “Publish on its own above a score” publishes high-scoring videos without waiting, and the rest still wait for you."
		id="field-approval-mode"
		inputId="input-approval-mode"
	>
		<select id="input-approval-mode" bind:value={value.approval_mode}>
			<option value="manual">I check every video myself</option>
			<option value="auto">Publish on its own above a score</option>
		</select>
	</Field>

	{#if value.approval_mode === 'auto'}
		<Field
			label="Publish on its own at this score or above (out of 10)"
			help="Finished videos are scored out of 10. At or above this score they publish without waiting for you; below it they still wait. Test videos always wait."
			id="field-auto-approve-score"
			inputId="input-auto-approve-score"
		>
			<input
				id="input-auto-approve-score"
				type="number"
				min="1"
				max="10"
				step="1"
				required
				bind:value={value.auto_approve_score}
			/>
		</Field>
	{/if}

	<Field
		label="Who can see the video on YouTube?"
		help="Private: only you. Unlisted: anyone with the link. Public: anyone can find it. Private is a safe way to start."
		id="field-visibility"
		inputId="input-visibility"
	>
		<select id="input-visibility" bind:value={value.visibility}>
			<option value="private">Private — only I can see it</option>
			<option value="unlisted">Unlisted — anyone with the link</option>
			<option value="public">Public — anyone can find it</option>
		</select>
	</Field>

	<Field
		label="Anything else Shortsmith should know"
		help="Free words for anything else: “always end with a question”, “no scary endings”. These notes are read every time a video is planned."
		id="field-extra-notes"
		inputId="input-extra-notes"
	>
		<textarea id="input-extra-notes" bind:value={value.extra_notes}></textarea>
	</Field>

	<div class="card" id="field-estimate">
		<h3>Estimated clip and thumbnail cost with practice mode off</h3>
		{#if estimate}
			<p>
				About <strong><Money usd={estimate.per_video_usd} /></strong> per video, about
				<strong><Money usd={estimate.per_month_usd} /></strong> per month at this pace.
			</p>
			{#if monthlyBudget !== null && estimate.per_month_usd > monthlyBudget}
				<p>
					That monthly pace is more than your <Money usd={monthlyBudget} /> budget, so videos
					would stop before the extra is spent. Slow the pace above or
					<a href="/settings">raise the budget in Settings</a>.
				</p>
			{/if}
		{:else if estimateFailed}
			<p>The estimate could not be worked out just now. The recipe can still be saved.</p>
		{:else}
			<p class="muted">Working out the estimate…</p>
		{/if}
		<p class="muted small">
			Making the moving clips is nearly all of the cost, charged for every second at your
			chosen video size. Planning and the quality check add a few cents per video on top.
			In practice mode the clips and thumbnail are free.
		</p>
	</div>

	<p class="submit-row">
		<button class="btn btn-primary" type="submit" disabled={busy}>
			{busy ? 'Saving…' : submitLabel}
		</button>
	</p>
</form>

<style>
	.submit-row {
		margin-top: 1rem;
	}
</style>
