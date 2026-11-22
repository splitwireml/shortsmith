<script lang="ts">
	import { api } from '$lib/api';
	import Field from '$lib/components/Field.svelte';
	import YoutubeConnect from '$lib/components/YoutubeConnect.svelte';
	import { setPractice } from '$lib/practice.svelte';
	import type { Settings } from '$lib/types';
	import { onMount } from 'svelte';

	let form = $state<Settings | null>(null);
	let loading = $state(true);
	let loadError = $state('');
	let saving = $state(false);
	let saveError = $state('');
	let notice = $state('');

	async function load() {
		loading = true;
		try {
			form = await api.get<Settings>('/settings');
			setPractice(form.practice_mode);
			loadError = '';
		} catch (caught) {
			loadError =
				caught instanceof Error ? caught.message : 'Settings could not be loaded. Try again.';
		} finally {
			loading = false;
		}
	}

	async function save(event: SubmitEvent) {
		event.preventDefault();
		if (!form || saving) return;
		saving = true;
		saveError = '';
		notice = '';
		try {
			form = await api.put<Settings>('/settings', {
				monthly_budget_usd: form.monthly_budget_usd,
				per_video_cap_usd: form.per_video_cap_usd,
				retention_days: form.retention_days,
				max_storage_gb: form.max_storage_gb,
				practice_mode: form.practice_mode,
				planner_model: form.planner_model,
				planner_effort: form.planner_effort,
				reviewer_model: form.reviewer_model,
				reviewer_effort: form.reviewer_effort,
				analyst_model: form.analyst_model,
				analyst_effort: form.analyst_effort,
				helper_model: form.helper_model,
				helper_effort: form.helper_effort,
				video_model: form.video_model,
				video_resolution: form.video_resolution,
				image_model: form.image_model
			});
			setPractice(form.practice_mode);
			notice = 'Your settings have been saved.';
		} catch (caught) {
			saveError =
				caught instanceof Error ? caught.message : 'Settings could not be saved. Try again.';
		} finally {
			saving = false;
		}
	}

	onMount(load);
</script>

