import { describe, expect, it } from 'vitest';
import { searchArticles, type Article } from './search';

// Shape from docs/02-architecture.md. `pages` are SvelteKit route ids.
const articles: Article[] = [
	{
		id: 'practice-mode',
		title: 'What is practice mode?',
		body: 'In practice mode videos are made from free test clips and nothing is uploaded to YouTube. Only the planning text costs a few cents.',
		pages: ['/settings', '/'],
		keywords: ['test', 'free', 'fake']
	},
	{
		id: 'budget',
		title: 'Setting a monthly budget',
		body: 'The budget is the most the app may spend in a month. You can change it at any time. When it is reached, videos stop before anything is spent.',
		pages: ['/settings'],
		keywords: ['money', 'limit', 'spend']
	},
	{
		id: 'costs-page',
		title: 'Reading the costs page',
		body: 'See where it goes: spend by stage, by recipe and per video. Video clips are nearly all of the cost.',
		pages: ['/costs'],
		keywords: ['money', 'dollars', 'spend']
	},
	{
		id: 'connect-youtube',
		title: 'Connecting your YouTube channel',
		body: 'Press Connect and sign in with Google in the tab that opens. If the connection expires, press Reconnect.',
		pages: ['/setup', '/settings'],
		keywords: ['google', 'channel', 'login'],
		show_me: { href: '/settings', highlight: 'youtube-connect' }
	},
	{
		id: 'approve',
		title: 'Approving or rejecting a video',
		body: 'Watch the video, then press Approve to publish it or Reject to throw it away. Your reason becomes a lesson.',
		pages: ['/videos/[id]', '/'],
		keywords: ['publish', 'inbox']
	}
];

const ids = (query: string, page = '') => searchArticles(articles, query, page).map((a) => a.id);

describe('searchArticles', () => {
	it('finds the right article for a question asked in plain words', () => {
		expect(ids('How do I change my budget?')[0]).toBe('budget');
	});

	it('ignores ordinary question words so they match nothing on their own', () => {
		expect(ids('How do I change my budget?')).toEqual(['budget']);
	});

	it('matches words while they are still being typed, ignoring case', () => {
		expect(ids('BUDG')[0]).toBe('budget');
	});

	it('ranks the article about a topic above one that only mentions it', () => {
		const result = ids('youtube');
		expect(result).toContain('practice-mode');
		expect(result[0]).toBe('connect-youtube');
	});

	it('leaves out articles that do not match at all', () => {
		expect(ids('youtube')).not.toContain('budget');
		expect(ids('zebra')).toEqual([]);
	});

	it("puts the current page's articles first when matches are equally good", () => {
		expect(ids('spend money', '/costs')[0]).toBe('costs-page');
		expect(ids('spend money', '/settings')[0]).toBe('budget');
	});

	it("lists every article, current page's first, before anything is typed", () => {
		const result = ids('  ', '/costs');
		expect(result[0]).toBe('costs-page');
		expect([...result].sort()).toEqual(articles.map((a) => a.id).sort());
	});
});
