const DATE_ONLY_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

function digitsToEpochMs(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) {
        return null;
    }
    const digits = String(Math.trunc(Math.abs(n))).length;
    return digits >= 12 || n >= 1e12 ? n : n * 1000;
}

function formatMsUtc(ms) {
    const d = new Date(ms);
    const y = d.getUTCFullYear();
    const m = String(d.getUTCMonth() + 1).padStart(2, '0');
    const day = String(d.getUTCDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

function formatMsLocal(ms) {
    const d = new Date(ms);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

function parseDateOnlyLocalMs(value) {
    const m = DATE_ONLY_RE.exec(String(value).trim());
    if (!m) {
        return null;
    }
    const y = Number(m[1]);
    const mo = Number(m[2]);
    const day = Number(m[3]);
    const ms = new Date(y, mo - 1, day).getTime();
    return Number.isNaN(ms) ? null : ms;
}

// Parse inventory `date`-field values (YYYY-MM-DD or legacy Unix epoch seconds/ms) to epoch ms, or null.
export function parseInventoryDateMs(value) {
    if (value === '' || value == null) {
        return null;
    }
    if (typeof value === 'number' && Number.isFinite(value)) {
        return digitsToEpochMs(value);
    }
    const s = String(value).trim();
    if (/^\d+$/.test(s)) {
        return digitsToEpochMs(s);
    }
    const dateOnlyMs = parseDateOnlyLocalMs(s);
    if (dateOnlyMs != null) {
        return dateOnlyMs;
    }
    const parsed = Date.parse(s);
    return Number.isNaN(parsed) ? null : parsed;
}

// Format for display and `<input type="date">` (calendar date; never shifted by timezone).
export function formatInventoryDateValue(value) {
    if (value === '' || value == null) {
        return value == null ? '' : String(value);
    }
    const s = String(value).trim();
    if (DATE_ONLY_RE.test(s)) {
        return s;
    }
    if (/^\d+$/.test(s)) {
        const ms = digitsToEpochMs(s);
        return formatMsUtc(ms);
    }
    if (typeof value === 'number' && Number.isFinite(value)) {
        const ms = digitsToEpochMs(value);
        const digits = String(Math.trunc(Math.abs(value))).length;
        return digits >= 12 || value >= 1e12 ? formatMsLocal(ms) : formatMsUtc(ms);
    }
    const dateOnlyMs = parseDateOnlyLocalMs(s);
    if (dateOnlyMs != null) {
        return formatMsLocal(dateOnlyMs);
    }
    const parsed = Date.parse(s);
    if (Number.isNaN(parsed)) {
        return s;
    }
    return formatMsLocal(parsed);
}