<div class="container stack">
	<div>
		<h1>Settings</h1>
		<p class="lede">Money limits, practice mode and your YouTube connection.</p>
	</div>

	{#if loading}
		<p class="muted">Loading…</p>
	{/if}
	{#if loadError}
		<div class="error-box">
			<p>{loadError}</p>
			<p><button class="btn btn-small" onclick={load}>Try again</button></p>
		</div>
	{/if}
	{#if notice}
		<div class="notice"><p>{notice}</p></div>
	{/if}
	{#if saveError}
		<div class="error-box"><p>{saveError}</p></div>
	{/if}

	<section class="card stack" id="youtube">
		<h2>Your YouTube channel</h2>
		<YoutubeConnect showDisconnect />
	</section>

	{#if form}
		<form class="card" onsubmit={save}>
			<h2>Money and everyday choices</h2>

			<Field
				label="Monthly budget (dollars)"
				help="The most Shortsmith may spend in a month, across everything. Before any paid step it checks this first; if the step would go over, the video stops and nothing is spent."
				id="setting-monthly-budget"
				inputId="input-monthly-budget"
			>
				<input
					id="input-monthly-budget"
					type="number"
					min="0"
					step="0.50"
					required
					bind:value={form.monthly_budget_usd}
				/>
			</Field>

			<Field
				label="Most one video may cost (dollars)"
				help="A safety net for a single video: if making it would cost more than this, it stops before the money is spent and explains why."
				id="setting-per-video-cap"
				inputId="input-per-video-cap"
			>
				<input
					id="input-per-video-cap"
					type="number"
					min="0"
					step="0.50"
					required
					bind:value={form.per_video_cap_usd}
				/>
			</Field>

			<Field
				label="Practice mode"
				help="In practice mode the clips are free coloured test clips and nothing is uploaded to YouTube. Writing the plan still costs a few cents, which makes a practice run true to life. A yellow banner shows while it is on."
				id="setting-practice-mode"
				inputId="input-practice-mode"
			>
				<span class="row">
					<input id="input-practice-mode" type="checkbox" bind:checked={form.practice_mode} />
					<span>{form.practice_mode ? 'Practice mode is on' : 'Practice mode is off — real videos'}</span>
				</span>
			</Field>

			<Field
				label="Keep video files for … days"
				help="After this many days, clean-up removes old video files to free space: unpublished videos become “archived”. Published videos stay on YouTube either way, and notes and money records are always kept."
				id="setting-retention-days"
				inputId="input-retention-days"
			>
				<input
					id="input-retention-days"
					type="number"
					min="1"
					step="1"
					required
					bind:value={form.retention_days}
				/>
			</Field>

			<Field
				label="Most room videos may take up (GB)"
				help="If the folder holding video files grows past this size, the oldest files are removed first until there is room again."
				id="setting-max-storage"
				inputId="input-max-storage"
			>
				<input
					id="input-max-storage"
					type="number"
					min="0.5"
					step="0.5"
					required
					bind:value={form.max_storage_gb}
				/>
			</Field>

			<details id="advanced-settings">
				<summary><strong>Advanced: the names under the hood</strong></summary>
				<p class="muted">
					The starting choices work well. Change these only if you know the exact name you want —
					a name Shortsmith cannot price will be refused, so nothing is spent at an unknown
					price. “Effort” is how hard a wording step thinks; harder costs a little more.
				</p>

				<Field
					label="Planning the video"
					help="Writes the idea, title and scene-by-scene plan. Starting name: gemini-4-hydrogen."
					inputId="input-planner-model"
				>
					<input id="input-planner-model" bind:value={form.planner_model} required />
					<select aria-label="Planning effort" bind:value={form.planner_effort}>
						<option value="low">Effort: low</option>
						<option value="medium">Effort: medium</option>
						<option value="high">Effort: high</option>
						<option value="xhigh">Effort: extra high (only some names)</option>
					</select>
				</Field>

				<Field
					label="Checking the finished video"
					help="Watches the joined video, scores it and names any bad clip. Starting name: gemini-4-argon."
					inputId="input-reviewer-model"
				>
					<input id="input-reviewer-model" bind:value={form.reviewer_model} required />
					<select aria-label="Checking effort" bind:value={form.reviewer_effort}>
						<option value="low">Effort: low</option>
						<option value="medium">Effort: medium</option>
						<option value="high">Effort: high</option>
						<option value="xhigh">Effort: extra high (only some names)</option>
					</select>
				</Field>

				<Field
					label="Learning from results"
					help="Studies viewer numbers and writes short lessons. Starting name: gemini-4-hydrogen."
					inputId="input-analyst-model"
				>
					<input id="input-analyst-model" bind:value={form.analyst_model} required />
					<select aria-label="Learning effort" bind:value={form.analyst_effort}>
						<option value="low">Effort: low</option>
						<option value="medium">Effort: medium</option>
						<option value="high">Effort: high</option>
						<option value="xhigh">Effort: extra high (only some names)</option>
					</select>
				</Field>

				<Field
					label="Help answers and filling in recipes"
					help="Answers “Ask the assistant” questions and fills in a recipe from one sentence. Starting name: gemini-4-hydrogen."
					inputId="input-helper-model"
				>
					<input id="input-helper-model" bind:value={form.helper_model} required />
					<select aria-label="Help effort" bind:value={form.helper_effort}>
						<option value="low">Effort: low</option>
						<option value="medium">Effort: medium</option>
						<option value="high">Effort: high</option>
						<option value="xhigh">Effort: extra high (only some names)</option>
					</select>
				</Field>

				<Field
					label="Making the moving clips"
					help="Makes each video clip. Starting name: gemini-omni-1.2-flash. Bigger sizes cost more per second; 720p is the usual choice."
					inputId="input-video-model"
				>
					<input id="input-video-model" bind:value={form.video_model} required />
					<select aria-label="Video size" bind:value={form.video_resolution}>
						<option value="360p">Size: 360p (cheapest)</option>
						<option value="720p">Size: 720p (usual)</option>
						<option value="1080p">Size: 1080p</option>
						<option value="4k">Size: 4k (most costly)</option>
					</select>
				</Field>

				<Field
					label="Making the thumbnail picture"
					help="Makes the still picture viewers see first. Starting name: gemini-nano-banana-2.1. Other known names: gemini-3.1-flash-image, gemini-3.1-flash-lite-image, gemini-3-pro-image."
					inputId="input-image-model"
				>
					<input id="input-image-model" bind:value={form.image_model} required />
				</Field>
			</details>

			<p class="submit-row">
				<button class="btn btn-primary" type="submit" disabled={saving}>
					{saving ? 'Saving…' : 'Save settings'}
				</button>
			</p>
			<p class="muted small"><a href="/setup">Reopen the setup guide</a></p>
		</form>
	{/if}
</div>

<style>
	details {
		margin-top: 1.2rem;
		border-top: 1px solid var(--line);
		padding-top: 1rem;
	}

	summary {
		cursor: pointer;
		margin-bottom: 0.6rem;
	}

	.submit-row {
		margin-top: 1rem;
	}

	select {
		margin-top: 0.4rem;
	}
</style>
