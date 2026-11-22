// Money and times in the plain words the person using the app expects.

const dollars = new Intl.NumberFormat('en-US', {
	style: 'currency',
	currency: 'USD',
	minimumFractionDigits: 2,
	maximumFractionDigits: 2
});

export function formatMoney(usd: number): string {
	// A real charge smaller than a cent must never read as “free”.
	if (usd !== 0 && Math.abs(usd) < 0.01) {
		return usd < 0 ? '-less than $0.01' : 'less than $0.01';
	}
	return dollars.format(usd);
}

const HAS_ZONE = /(?:Z|[+-]\d{2}:?\d{2})$/i;

export function parseServerDate(value: string): Date {
	// Stored times come back without a timezone but were saved in UTC,
	// and fractional seconds may carry more digits than a browser
	// reads. Pin both down before handing the string to Date.
	let text = value.trim().replace(' ', 'T');
	text = text.replace(/(\.\d{3})\d+/, '$1');
	if (/^\d{4}-\d{2}-\d{2}T/.test(text) && !HAS_ZONE.test(text)) {
		text += 'Z';
	}
	return new Date(text);
}

function ago(count: number, unit: string): string {
	return count === 1 ? `1 ${unit} ago` : `${count} ${unit}s ago`;
}

export function timeAgo(value: string | null | undefined, now: Date = new Date()): string {
	if (!value) return 'not yet';
	const then = parseServerDate(value);
	if (Number.isNaN(then.getTime())) return 'not yet';
	const seconds = Math.floor((now.getTime() - then.getTime()) / 1000);
	// A laptop clock a little behind the server is still “just now”.
	if (seconds < 60) return 'just now';
	const minutes = Math.floor(seconds / 60);
	if (minutes < 60) return ago(minutes, 'minute');
	const hours = Math.floor(minutes / 60);
	if (hours < 24) return ago(hours, 'hour');
	return ago(Math.floor(hours / 24), 'day');
}

export function plainDate(value: string | null | undefined): string {
	if (!value) return '—';
	const date = parseServerDate(value.length === 10 ? `${value}T00:00:00Z` : value);
	if (Number.isNaN(date.getTime())) return value;
	return date.toLocaleDateString('en-GB', {
		day: 'numeric',
		month: 'short',
		year: 'numeric',
		timeZone: 'UTC'
	});
}
