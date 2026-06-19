import {countByWeight} from "./units";

// "Count by weight" computed fields.  A Count (number) field can carry metadata linking it to a Total Weight and a
// Unit Weight field; the table then fills the count automatically from the two weights (count = round(total / unit)).
// The metadata is a plain property on the field dict, so it round-trips through the config/API unchanged.

export const COUNT_BY_WEIGHT = 'count_by_weight';

// The fields the "Count by weight" preset creates.
const UNIT_WEIGHT = {key: 'unit_weight', label: 'Unit Weight', type: 'quantity', unit: 'g'};
const TOTAL_WEIGHT = {key: 'total_weight', label: 'Total Weight', type: 'quantity', unit: 'g'};
const COUNT_COMPUTE = {kind: COUNT_BY_WEIGHT, total: 'total_weight', unit: 'unit_weight'};

// True when a field is a Count computed from weights.
export function isCountByWeight(field) {
    return !!field && field.compute && field.compute.kind === COUNT_BY_WEIGHT;
}

/**
 * Add the "Count by weight" fields to a schema: Unit Weight and Total Weight (quantity, grams), plus a Count that
 * is tagged as computed.  An existing `count` field is linked in place (so a Tool/Fastener inventory's Count just
 * becomes computed) rather than duplicated; existing weight fields are left untouched.  Returns a new field list.
 */
export function addCountByWeightFields(fields) {
    const list = (fields || []).map(f => ({...f}));
    const has = (key) => list.some(f => f.key === key);

    if (!has(UNIT_WEIGHT.key)) {
        list.push({...UNIT_WEIGHT});
    }
    if (!has(TOTAL_WEIGHT.key)) {
        list.push({...TOTAL_WEIGHT});
    }
    const existingCount = list.find(f => f.key === 'count');
    if (existingCount) {
        existingCount.compute = {...COUNT_COMPUTE};
        if (existingCount.type !== 'number') {
            existingCount.type = 'number';
        }
    } else {
        list.push({key: 'count', label: 'Count', type: 'number', compute: {...COUNT_COMPUTE}});
    }
    return list;
}

/**
 * The count-by-weight configs present in a schema, each resolved to the weight fields' keys and default units:
 * [{countKey, totalKey, unitKey, totalUnit, unitUnit}].  Skips configs whose referenced weight fields are missing.
 */
export function computedCountConfigs(fields) {
    return (fields || [])
        .filter(isCountByWeight)
        .map(f => {
            const totalField = (fields || []).find(x => x.key === f.compute.total);
            const unitField = (fields || []).find(x => x.key === f.compute.unit);
            if (!totalField || !unitField) {
                return null;
            }
            return {
                countKey: f.key,
                totalKey: totalField.key,
                unitKey: unitField.key,
                totalUnit: totalField.unit || '',
                unitUnit: unitField.unit || '',
            };
        })
        .filter(Boolean);
}

/**
 * Recompute computed counts on an item after its field `changedKey` changed, mutating and returning the item.
 * Only acts when the change was to one of a count's weight inputs (value or unit), so a hand-typed count survives
 * edits to unrelated fields and is only touched when a weight actually changes.  When a weight changes, the count
 * always reflects the new reality: it is set to the computed value (0 included) when both weights are present, or
 * cleared when they can't produce one (a weight blanked, incompatible units) — so a stale count can never persist
 * against edited weights.
 */
export function applyComputedCounts(item, configs, changedKey) {
    (configs || []).forEach(c => {
        const triggers = [c.totalKey, c.unitKey, `${c.totalKey}_unit`, `${c.unitKey}_unit`];
        if (!triggers.includes(changedKey)) {
            return;
        }
        const count = countByWeight(
            item[c.totalKey], item[`${c.totalKey}_unit`] || c.totalUnit,
            item[c.unitKey], item[`${c.unitKey}_unit`] || c.unitUnit,
        );
        item[c.countKey] = count === null ? '' : String(count);
    });
    return item;
}
