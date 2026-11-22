<script lang="ts">
	// The one YouTube connection display, shared by Settings and the
	// setup guide: it loads the connection, offers Connect/Reconnect
	// (waiting for the browser sign-in to land), and reports each new
	// status to the page. Expiry is checked first: an expired sign-in
	// comes back as connected:false with needs_reconnect:true.
	import { api } from '$lib/api';
	import type { YoutubeStatus } from '$lib/types';
	import { waitForYoutube } from '$lib/youtube';
	import { onMount } from 'svelte';

	let {
		showDisconnect = false,
		disabled = false,
		onChange
	}: {
		showDisconnect?: boolean;
		disabled?: boolean;
		onChange?: (status: YoutubeStatus | null) => void;
	} = $props();

	let status = $state<YoutubeStatus | null>(null);
	let unavailable = $state(false);
	let busy = $state(false);
	let message = $state('');

	async function load() {
		try {
			status = await api.get<YoutubeStatus>('/youtube/status');
			unavailable = false;
		} catch {
			status = null;
			unavailable = true;
		}
		onChange?.(status);
	}

	async function connect() {
		if (busy || disabled) return;
		busy = true;
		message = 'A Google sign-in page should open. Sign in there, then come back here.';
		try {
			await api.post('/youtube/connect');
			// Sign-in finishes in the browser tab it opened; wait for it here.
			message =
				'Waiting for the Google sign-in to finish. This page updates itself when it lands.';
			status = (await waitForYoutube()) ?? status;
			unavailable = status === null;
			onChange?.(status);
			message =
				status?.connected && !status.needs_reconnect
					? 'YouTube is connected.'
					: 'Signing in has not finished yet. Finish it in the Google tab, or press the button to try again.';
		} catch {
			message = 'YouTube could not be connected just now. Try again in a moment.';
		} finally {
			busy = false;
		}
	}

	async function disconnect() {
		if (busy || disabled) return;
		busy = true;
		message = '';
		try {
			await api.post('/youtube/disconnect');
			await load();
			message =
				'YouTube has been disconnected. Nothing will be uploaded until you connect again.';
		} catch {
			message = 'YouTube could not be disconnected just now. Try again in a moment.';
		} finally {
			busy = false;
		}
	}

	onMount(load);
</script>

<div class="stack">
	{#if unavailable}
		<p>
			The YouTube connection could not be checked just now. Everything else works as normal —
			try again in a moment.
		</p>
		<p>
			<button class="btn" id="youtube-connect" disabled={busy || disabled} onclick={load}>
				Check again
			</button>
		</p>
	{:else if status?.needs_reconnect}
		<p>
			<strong>The connection has expired</strong>{#if status.channel_title}
				for “{status.channel_title}”{/if}. This is normal now and then. Reconnect to carry on
			publishing — nothing is lost.
		</p>
		<p class="row">
			<button class="btn" id="youtube-connect" disabled={busy || disabled} onclick={connect}>
				{busy ? 'Opening sign-in…' : 'Reconnect YouTube'}
			</button>
		</p>
	{:else if status?.connected}
		<p>
			Connected{#if status.channel_title}
				to <strong>“{status.channel_title}”</strong>{/if}. Videos you approve are uploaded to this
			channel.
		</p>
		<p class="row">
			<button class="btn" id="youtube-connect" disabled={busy || disabled} onclick={connect}>
				Reconnect
			</button>
			{#if showDisconnect}
				<button class="btn btn-danger" disabled={busy || disabled} onclick={disconnect}>
					Disconnect
				</button>
			{/if}
		</p>
	{:else}
		<p>
			Not connected yet. Connect when you are ready to publish; you can make and practise with
			videos first.
		</p>
		<p>
			<button class="btn" id="youtube-connect" disabled={busy || disabled} onclick={connect}>
				{busy ? 'Opening sign-in…' : 'Connect YouTube'}
			</button>
		</p>
	{/if}
	{#if message}
		<p>{message}</p>
	{/if}
</div>
