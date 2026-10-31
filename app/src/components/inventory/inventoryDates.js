const DATE_ONLY_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
/** Legacy inventory dates stored as Unix epoch seconds (not arbitrary digit strings). */
const EPOCH_SECONDS_RE = /^\d{9,10}(\.0+)?$/;

function digitsToEpochMs(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) {
        return null;
    }
    return n * 1000;
}

function isEpochSecondsNumber(value) {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
        return false;
    }
    const digits = String(Math.trunc(Math.abs(value))).length;
    return digits >= 9 && digits <= 10;
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

/** Today's calendar date in the local timezone as YYYY-MM-DD. */
export function localTodayYmd() {
    return formatMsLocal(Date.now());
}

// Parse inventory `date`-field values (YYYY-MM-DD or legacy Unix epoch seconds) to epoch ms, or null.
export function parseInventoryDateMs(value) {
    if (value === '' || value == null) {
        return null;
    }
    if (isEpochSecondsNumber(value)) {
        return digitsToEpochMs(value);
    }
    const s = String(value).trim();
    if (EPOCH_SECONDS_RE.test(s)) {
        return digitsToEpochMs(s);
    }
    const dateOnlyMs = parseDateOnlyLocalMs(s);
    if (dateOnlyMs != null) {
        return dateOnlyMs;
    }
    if (/^\d+$/.test(s)) {
        return null;
    }
    const parsed = Date.parse(s);
    return Number.isNaN(parsed) ? null : parsed;
}

// Format for display and `<input type="date">` (calendar date; never shifted by timezone).
export function formatInventoryDateValue(value) {
    if (value === '' || value == null) {
        return value == null ? '' : String(value);
    }
    if (typeof value === 'number' && Number.isFinite(value)) {
        // A YAML number is either legacy epoch seconds or something we can't interpret; never treat it as epoch
        // milliseconds, so `2030` and `'2030'` display the same.
        return isEpochSecondsNumber(value) ? formatMsUtc(digitsToEpochMs(value)) : String(value);
    }
    const s = String(value).trim();
    if (DATE_ONLY_RE.test(s)) {
        return s;
    }
    if (EPOCH_SECONDS_RE.test(s)) {
        return formatMsUtc(digitsToEpochMs(s));
    }
    if (/^\d+$/.test(s)) {
        return s;
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
