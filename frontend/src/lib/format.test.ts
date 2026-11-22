import { describe, expect, it, vi } from 'vitest';
import { formatMoney, timeAgo } from './format';

describe('formatMoney', () => {
	it('shows dollars with cents and thousands separators', () => {
		expect(formatMoney(0)).toBe('$0.00');
		expect(formatMoney(0.07)).toBe('$0.07');
		expect(formatMoney(1.4)).toBe('$1.40');
		expect(formatMoney(1234.5)).toBe('$1,234.50');
	});

	it('never shows a real but tiny cost as $0.00', () => {
		// A text call costs fractions of a cent; "$0.00" would read as "free".
		expect(formatMoney(0.0031)).toBe('less than $0.01');
	});
});

describe('timeAgo', () => {
	const now = new Date('2026-11-22T12:00:00Z');

	it('says how long ago in plain words', () => {
		expect(timeAgo('2026-11-22T11:59:30Z', now)).toBe('just now');
		expect(timeAgo('2026-11-22T11:59:00Z', now)).toBe('1 minute ago');
		expect(timeAgo('2026-11-22T11:55:00Z', now)).toBe('5 minutes ago');
		expect(timeAgo('2026-11-22T11:00:00Z', now)).toBe('1 hour ago');
		expect(timeAgo('2026-11-22T09:00:00Z', now)).toBe('3 hours ago');
		expect(timeAgo('2026-11-21T12:00:00Z', now)).toBe('1 day ago');
		expect(timeAgo('2026-11-20T12:00:00Z', now)).toBe('2 days ago');
	});

	it('says "just now" when the laptop clock is slightly behind the server', () => {
		expect(timeAgo('2026-11-22T12:00:20Z', now)).toBe('just now');
	});

	it('reads server times without a timezone as UTC', () => {
		// SQLite hands datetimes back without a zone; they were saved in UTC.
		vi.stubEnv('TZ', 'America/New_York');
		try {
			expect(timeAgo('2026-11-22T09:00:00', now)).toBe('3 hours ago');
			expect(timeAgo('2026-11-22T08:59:59.123456', now)).toBe('3 hours ago');
			expect(timeAgo('2026-11-22T09:00:00+00:00', now)).toBe('3 hours ago');
		} finally {
			vi.unstubAllEnvs();
		}
	});
});
