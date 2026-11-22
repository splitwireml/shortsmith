<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '$lib/api';
	import Field from '$lib/components/Field.svelte';
	import SystemChecks from '$lib/components/SystemChecks.svelte';
	import { setPractice } from '$lib/practice.svelte';
	import type { Pipeline, Settings, StatusResponse, Video, YoutubeStatus } from '$lib/types';
	import { waitForYoutube } from '$lib/youtube';
	import { onMount } from 'svelte';

	const stepTitles = [
		'Check everything is working',
		'Connect YouTube',
		'Create your first recipe',
		'Set a budget',
		'Make a practice video'
	];

	const stepNames = ['check', 'connect', 'recipe', 'budget', 'practice'];
	const STORE_KEY = 'shortsmith-setup';

	let step = $state(0);
	let skipped = $state<number[]>([]);
	let restored = $state(false);
	let status = $state<StatusResponse | null>(null);
	let youtube = $state<YoutubeStatus | null>(null);
	let youtubeUnavailable = $state(false);
	let pipelines = $state<Pipeline[]>([]);
	let settings = $state<Settings | null>(null);
	let videos = $state<Video[]>([]);
	let budget = $state(30);
	let budgetConfirmed = $state(false);
	let selectedRecipe = $state('');
	let practiceStarted = $state(false);
	let practiceVideoId = $state<number | null>(null);
	let busy = $state('');
	let message = $state('');
	let error = $state('');
	let loading = $state(true);

	const coreChecks = $derived(
		status ? status.checks.filter((check) => check.name !== 'youtube') : []
	);
	const youtubeChecks = $derived(
		status ? status.checks.filter((check) => check.name === 'youtube') : []
	);

	const coreChecksOk = $derived(
		status !== null &&
			status.checks
				.filter((check) => check.name !== 'youtube')
				.every((check) => check.ok)
	);
	const dones = $derived([
		coreChecksOk,
		Boolean(youtube?.connected) && !youtube?.needs_reconnect,
		pipelines.length > 0,
		budgetConfirmed,
		practiceStarted || videos.some((video) => video.is_test)
	]);

	// The guide keeps its place for the session: leaving to create a
	// recipe (or closing and reopening the guide) must not lose the
	// current step, skipped steps, or a saved budget.
	function restoreGuide() {
		try {
			const raw = sessionStorage.getItem(STORE_KEY);
			if (raw) {
				const saved = JSON.parse(raw) as {
					step?: unknown;
					skipped?: unknown;
					budgetConfirmed?: unknown;
				};
				if (Number.isInteger(saved.step)) {
					step = Math.min(stepTitles.length - 1, Math.max(0, Number(saved.step)));
				}
				if (Array.isArray(saved.skipped)) {
					skipped = saved.skipped.filter((value) => Number.isInteger(value)) as number[];
				}
				budgetConfirmed = saved.budgetConfirmed === true;
			}
		} catch {
			// No stored place; start at the beginning.
		}
		const named = page.url.searchParams.get('step');
		const index = named ? stepNames.indexOf(named) : -1;
		if (index >= 0) step = index;
		if (page.url.searchParams.get('saved') === 'recipe') {
			message = 'Recipe saved. It is paused, so nothing is scheduled yet. Next, set your budget.';
		}
		restored = true;
	}

	$effect(() => {
		void step;
		void skipped;
		void budgetConfirmed;
		if (!restored) return;
		try {
			sessionStorage.setItem(STORE_KEY, JSON.stringify({ step, skipped, budgetConfirmed }));
		} catch {
			// Keeping our place is a nicety; the guide still works without it.
		}
	});

	async function load() {
		loading = true;
		try {
			status = await api.get<StatusResponse>('/status');
		} catch {
			status = null;
		}
		try {
			settings = await api.get<Settings>('/settings');
			budget = settings.monthly_budget_usd;
			setPractice(settings.practice_mode);
		} catch {
			settings = null;
		}
		try {
			pipelines = await api.get<Pipeline[]>('/pipelines');
			if (!selectedRecipe && pipelines.length > 0) selectedRecipe = String(pipelines[0].id);
		} catch {
			pipelines = [];
		}
		try {
			videos = await api.get<Video[]>('/videos');
			if (practiceVideoId === null) {
				const tests = videos.filter((video) => video.is_test);
				const mine = tests.filter(
					(video) => String(video.pipeline_id) === selectedRecipe
				);
				const latest = (mine.length > 0 ? mine : tests).at(-1);
				if (latest) practiceVideoId = latest.id;
			}
		} catch {
			videos = [];
		}
		try {
			youtube = await api.get<YoutubeStatus>('/youtube/status');
			youtubeUnavailable = false;
		} catch {
			youtube = null;
			youtubeUnavailable = true;
		}
		loading = false;
	}

	function next() {
		message = '';
		error = '';
		if (step < stepTitles.length - 1) step += 1;
	}

	function back() {
		message = '';
		error = '';
		if (step > 0) step -= 1;
	}

	function skip() {
		if (!skipped.includes(step)) skipped = [...skipped, step];
		next();
	}

	async function finish() {
		if (busy) return;
		busy = 'finish';
		try {
			await api.put<Settings>('/settings', { onboarding_done: true });
		} catch {
			// Finishing still takes the person home; the guide can be reopened any time.
		} finally {
			busy = '';
		}
		await goto('/');
	}

	async function connectYoutube() {
		if (busy) return;
		busy = 'youtube';
		message = 'A Google sign-in page should open. Sign in there, then come back here.';
		error = '';
		try {
			await api.post('/youtube/connect');
			message = 'Waiting for the Google sign-in to finish. This page updates itself.';
			youtube = (await waitForYoutube()) ?? youtube;
			youtubeUnavailable = youtube === null;
			message =
				youtube?.connected && !youtube.needs_reconnect
					? 'YouTube is connected.'
					: 'Signing in has not finished yet. Finish it in the Google tab, or skip this step.';
		} catch {
			error = 'YouTube could not be connected just now. You can skip this step and connect later in Settings.';
		} finally {
			busy = '';
		}
	}

	async function saveBudget() {
		if (busy) return;
		busy = 'budget';
		error = '';
		message = '';
		try {
			settings = await api.put<Settings>('/settings', { monthly_budget_usd: budget });
			budgetConfirmed = true;
			message = 'Budget saved. Shortsmith stops before spending past it.';
			if (step < stepTitles.length - 1) step += 1;
		} catch (caught) {
			error =
				caught instanceof Error ? caught.message : 'The budget could not be saved. Try again.';
		} finally {
			busy = '';
		}
	}

	async function makePractice() {
		if (!selectedRecipe || busy) return;
		busy = 'practice';
		error = '';
		message = '';
		// Confirm practice mode with a fresh read (and switch it on if
		// needed) before queuing anything: a practice run must never
		// quietly become a real, paid one.
		let confirmed: Settings;
		try {
			confirmed = await api.get<Settings>('/settings');
			if (!confirmed.practice_mode) {
				confirmed = await api.put<Settings>('/settings', { practice_mode: true });
			}
			if (!confirmed.practice_mode) throw new Error('practice mode is off');
		} catch {
			error =
				'Practice mode could not be confirmed, so no video was started. Open Settings, make sure practice mode is on, then try again.';
			busy = '';
			return;
		}
		settings = confirmed;
		setPractice(true);
		try {
			const queued = await api.post<Video[]>(`/pipelines/${selectedRecipe}/run`, {
				count: 1,
				is_test: true
			});
			practiceStarted = true;
			practiceVideoId = queued[0]?.id ?? null;
			message = 'Your practice video has been started.';
			await load();
		} catch (caught) {
			error =
				caught instanceof Error
					? caught.message
					: 'The practice video could not be started. Try again.';
		} finally {
			busy = '';
		}
	}

	onMount(() => {
		restoreGuide();
		void load();
	});
