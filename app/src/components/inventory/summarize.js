import {formatTotals, sumQuantities} from "./units";

// Field-role detection and client-side aggregation for an inventory.  This is the single source of truth shared by
// the Summary tab, the PDF export, and the ration calculator — the backend stores raw items and does no aggregation.

// Fields the summary can group by (categorical), in schema order.
export function groupFieldsOf(fields) {
    return (fields || []).filter(f => ['text', 'select', 'location'].includes(f.type));
}

// Fields the summary can sum, in schema order: quantity (unit-aware), plus number and calories (plain totals).
export function summableFieldsOf(fields) {
    return (fields || []).filter(f => ['quantity', 'number', 'calories'].includes(f.type));
}

// Default grouping: prefer Category (so grains/dairy/etc. are visible), else the first group field.
export function defaultGroupKey(fields) {
    const groups = groupFieldsOf(fields);
    return (groups.find(f => f.key === 'category') || groups[0])?.key;
}

// Default field to sum: the first quantity field, else the first number, else the first calories field.
export function defaultSumKey(fields) {
    const summable = summableFieldsOf(fields);
    for (const type of ['quantity', 'number', 'calories']) {
        const f = summable.find(s => s.type === type);
        if (f) {
            return f.key;
        }
    }
    return undefined;
}

// The calories field is detected by its dedicated `calories` type (falling back to a field literally keyed
// "calories" for inventories created before the type existed).
export function findCaloriesKey(fields) {
    const byType = (fields || []).find(f => f.type === 'calories');
    if (byType) {
        return byType.key;
    }
    const legacy = (fields || []).find(f => f.key === 'calories' && f.type === 'number');
    return legacy ? legacy.key : null;
}

// The count multiplier: prefer a number field keyed "count", else the first number field, else none (treat as 1).
export function findCountKey(fields) {
    const count = (fields || []).find(f => f.type === 'number' && f.key === 'count');
    if (count) {
        return count.key;
    }
    const firstNumber = (fields || []).find(f => f.type === 'number');
    return firstNumber ? firstNumber.key : null;
}

// Parse an item's field value into a finite number, or null when blank/non-numeric.
function numericValue(item, key) {
    const raw = item[key];
    if (raw === '' || raw == null) {
        return null;
    }
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
}

/**
 * Group items by `groupKey` and aggregate each group, returning rows sorted by group name.
 *
 * The "Total" depends on the summed field's type (looked up in `fields`):
 *   - `quantity`         → count-aware, unit-compacted (Σ per-container size × count), e.g. "110 lb".
 *   - `number`/`calories`→ a plain column total of the raw values (Σ value, NOT × count), e.g. "280".
 * The dedicated `calories` total in each row stays count-aware (Σ per-unit calories × count), independent of the
 * chosen sum field.
 *
 * Each row: {name, count, total, totalSort, calories}.  Returns [] when there is no group field.  A blank/zero
 * count is treated as a single unit (matches the ration estimate's convention).
 */
export function summarizeInventory(items, {fields, groupKey, sumKey, countKey, caloriesKey}) {
    if (!groupKey) {
        return [];
    }
    const sumType = (fields || []).find(f => f.key === sumKey)?.type;
    const isQuantitySum = sumType === 'quantity';
    const unitsOf = (item) => {
        const c = countKey ? Number(item[countKey]) : 1;
        return c > 0 ? c : 1;
    };
    const groups = {};
    (items || []).forEach(item => {
        const key = item[groupKey] || '(none)';
        if (!groups[key]) {
            groups[key] = {entries: [], plainTotal: 0, hasPlain: false, count: 0, calories: 0};
        }
        const group = groups[key];
        group.count += 1;
        const units = unitsOf(item);
        if (sumKey && isQuantitySum) {
            const size = Number(item[sumKey]);
            group.entries.push({
                value: (size > 0 ? size : 0) * units,
                unit: item[`${sumKey}_unit`],
            });
        } else if (sumKey) {
            // number / calories: a plain sum of the column's raw values.
            const n = numericValue(item, sumKey);
            if (n !== null) {
                group.plainTotal += n;
                group.hasPlain = true;
            }
        }
        if (caloriesKey) {
            const cal = Number(item[caloriesKey]);
            if (cal > 0) {
                group.calories += cal * units;
            }
        }
    });
    return Object.entries(groups).map(([name, g]) => {
        let total, totalSort;
        if (sumKey && isQuantitySum) {
            const summed = sumQuantities(g.entries);
            total = formatTotals(summed);
            totalSort = (summed.totals || []).reduce((s, x) => s + x.magnitude, 0) + (summed.unitlessCount || 0);
        } else if (sumKey) {
            total = g.hasPlain ? g.plainTotal.toLocaleString() : '—';
            totalSort = g.plainTotal;
        } else {
            total = '—';
            totalSort = 0;
        }
        return {name, count: g.count, total, totalSort, calories: g.calories};
    }).sort((a, b) => a.name.localeCompare(b.name));
}

// Return a copy of summary rows sorted by the given column (`name`|`count`|`total`|`calories`) and direction.
export function sortSummaryRows(rows, sort) {
    const compare = (a, b) => {
        const r = sort.key === 'name' ? a.name.localeCompare(b.name)
            : sort.key === 'count' ? a.count - b.count
                : sort.key === 'total' ? a.totalSort - b.totalSort
                    : a.calories - b.calories;
        return sort.dir === 'desc' ? -r : r;
    };
    return [...rows].sort(compare);
}
