import { describe, expect, it } from 'vitest';

import { parseUtcTimestamp } from './time';

describe('UTC timestamp parsing', () => {
    it('treats SQLite timestamps as UTC instead of browser-local time', () => {
        expect(parseUtcTimestamp('2026-08-12 00:00:00').toISOString()).toBe('2026-08-12T00:00:00.000Z');
    });

    it('preserves explicit source offsets', () => {
        expect(parseUtcTimestamp('2026-08-12T08:00:00+08:00').toISOString()).toBe('2026-08-12T00:00:00.000Z');
    });
});
