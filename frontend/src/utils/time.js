const SQL_TIMESTAMP = /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/;

export function parseUtcTimestamp(value) {
    if (value instanceof Date) return value;
    if (typeof value !== 'string' || !value.trim()) return new Date(Number.NaN);
    const raw = value.trim();
    const normalized = SQL_TIMESTAMP.test(raw) ? `${raw.replace(' ', 'T')}Z` : raw;
    return new Date(normalized);
}

export function formatLocalDateTime(value) {
    const date = parseUtcTimestamp(value);
    return Number.isNaN(date.getTime()) ? value || '-' : date.toLocaleString('zh-CN');
}

export function formatLocalDate(value) {
    const date = parseUtcTimestamp(value);
    return Number.isNaN(date.getTime()) ? value || '-' : date.toLocaleDateString('zh-CN');
}

export function formatLocalTime(value) {
    const date = parseUtcTimestamp(value);
    if (Number.isNaN(date.getTime())) return value || '-';
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
}
