// Parse inventory `date`-field values (YYYY-MM-DD or legacy Unix epoch seconds/ms) to epoch ms, or null.
export function parseInventoryDateMs(value) {
    if (value === '' || value == null) {
        return null;
    }
    if (typeof value === 'number' && Number.isFinite(value)) {
        return value < 1e12 ? value * 1000 : value;
    }
    const s = String(value).trim();
    if (/^\d+$/.test(s)) {
        const n = Number(s);
        return n < 1e12 ? n * 1000 : n;
    }
    const parsed = Date.parse(s);
    return Number.isNaN(parsed) ? null : parsed;
}

// Format for display and `<input type="date">` (local calendar date).
export function formatInventoryDateValue(value) {
    const ms = parseInventoryDateMs(value);
    if (ms == null) {
        return value == null ? '' : String(value);
    }
    const d = new Date(ms);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}
