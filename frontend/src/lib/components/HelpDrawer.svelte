<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '$lib/api';
	import { searchArticles, type Article } from '$lib/help/search';
	import { highlightElement } from '$lib/highlight';

	type Props = { open: boolean; onClose: () => void };
	let { open, onClose }: Props = $props();

	const FEW = 5;

	let articles = $state<Article[]>([]);
	let attempted = $state(false);
	let loadError = $state('');
	let query = $state('');
	let showAll = $state(false);
	let openId = $state<string | null>(null);
	let question = $state('');
	let answer = $state('');
	let askError = $state('');
	let asking = $state(false);

	const currentPage = $derived(page.route.id ?? page.url.pathname);
	const results = $derived(searchArticles(articles, query, currentPage));
	const shown = $derived(showAll ? results : results.slice(0, FEW));

	$effect(() => {
		void query;
		showAll = false;
		openId = null;
	});

	function preview(article: Article): string {
		const end = article.body.indexOf('. ');
		const first = end === -1 ? article.body : article.body.slice(0, end + 1);
		return first.length > 120 ? `${first.slice(0, 117)}…` : first;
	}

	function goToAsk() {
		document.getElementById('help-ask-section')?.scrollIntoView({ block: 'start' });
		document.getElementById('help-ask')?.focus({ preventScroll: true });
	}

	async function load() {
		attempted = true;
		loadError = '';
		try {
			const data = await api.get<Article[] | { articles?: Article[] }>('/help/articles');
			articles = Array.isArray(data) ? data : (data.articles ?? []);
			if (articles.length === 0) {
				loadError = 'Help pages are not available yet. Try again in a moment.';
			}
		} catch {
			loadError = 'Help pages could not be loaded just now. Try again in a moment.';
		}
	}

	$effect(() => {
		if (open && !attempted) void load();
	});

	function showMe(article: Article) {
		if (!article.show_me) return;
		const { href, highlight } = article.show_me;
		// Already on a page this article covers and the thing is here:
		// light it up in place so unsaved words are not thrown away.
		if (article.pages.includes(currentPage) && document.getElementById(highlight)) {
			onClose();
			setTimeout(() => highlightElement(highlight), 60);
			return;
		}
		onClose();
		void goto(`${href}?highlight=${encodeURIComponent(highlight)}`);
	}

	async function ask() {
		const trimmed = question.trim();
		if (!trimmed || asking) return;
		asking = true;
		askError = '';
		answer = '';
		try {
			const reply = await api.post<{ answer?: string }>('/help/ask', {
				question: trimmed,
				page: currentPage
			});
			answer = reply.answer?.trim() ?? '';
			if (!answer) {
				askError = 'The assistant could not answer just now. Try searching the help pages above.';
			}
		} catch {
			askError = 'The assistant could not answer just now. Try searching the help pages above.';
		} finally {
			asking = false;
		}
	}
</script>

{#if open}
	<button class="overlay" aria-label="Close help" onclick={onClose}></button>
	<aside class="drawer" aria-label="Help">
		<div class="row-between">
			<h2>Help</h2>
			<button class="btn btn-small" onclick={onClose}>Close</button>
		</div>
		<label class="search-label" for="help-search">Search the help pages</label>
		<!-- svelte-ignore a11y_autofocus -->
		<input
			id="help-search"
			type="search"
			placeholder="Type a word, like budget or YouTube"
			bind:value={query}
			autofocus
		/>
		<p class="muted small">
			Help for the page you are on comes first.
			<button class="linklike" onclick={goToAsk}>Ask the assistant</button> if search does not find
			it. Press the ? key any time.
		</p>

		{#if loadError}
			<div class="error-box stack">
				<p>{loadError}</p>
				<p>
					<button
						class="btn btn-small"
						onclick={() => {
							attempted = false;
							void load();
						}}>Try again</button
					>
				</p>
			</div>
		{:else if results.length === 0}
			<p>Nothing matches those words yet. Try a shorter word, or ask the assistant below.</p>
		{:else}
			<p class="muted small">
				Showing {shown.length} of {results.length}
				{results.length === 1 ? 'result' : 'results'}.
			</p>
			<div class="stack">
				{#each shown as article (article.id)}
					<article class="help-article">
						<h3>
							<button
								class="title-button"
								aria-expanded={openId === article.id}
								onclick={() => (openId = openId === article.id ? null : article.id)}
							>
								{article.title}
							</button>
						</h3>
						{#if openId === article.id}
							<p>{article.body}</p>
						{:else}
							<p class="preview">{preview(article)}</p>
						{/if}
						<p class="row">
							{#if openId !== article.id}
								<button class="linklike" onclick={() => (openId = article.id)}>Read more</button>
							{/if}
							{#if article.show_me}
								<button class="btn btn-small" onclick={() => showMe(article)}>Show me</button>
							{/if}
						</p>
					</article>
				{/each}
			</div>
			{#if !showAll && results.length > shown.length}
				<p>
					<button class="btn" onclick={() => (showAll = true)}>
						Show more ({results.length - shown.length} more)
					</button>
				</p>
			{/if}
		{/if}

		<hr />
		<h3 id="help-ask-section">Ask the assistant</h3>
		<p class="muted">
			For anything search did not find. It answers from these help pages and how your app stands
			right now. Each question costs a few cents and appears under Money spent.
		</p>
		<label class="search-label" for="help-ask">Your question</label>
		<textarea id="help-ask" bind:value={question} placeholder="How do I …?"></textarea>
		<p>
			<button class="btn btn-primary" disabled={asking || !question.trim()} onclick={ask}>
				{asking ? 'Asking…' : 'Ask the assistant'}
			</button>
		</p>
		{#if answer}
			<div class="notice"><p>{answer}</p></div>
		{/if}
		{#if askError}
			<div class="error-box"><p>{askError}</p></div>
		{/if}
	</aside>
{/if}

<style>
	.overlay {
		position: fixed;
		inset: 0;
		background: rgba(20, 35, 28, 0.4);
		border: none;
		z-index: 40;
		cursor: pointer;
	}

	.drawer {
		position: fixed;
		top: 0;
		right: 0;
		height: 100dvh;
		width: min(28rem, 100vw);
		background: var(--paper);
		border-left: 1px solid var(--line);
		z-index: 41;
		overflow-y: auto;
		padding: 1rem;
	}

	.search-label {
		display: block;
		font-weight: 700;
		margin-bottom: 0.3rem;
	}

	.help-article {
		border: 1px solid var(--line);
		border-radius: 10px;
		padding: 0.8rem 0.9rem;
	}

	.title-button {
		background: none;
		border: none;
		padding: 0;
		font: inherit;
		font-weight: 700;
		color: var(--ink);
		text-align: left;
		cursor: pointer;
	}

	.preview {
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		color: var(--ink-soft);
	}

	hr {
		border: none;
		border-top: 1px solid var(--line);
		margin: 1.2rem 0;
	}
</style>
