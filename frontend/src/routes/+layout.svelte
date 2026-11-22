<script lang="ts">
	import { page } from '$app/state';
	import HelpDrawer from '$lib/components/HelpDrawer.svelte';
	import { highlightElement } from '$lib/highlight';
	import { practiceState, refreshPractice } from '$lib/practice.svelte';
	import type { Snippet } from 'svelte';
	import '../app.css';

	let { children }: { children: Snippet } = $props();

	let helpOpen = $state(false);
	let menuOpen = $state(false);

	// Shared practice state: settings writers update it on save, and this
	// refresh on navigation keeps the last confirmed value if it fails.
	$effect(() => {
		void page.url.pathname;
		menuOpen = false;
		void refreshPractice();
	});

	$effect(() => {
		const highlight = page.url.searchParams.get('highlight');
		if (!highlight) return;
		const timer = setTimeout(() => highlightElement(highlight), 150);
		return () => clearTimeout(timer);
	});

	function onKeyDown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			helpOpen = false;
			return;
		}
		if (event.key !== '?') return;
		const target = event.target as HTMLElement | null;
		const typing =
			target?.tagName === 'INPUT' ||
			target?.tagName === 'TEXTAREA' ||
			target?.tagName === 'SELECT' ||
			target?.isContentEditable;
		if (typing) return;
		event.preventDefault();
		helpOpen = !helpOpen;
	}

	const links = [
		{ href: '/', label: 'Home' },
		{ href: '/pipelines', label: 'Recipes' },
		{ href: '/videos', label: 'Videos' },
		{ href: '/costs', label: 'Money spent' },
		{ href: '/insights', label: 'Lessons' },
		{ href: '/settings', label: 'Settings' },
		{ href: '/setup', label: 'Setup guide' }
	];

	function isActive(href: string): boolean {
		const path = page.url.pathname;
		return href === '/' ? path === '/' : path === href || path.startsWith(`${href}/`);
	}
</script>

<svelte:window onkeydown={onKeyDown} />

{#if practiceState.on}
	<div class="practice-banner">
		Practice mode: free test clips, nothing uploaded. <a href="/settings">Settings</a>
	</div>
{/if}

<header class="site-header">
	<div class="header-inner">
		<a class="brand" href="/">
			<span class="brand-name">Shortsmith</span>
			<span class="brand-sub">YouTube Shorts, made on this laptop</span>
		</a>
		<div class="header-actions">
			<button class="btn btn-small help-button" onclick={() => (helpOpen = !helpOpen)}>
				? Help
			</button>
			<button
				class="btn btn-small menu-button"
				aria-expanded={menuOpen}
				onclick={() => (menuOpen = !menuOpen)}
			>
				Menu
			</button>
		</div>
		<nav class={menuOpen ? 'main-nav nav-open' : 'main-nav'} aria-label="Main">
			<ul class="nav-list">
				{#each links as link (link.href)}
					<li>
						<a href={link.href} aria-current={isActive(link.href) ? 'page' : undefined}>
							{link.label}
						</a>
					</li>
				{/each}
			</ul>
		</nav>
	</div>
</header>

<main>
	{@render children()}
</main>

<footer class="site-footer">
	<p class="muted small">
		Shortsmith runs only on this laptop. Stuck? Press <strong>?</strong> for help, or reopen the
		<a href="/setup">setup guide</a>.
	</p>
</footer>

<HelpDrawer open={helpOpen} onClose={() => (helpOpen = false)} />

<style>
	.site-header {
		background: var(--paper);
		border-bottom: 1px solid var(--line);
	}

	.header-inner {
		max-width: 960px;
		margin: 0 auto;
		padding: 0.8rem 1rem;
		display: flex;
		flex-wrap: wrap;
		gap: 0.6rem 1.5rem;
		align-items: center;
		justify-content: space-between;
	}

	.brand {
		text-decoration: none;
		color: var(--ink);
		display: flex;
		flex-direction: column;
	}

	.brand-name {
		font-size: 1.4rem;
		font-weight: 800;
		line-height: 1.1;
	}

	.brand-sub {
		color: var(--ink-soft);
		font-size: 0.85rem;
	}

	.nav-list {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem 1rem;
		align-items: center;
		list-style: none;
		margin: 0;
		padding: 0;
		font-weight: 600;
	}

	.nav-list a[aria-current='page'] {
		color: var(--ink);
		text-decoration-thickness: 3px;
	}

	.help-button {
		font-weight: 800;
	}

	.header-actions {
		display: flex;
		gap: 0.5rem;
		align-items: center;
		order: 3;
	}

	.main-nav {
		order: 2;
	}

	.menu-button {
		display: none;
	}

	/* At phone width the links wait behind Menu; Help stays visible. */
	@media (max-width: 720px) {
		.menu-button {
			display: inline-block;
		}

		.main-nav {
			display: none;
			width: 100%;
			order: 4;
		}

		.main-nav.nav-open {
			display: block;
		}

		.nav-list {
			flex-direction: column;
			align-items: flex-start;
			gap: 0.6rem;
			padding: 0.4rem 0 0.2rem;
		}

		.brand-sub {
			display: none;
		}
	}

	.site-footer {
		max-width: 960px;
		margin: 0 auto;
		padding: 0 1rem 2rem;
	}
</style>