</script>

<div class="container stack setup-flow">
	<div>
		<h1>Setup guide</h1>
		<p class="lede">
			Five short steps. Skip anything you like — this guide can be reopened at any time.
		</p>
	</div>

	{#if loading}
		<p class="muted">Loading…</p>
	{/if}
	{#if message}
		<div class="notice"><p>{message}</p></div>
	{/if}
	{#if error}
		<div class="error-box"><p>{error}</p></div>
	{/if}

	<details class="steps-box" id="setup-steps" open>
		<summary>Setup progress — step {step + 1} of {stepTitles.length}</summary>
		<ol class="step-list">
			{#each stepTitles as title, index (title)}
				<li class:step-current={index === step}>
					<button class="linklike step-link" onclick={() => (step = index)}>
						{index + 1}. {title}
					</button>
					<span class="badge {dones[index] ? 'badge-ok' : ''}">
						{dones[index]
							? '✓ Done'
							: skipped.includes(index)
								? 'Skipped'
								: index === step
									? 'You are here'
									: 'To do'}
					</span>
				</li>
			{/each}
		</ol>
	</details>

	<section class="card stack step-card">
		{#if step === 0}
			<h2>1. Check everything is working</h2>
			<p class="muted small">
				These three are what practice needs. YouTube is the next step and is optional for
				practice.
			</p>
			{#if status}
				<SystemChecks checks={coreChecks} />
			{:else}
				<p>The checks could not be loaded. Make sure the app is still running, then try again.</p>
			{/if}
			<p><button class="btn" onclick={load}>Check again</button></p>
		{:else if step === 1}
			<h2>2. Connect YouTube <span class="badge badge-needs">Optional for practice</span></h2>
			{#if youtubeChecks.length > 0}
				<SystemChecks checks={youtubeChecks} />
			{/if}
			<p>
				Connecting lets Shortsmith upload videos you approve and collect their viewer numbers. You
				can skip this and connect later in Settings — making and practising with videos works
				without it.
			</p>
			{#if youtubeUnavailable}
				<p>
					The YouTube connection could not be checked just now. Skip this step and connect later
					in Settings.
				</p>
			{:else if youtube?.connected && youtube.needs_reconnect}
				<p>
					<strong>The connection has expired.</strong> Reconnect to carry on — nothing is lost.
				</p>
				<p>
					<button class="btn" disabled={busy !== ''} onclick={connectYoutube}>
						{busy === 'youtube' ? 'Opening sign-in…' : 'Reconnect YouTube'}
					</button>
				</p>
			{:else if youtube?.connected}
				<p>
					Connected{#if youtube.channel_title}
						to <strong>“{youtube.channel_title}”</strong>{/if}. Lovely — nothing more to do here.
				</p>
			{:else}
				<p>
					<button class="btn" disabled={busy !== ''} onclick={connectYoutube}>
						{busy === 'youtube' ? 'Opening sign-in…' : 'Connect YouTube'}
					</button>
				</p>
				<p class="muted small">Sign in with the Google account that owns your channel.</p>
			{/if}
		{:else if step === 2}
			<h2>3. Create your first recipe</h2>
			<p>
				A channel recipe is your saved instructions for one kind of video. Start from a ready-made
				one, describe your idea in a sentence, or fill in the form yourself. New recipes are
				saved paused, so saving one spends nothing; saving brings you back here to set a budget.
			</p>
			{#if pipelines.length > 0}
				<p>
					You already have {pipelines.length}
					{pipelines.length === 1 ? 'recipe' : 'recipes'}:
					{pipelines.map((pipeline) => pipeline.name).join(', ')}.
				</p>
			{/if}
			<p class="row">
				<a class="btn" href="/pipelines/new?from=setup">Create a recipe</a>
				<button class="btn" onclick={load}>I have made one — check again</button>
			</p>
		{:else if step === 3}
			<h2>4. Set a budget</h2>
			<p>
				The monthly budget is the most Shortsmith may spend in a month. Before any paid step it
				checks first, so nothing is spent past your limit.
			</p>
			<Field
				label="Monthly budget (dollars)"
				help="Thirty dollars makes roughly a dozen half-minute videos. You can change this at any time in Settings, where there is also a most-one-video limit."
				inputId="setup-budget"
			>
				<input id="setup-budget" type="number" min="0" step="1" bind:value={budget} />
			</Field>
			<p>
				<button class="btn" disabled={busy !== ''} onclick={saveBudget}>
					{busy === 'budget' ? 'Saving…' : 'Save budget and continue'}
				</button>
			</p>
		{:else}
			<h2>5. Make a practice video</h2>
			<p>
				A practice video has a real plan but free coloured test clips, and nothing is uploaded.
				Writing the plan and checking it cost a few cents. It is the safe way to see the whole
				journey: planning, making, checking, then your approval.
			</p>
			{#if pipelines.length === 0}
				<p>
					You need a recipe first. Go back to step 3, or
					<a href="/pipelines/new?from=setup">create one now</a>.
				</p>
			{:else}
				{#if settings && !settings.practice_mode}
					<p>
						Practice mode is off just now. Pressing the button below turns it back on first, so
						this stays a practice run.
					</p>
				{/if}
				<Field
					label="Which recipe?"
					help="The practice video follows this recipe, exactly like a real one but with free test clips."
					inputId="setup-recipe"
				>
					<select id="setup-recipe" bind:value={selectedRecipe}>
						{#each pipelines as pipeline (pipeline.id)}
							<option value={String(pipeline.id)}>{pipeline.name}</option>
						{/each}
					</select>
				</Field>
				<p>
					<button class="btn" disabled={busy !== '' || !selectedRecipe} onclick={makePractice}>
						{busy === 'practice' ? 'Starting…' : 'Make a practice video'}
					</button>
				</p>
				{#if practiceVideoId}
					<p>
						<a class="btn" href="/videos/{practiceVideoId}">View your practice video</a>
					</p>
					<p class="muted small">
						It moves from planning to “Needs you” on its own; watch it there, then approve,
						reject or leave a note.
					</p>
				{:else if dones[4]}
					<p>
						Started. Watch its progress on the <a href="/">home page</a>, then approve, reject
						or leave a note when it reaches “Needs you”.
					</p>
				{/if}
			{/if}
		{/if}
	</section>

	<div class="row-between">
		<p class="row">
			<button class="btn" disabled={step === 0} onclick={back}>Back</button>
			{#if step < stepTitles.length - 1}
				<button class="linklike" onclick={skip}>Skip this step</button>
			{/if}
		</p>
		<p>
			{#if step < stepTitles.length - 1}
				<button class="btn btn-primary" onclick={next}>Next</button>
			{:else}
				<button class="btn btn-primary" disabled={busy !== ''} onclick={finish}>
					{busy === 'finish' ? 'Finishing…' : 'Finish and go home'}
				</button>
			{/if}
		</p>
	</div>
	<p>
		<button class="linklike" disabled={busy !== ''} onclick={finish}>
			Skip the whole guide for now
		</button>
	</p>
</div>

<style>
	.step-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 0.5rem;
	}

	.step-list li {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 1rem;
		align-items: center;
		justify-content: space-between;
		background: var(--paper);
		border: 1px solid var(--line);
		border-radius: 10px;
		padding: 0.6rem 0.9rem;
	}

	.step-list li.step-current {
		border-color: var(--primary);
		border-width: 2px;
	}

	.step-link {
		font-size: 1rem;
		font-weight: 700;
	}

	.steps-box summary {
		cursor: pointer;
		font-weight: 700;
		margin-bottom: 0.5rem;
	}

	/* On a phone the current step comes first; the checklist waits below. */
	@media (max-width: 720px) {
		.setup-flow {
			display: flex;
			flex-direction: column;
		}

		.steps-box {
			order: 10;
		}
	}
</style>
