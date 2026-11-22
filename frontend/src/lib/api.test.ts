import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from './api';

const json = (body: unknown, status = 200) =>
	new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

function serverReplies(reply: () => Response | Promise<Response>) {
	const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => reply());
	vi.stubGlobal('fetch', fetchMock);
	return fetchMock;
}

async function errorFrom(call: Promise<unknown>): Promise<ApiError> {
	try {
		await call;
	} catch (error) {
		expect(error).toBeInstanceOf(ApiError);
		return error as ApiError;
	}
	throw new Error('expected the call to fail');
}

// Raw technical text the person using the app must never see.
const JARGON =
	/internal server error|bad gateway|failed to fetch|typeerror|syntaxerror|unexpected (token|end)|json|\[object|undefined|null|\b[45]\d\d\b/i;

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('api', () => {
	it('gets JSON from /api', async () => {
		const fetchMock = serverReplies(() => json({ practice_mode: true }));
		await expect(api.get('/status')).resolves.toEqual({ practice_mode: true });
		expect(fetchMock.mock.calls[0][0]).toBe('/api/status');
	});

	it('sends a body as JSON and returns the reply', async () => {
		const fetchMock = serverReplies(() => json([{ id: 7, status: 'queued' }], 201));
		const videos = await api.post('/pipelines/1/run', { count: 2, is_test: true });

		expect(videos).toEqual([{ id: 7, status: 'queued' }]);
		const [url, init] = fetchMock.mock.calls[0];
		expect(url).toBe('/api/pipelines/1/run');
		expect(init?.method).toBe('POST');
		expect(new Headers(init?.headers).get('content-type')).toContain('application/json');
		expect(JSON.parse(String(init?.body))).toEqual({ count: 2, is_test: true });
	});

	it('handles an empty "done" reply', async () => {
		const fetchMock = serverReplies(() => new Response(null, { status: 204 }));
		await expect(api.del('/pipelines/3')).resolves.toBeUndefined();
		expect(fetchMock.mock.calls[0][1]?.method).toBe('DELETE');
	});

	it("passes the server's own plain sentence straight through", async () => {
		const sentence = 'This video is not waiting for your decision right now.';
		serverReplies(() => json({ detail: sentence }, 409));

		const error = await errorFrom(api.post('/videos/4/approve'));
		expect(error.message).toBe(sentence);
		expect(error.status).toBe(409);
	});

	it.each([
		['the server crashed', () => new Response('Internal Server Error', { status: 500 })],
		['the backend is not running behind the dev proxy', () => new Response(null, { status: 502 })],
		[
			'the detail is not a sentence',
			() => json({ detail: [{ loc: ['body', 'name'], msg: 'Field required' }] }, 422)
		],
		[
			'the app cannot be reached at all',
			() => Promise.reject(new TypeError('Failed to fetch'))
		]
	])('gives a plain message when %s', async (_case, reply) => {
		serverReplies(reply);

		const error = await errorFrom(api.put('/settings', { monthly_budget_usd: 30 }));
		expect(error.message.trim().length).toBeGreaterThan(10);
		expect(error.message).not.toMatch(JARGON);
	});
});
