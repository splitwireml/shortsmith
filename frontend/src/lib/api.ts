// The one way the browser talks to Shortsmith. Every call goes through
// here so the person using the app only ever sees a plain sentence.

export class ApiError extends Error {
	status: number;

	constructor(message: string, status: number) {
		super(message);
		this.name = 'ApiError';
		this.status = status;
	}
}

const OFFLINE =
	'Shortsmith could not be reached. Check that the app is still running, then try again.';
const WENT_WRONG = 'Something went wrong in Shortsmith. Please wait a moment and try again.';
const PLEASE_CHECK = 'Shortsmith could not do that. Please check what you entered and try again.';

function plainMessage(status: number): string {
	if (status >= 500) return WENT_WRONG;
	if (status >= 400) return PLEASE_CHECK;
	return WENT_WRONG;
}

async function messageFrom(response: Response): Promise<string> {
	// The server answers errors with one plain sentence. Anything else
	// is a crash page or a form problem the person cannot act on, so
	// swap it for a sentence they can.
	const text = await response.text().catch(() => '');
	if (text) {
		try {
			const parsed: unknown = JSON.parse(text);
			if (
				parsed !== null &&
				typeof parsed === 'object' &&
				'detail' in parsed &&
				typeof (parsed as { detail: unknown }).detail === 'string' &&
				(parsed as { detail: string }).detail.trim() !== ''
			) {
				return (parsed as { detail: string }).detail;
			}
		} catch {
			// Not a server sentence at all; use the plain message below.
		}
	}
	return plainMessage(response.status);
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
	let response: Response;
	try {
		response = await fetch(`/api${path}`, {
			method,
			headers: body === undefined ? undefined : { 'content-type': 'application/json' },
			body: body === undefined ? undefined : JSON.stringify(body)
		});
	} catch {
		throw new ApiError(OFFLINE, 0);
	}

	if (!response.ok) {
		throw new ApiError(await messageFrom(response), response.status);
	}
	if (response.status === 204) return undefined as T;

	const text = await response.text().catch(() => '');
	if (text.trim() === '') return undefined as T;
	try {
		return JSON.parse(text) as T;
	} catch {
		// A successful answer we cannot read is still not something to
		// show the person; hand back the text for pages that can use it.
		return text as T;
	}
}

export const api = {
	get<T>(path: string): Promise<T> {
		return request<T>('GET', path);
	},
	post<T>(path: string, body?: unknown): Promise<T> {
		return request<T>('POST', path, body);
	},
	put<T>(path: string, body?: unknown): Promise<T> {
		return request<T>('PUT', path, body);
	},
	del(path: string): Promise<void> {
		return request<void>('DELETE', path);
	}
};
