import {formatValue} from "./InventoryTable";

// Fields in display (column) order.
function orderedFields(fields) {
    return [...(fields || [])].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
}

// Quote a single CSV cell per RFC 4180: wrap in double-quotes (escaping internal quotes by doubling) when the value
// contains a comma, quote, or newline.
function escapeCell(value) {
    const s = value == null ? '' : String(value);
    return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/**
 * Build an RFC-4180 CSV string for an inventory: a header row of field labels followed by one row per item, using
 * the same value formatting as the on-screen table (quantity fields render as `<magnitude> <unit>`).
 */
export function toCSV(fields, items) {
    const cols = orderedFields(fields);
    const header = cols.map(f => escapeCell(f.label || f.key));
    const rows = (items || []).map(item => cols.map(f => escapeCell(formatValue(item, f))));
    return [header, ...rows].map(row => row.join(',')).join('\r\n');
}

// Filesystem-safe export filename derived from the inventory name (e.g. "Food Storage" -> "food-storage.csv").
export function inventoryExportFilename(name, ext) {
    const base = (name || 'inventory').trim().toLowerCase()
        .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'inventory';
    return `${base}.${ext}`;
}

// Trigger a browser download of `csv` as `filename`.  A UTF-8 BOM is prepended so spreadsheet apps (notably Excel)
// detect the encoding and render non-ASCII characters correctly.
export function downloadCSV(filename, csv) {
    const BOM = String.fromCharCode(0xFEFF);
    const blob = new Blob([BOM + csv], {type: 'text/csv;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    // The anchor must be attached to the document for click() to trigger a download in some browsers, and the
    // object URL must stay alive until the browser has started fetching it — so revoke on the next tick.
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 0);
}
