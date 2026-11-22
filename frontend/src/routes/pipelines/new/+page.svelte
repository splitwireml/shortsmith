<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '$lib/api';
	import Field from '$lib/components/Field.svelte';
	import PipelineForm from '$lib/components/PipelineForm.svelte';
	import type { Pipeline, PipelineInput } from '$lib/types';
	import { onMount } from 'svelte';

	function blankForm(): PipelineInput {
		return {
			name: '',
			niche: '',
			objective: '',
			audience: '',
			region_notes: '',
			genre: '',
			art_style: '',
			target_seconds: 30,
			every_days: 2,
			videos_per_run: 1,
			approval_mode: 'manual',
			auto_approve_score: 8,
			visibility: 'private',
			extra_notes: ''
		};
	}

	let formData = $state<PipelineInput>(blankForm());
	let presets = $state<PipelineInput[]>([]);
	let presetsError = $state('');
	let chosenPreset = $state('');
	let description = $state('');
	let suggesting = $state(false);
	let suggestError = $state('');
	let suggestNotice = $state('');
	let saving = $state(false);
	let saveError = $state('');

	const fromSetup = $derived(page.url.searchParams.get('from') === 'setup');

	function pickPreset(preset: PipelineInput) {
		formData = { ...preset };
		chosenPreset = preset.name;
	}

	function startBlank() {
		formData = blankForm();
		chosenPreset = '';
	}

	async function load() {
		try {
			presets = await api.get<PipelineInput[]>('/presets');
		} catch {
			presetsError =
				'Ready-made recipes could not be loaded. The blank form below works just as well.';
		}
	}

	async function suggest() {
		const sentence = description.trim();
		if (!sentence || suggesting) return;
		suggesting = true;
		suggestError = '';
		suggestNotice = '';
		try {
			const filled = await api.post<PipelineInput>('/pipelines/suggest', {
				description: sentence
			});
			formData = { ...filled };
			chosenPreset = '';
			suggestNotice =
				'The form below has been filled in. Read through it and change anything that is not quite right, then save.';
		} catch {
			suggestError =
				'That shortcut is not available just now. The form below works filled in by hand.';
		} finally {
			suggesting = false;
		}
	}

	async function save() {
		if (saving) return;
		saving = true;
		saveError = '';
		try {
			const created = await api.post<Pipeline>('/pipelines', formData);
			// From the setup guide, go straight back to its budget step;
			// otherwise land on the new (paused) recipe.
			if (fromSetup) {
				await goto('/setup?step=budget&saved=recipe');
			} else {
				await goto(`/pipelines/${created.id}`);
			}
		} catch (caught) {
			saveError =
				caught instanceof Error ? caught.message : 'The recipe could not be saved. Try again.';
		} finally {
			saving = false;
		}
	}

	onMount(load);
</script>

<div class="container stack">
	<div>
		<h1>Create a channel recipe</h1>
		<p class="lede">
			Tell Shortsmith what kind of videos to make. A new recipe is saved paused, so saving
			never starts spending. You can change any of this later.
		</p>
	</div>

	<section class="card" id="field-presets">
		<h2>Start from a ready-made recipe</h2>
		<p class="muted">Pick the closest one and adjust it, or start blank.</p>
		{#if presetsError}
			<p>{presetsError}</p>
		{/if}
		<p class="row">
			{#each presets as preset (preset.name)}
				<button type="button" class="btn btn-small" onclick={() => pickPreset(preset)}>
					{preset.name}
				</button>
			{/each}
			<button type="button" class="btn btn-small" onclick={startBlank}>Blank</button>
		</p>
		{#if chosenPreset}
			<div class="notice preset-summary">
				<p>
					<strong>{chosenPreset}</strong> — {formData.videos_per_run}
					{formData.videos_per_run === 1 ? 'video' : 'videos'} every {formData.every_days}
					{formData.every_days === 1 ? 'day' : 'days'}, about {formData.target_seconds} seconds
					each. Saved paused: nothing is scheduled until you start the schedule from the recipe
					page.
				</p>
				<p class="row">
					<button class="btn btn-primary" type="submit" form="recipe-form" disabled={saving}>
						{saving ? 'Saving…' : 'Save recipe'}
					</button>
					<a href="#recipe-form">Edit the details below first</a>
				</p>
			</div>
		{/if}
	</section>

	<section class="card" id="field-describe">
		<h2>…or describe it in a sentence</h2>
		<Field
			label="Your sentence"
			help="One sentence about the videos you want, such as “short jokes about cats for children”. Shortsmith fills in the form and you correct it. Filling the form in by hand works just as well."
			inputId="input-describe"
		>
			<input
				id="input-describe"
				bind:value={description}
				placeholder="e.g. Short jokes about cats for children"
			/>
		</Field>
		{#if suggestNotice}
			<div class="notice"><p>{suggestNotice}</p></div>
		{/if}
		{#if suggestError}
			<div class="error-box"><p>{suggestError}</p></div>
		{/if}
		<p>
			<button class="btn" disabled={suggesting || !description.trim()} onclick={suggest}>
				{suggesting ? 'Filling in…' : 'Fill in the form for me'}
			</button>
		</p>
	</section>

	<section class="card">
		<h2>The recipe</h2>
		{#if saveError}
			<div class="error-box"><p>{saveError}</p></div>
		{/if}
		<PipelineForm
			bind:value={formData}
			formId="recipe-form"
			submitLabel="Save recipe"
			busy={saving}
			onSubmit={save}
		/>
	</section>
</div>

<style>
	.preset-summary {
		margin-top: 0.8rem;
	}
</style>
