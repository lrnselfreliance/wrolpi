import {all, create} from "mathjs";

// A scoped mathjs instance so inventory unit handling never affects the global mathjs (used elsewhere).  All
// inventory quantity math (conversion + aggregation) lives here — the backend stores quantities as opaque
// {magnitude, unit} strings and does no unit math.
const math = create(all);

// Units offered in the unit dropdown for `quantity` fields, grouped by physical dimension.  Names are mathjs unit
// names (note: mathjs uses `lb`/`lbs`/`lbm`, NOT `pound`).
export const UNIT_GROUPS = [
    {label: 'Mass', units: ['lb', 'oz', 'kg', 'g', 'mg', 'ton', 'tonne', 'grain']},
    {label: 'Volume', units: ['gallon', 'quart', 'pint', 'cup', 'floz', 'liter', 'ml', 'tablespoon', 'teaspoon']},
    {label: 'Length', units: ['inch', 'foot', 'yard', 'mile', 'meter', 'cm', 'mm', 'km']},
];

export const ALL_UNITS = UNIT_GROUPS.flatMap(g => g.units);

// Compaction ladders (ascending): a summed quantity is displayed in the largest unit on a compatible ladder where
// the magnitude is still >= 1 (mirrors the old backend `compact_unit`, e.g. 2000 lb -> 1 ton, 16 oz + 1 lb -> 2 lb).
const COMPACTION_LADDERS = [
    ['oz', 'lb', 'ton'],
];

// Parse a magnitude + unit into a mathjs Unit, or null if it can't be parsed (blank value, or a non-standard unit
// like "can"/"each" the user typed).  Note: Number('') === 0, so blank strings are rejected explicitly.
function toUnit(value, unit) {
    if (value === '' || value === null || value === undefined) {
        return null;
    }
    if (typeof value === 'string' && value.trim() === '') {
        return null;
    }
    const n = Number(value);
    if (!Number.isFinite(n) || !unit) {
        return null;
    }
    try {
        return math.unit(n, unit);
    } catch {
        return null;
    }
}

// Convert a {value, unit} to another unit.  Returns a number, or null when incompatible/unparseable.
export function convert(value, fromUnit, toUnitName) {
    const u = toUnit(value, fromUnit);
    if (!u) {
        return null;
    }
    try {
        return u.toNumber(toUnitName);
    } catch {
        return null;
    }
}

/**
 * Estimate how many items a lot contains from a total weight and a single item's weight:
 * count = round(total / unit), converting `total` into the unit-weight's unit first (so e.g. a 2 kg total and a
 * 5 g unit weight give 400).  The result is rounded to a whole number — you can't have 403.7 nails.  A total below
 * one item (or zero) gives 0, not null, so a corrected-down weight doesn't leave a stale count behind.
 * Returns null when a weight is blank, the unit weight is non-positive, or the units are incompatible.
 */
export function countByWeight(total, totalUnit, unitWeight, unitWeightUnit) {
    const each = Number(unitWeight);
    if (!(each > 0) || total === '' || total === null || total === undefined) {
        return null;
    }
    let totalInEachUnit;
    if (totalUnit && unitWeightUnit && totalUnit !== unitWeightUnit) {
        totalInEachUnit = convert(total, totalUnit, unitWeightUnit);   // null if incompatible
    } else if ((totalUnit || '') === (unitWeightUnit || '')) {
        // Same unit (or both unitless) — divide the raw magnitudes.
        const t = Number(total);
        totalInEachUnit = Number.isFinite(t) ? t : null;
    } else {
        // One side has a unit and the other doesn't — can't safely divide, so refuse to guess.
        return null;
    }
    if (totalInEachUnit === null || !Number.isFinite(totalInEachUnit) || totalInEachUnit < 0) {
        return null;
    }
    return Math.round(totalInEachUnit / each);   // 0 for a sub-unit (or zero) total
}

function compact(unitValue) {
    // unitValue is a mathjs Unit.  On a compatible ladder, pick the largest unit where the value is still >= 1.
    for (const ladder of COMPACTION_LADDERS) {
        let compatible = false;
        try {
            unitValue.toNumber(ladder[0]);
            compatible = true;
        } catch {
            // Not this ladder's dimension.
        }
        if (!compatible) {
            continue;
        }
        let chosen = ladder[0];
        for (const u of ladder) {
            if (unitValue.toNumber(u) >= 1) {
                chosen = u;
            } else {
                break;
            }
        }
        return math.unit(unitValue.toNumber(chosen), chosen);
    }
    return unitValue;
}

function roundNumber(n) {
    return Math.round(n * 1e5) / 1e5;
}

/**
 * Sum a list of {value, unit} entries, combining compatible units and compacting the result.
 *
 * Returns {totals: [{magnitude, unit}], unitlessCount}:
 *   - `totals` is one entry per distinct physical dimension (mass, volume, ...), each summed and compacted.
 *   - `unitlessCount` counts entries with no/blank/non-standard unit but a numeric value (e.g. "5 cans"),
 *     so the UI can still show a plain count.
 */
export function sumQuantities(entries) {
    const buckets = [];  // [{unit: mathjsUnit, sample: unitName}]
    let unitlessTotal = 0;
    let hasUnitless = false;

    for (const {value, unit} of entries) {
        const parsed = toUnit(value, unit);
        if (!parsed) {
            const n = Number(value);
            if (Number.isFinite(n) && n !== 0) {
                unitlessTotal += n;
                hasUnitless = true;
            }
            continue;
        }
        // Find an existing bucket with a matching dimension.
        const bucket = buckets.find(b => {
            try {
                return b.unit.equalBase(parsed);
            } catch {
                return false;
            }
        });
        if (bucket) {
            bucket.unit = math.add(bucket.unit, parsed);
        } else {
            buckets.push({unit: parsed});
        }
    }

    const totals = buckets.map(b => {
        const compacted = compact(b.unit);
        const {value, unit} = compacted.toJSON();
        return {magnitude: roundNumber(value), unit};
    });

    return {totals, unitlessCount: hasUnitless ? roundNumber(unitlessTotal) : null};
}

// Format the result of sumQuantities into a short human string, e.g. "1.5 lb + 2 gallon (3 unitless)".
export function formatTotals(summed) {
    const parts = (summed.totals || []).map(t => `${t.magnitude} ${t.unit}`);
    if (summed.unitlessCount) {
        parts.push(`${summed.unitlessCount} unitless`);
    }
    return parts.length ? parts.join(' + ') : '—';
}
