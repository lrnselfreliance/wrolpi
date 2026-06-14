import React from "react";
import {GridColumn, Input, Label, TableBody, TableCell, TableRow} from "semantic-ui-react";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {Form, Header, Table} from "../Theme";
import {InfoPopup, roundDigits, useLocalStorage} from "../Common";
import {formatDuration} from "./WaterCalculator";

// Pure calculation functions for the Ration (food storage) estimate.
//
// The model: an inventory holds food items, each with a per-unit calorie value and a count.  Total stored calories
// divided by the household's daily calorie demand gives how many days the food lasts.

// Total calories stored across all items: sum of (calories * count) per item.  A blank/zero count is treated as 1
// (a single unit), and a blank calorie value contributes nothing.
export function totalCalories(items, caloriesKey, countKey) {
    if (!items || !caloriesKey) {
        return 0;
    }
    return items.reduce((sum, item) => {
        const calories = Number(item[caloriesKey]);
        if (!(calories > 0)) {
            return sum;
        }
        const rawCount = countKey ? Number(item[countKey]) : 1;
        const count = rawCount > 0 ? rawCount : 1;
        return sum + calories * count;
    }, 0);
}

// Household daily calorie demand: sum of per-category counts times per-category rates.
export function dailyCalorieDemand(counts, rates) {
    const term = (count, rate) => {
        const c = Number(count), r = Number(rate);
        return (c > 0 && r > 0) ? c * r : 0;
    };
    return term(counts.men, rates.men)
        + term(counts.women, rates.women)
        + term(counts.children, rates.children);
}

// Days the stored calories last at the given daily demand.  Returns null for impossible inputs.
export function daysOfFood(total, dailyDemand) {
    if (!(total > 0) || !(dailyDemand > 0)) {
        return null;
    }
    return total / dailyDemand;
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

// Per-person daily calorie needs, by activity level.  Adult figures are representative working-age values
// (ages 19-60) from the Dietary Guidelines for Americans 2020-2025, Appendix 2, Table A2-2 ("Estimated Calorie
// Needs per Day, by Age, Sex, and Physical Activity Level"), corroborated by the Merck Manuals table.  The single
// "children" figure is a mid-childhood approximation (the DGA child range is very wide, 1,000-3,200).  "Survival"
// is a short-term emergency ration floor, below maintenance.  All values are editable.
export const RATION_PRESETS = {
    sedentary: {
        label: 'Sedentary',
        description: 'Everyday-living activity only',
        rates: {men: 2400, women: 1800, children: 1600},
    },
    moderate: {
        label: 'Moderately Active',
        description: '~1.5–3 mi/day walking',
        rates: {men: 2600, women: 2000, children: 1800},
    },
    active: {
        label: 'Active',
        description: '>3 mi/day walking + activity',
        rates: {men: 3000, women: 2400, children: 2000},
    },
    survival: {
        label: 'Survival',
        description: 'Emergency ration floor (~1,200–1,500/adult)',
        rates: {men: 1500, women: 1200, children: 1200},
    },
};

const DEFAULT_PRESET = 'moderate';

const CATEGORY_META = [
    {key: 'men', label: 'Men', color: '#4477aa'},
    {key: 'women', label: 'Women', color: '#aa3377'},
    {key: 'children', label: 'Children', color: '#228833'},
];

const DEMAND_INFO = 'Per-person daily calorie needs come from the Dietary Guidelines for Americans 2020-2025 '
    + '(Appendix 2), by sex and physical activity level. Adult values are representative for ages 19-60; the '
    + 'children figure is a mid-childhood approximation since needs vary widely with age (1,000-3,200 kcal/day). '
    + 'The Survival preset is a short-term emergency ration floor, below maintenance. All values are editable — '
    + 'adjust the household and activity level to see how long the stored food lasts.';

function textColorFor(hex) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.6 ? '#000000' : '#ffffff';
}

function fmt(value, unit) {
    if (!Number.isFinite(value) || value <= 0) {
        return '—';
    }
    return unit ? `${roundDigits(value, 0)} ${unit}` : `${roundDigits(value, 0)}`;
}

/**
 * The household + preset controls and the days-of-food result.  Reused by the Ration calculator page and by the
 * inventory Summary (when the inventory has a `calories` field).  Household/preset selections are persisted under
 * shared localStorage keys, so adjusting them in one place carries to the other.
 */
export function RationEstimatePanel({items, caloriesKey, countKey}) {
    const [preset, setPreset] = useLocalStorage('ration_preset', DEFAULT_PRESET);
    const [counts, setCounts] = useLocalStorage('ration_counts', {men: '1', women: '1', children: ''});
    const [rates, setRates] = React.useState({...RATION_PRESETS[DEFAULT_PRESET].rates});

    React.useEffect(() => {
        // Fall back to the default preset if a stale/unknown key is persisted in localStorage.
        const p = RATION_PRESETS[preset] ?? RATION_PRESETS[DEFAULT_PRESET];
        setRates({...p.rates});
    }, [preset]);

    const total = totalCalories(items, caloriesKey, countKey);
    const daily = dailyCalorieDemand(counts, rates);
    const days = daysOfFood(total, daily);

    const inputProps = {fluid: true, type: 'number', onSelect: e => e.target.select(), autoComplete: 'off'};

    const countInput = ({key, label, color}) =>
        <Input {...inputProps} min={0} step={1} name={`count-${key}`} labelPosition='left' value={counts[key]}
               onChange={e => setCounts({...counts, [key]: e.target.value})}
               label={<Label style={{backgroundColor: color, color: textColorFor(color), borderColor: color}}>
                   {label}</Label>}/>;

    const rateInput = ({key, label, color}) =>
        <Input {...inputProps} min={0} step={50} name={`rate-${key}`} labelPosition='left' value={rates[key]}
               onChange={e => setRates({...rates, [key]: e.target.value})}
               label={<Label style={{backgroundColor: color, color: textColorFor(color), borderColor: color}}>
                   {label}</Label>}/>;

    return <Form>
        <Header as='h3'>People</Header>
        <Grid stackable columns={3}>
            {CATEGORY_META.map(meta => <GridColumn key={meta.key}>{countInput(meta)}</GridColumn>)}
        </Grid>

        <Header as='h3' style={{marginTop: '1em'}}>
            Daily Calories (per person) <InfoPopup content={DEMAND_INFO}/>
        </Header>
        <div style={{marginBottom: '1em'}}>
            {Object.entries(RATION_PRESETS).map(([key, p]) => (
                <button key={key} type='button' onClick={() => setPreset(key)} style={{
                    marginRight: '0.5em', padding: '0.4em 0.8em',
                    border: preset === key ? '2px solid #2185d0' : '1px solid #ccc',
                    background: preset === key ? '#e8f4fc' : 'white', borderRadius: '4px', cursor: 'pointer',
                }}>
                    <strong>{p.label}</strong> — {p.description}
                </button>
            ))}
        </div>
        <Grid stackable columns={3}>
            {CATEGORY_META.map(meta => <GridColumn key={meta.key}>{rateInput(meta)}</GridColumn>)}
        </Grid>

        <Table definition unstackable style={{marginTop: '1em'}}>
            <TableBody>
                <TableRow>
                    <TableCell width={6}>Total Stored Calories</TableCell>
                    <TableCell>{fmt(total, 'kcal')}</TableCell>
                </TableRow>
                <TableRow>
                    <TableCell>Daily Demand</TableCell>
                    <TableCell>{fmt(daily, 'kcal/day')}</TableCell>
                </TableRow>
                <TableRow>
                    <TableCell>Food Lasts</TableCell>
                    <TableCell>{days ? formatDuration(days) : '—'}</TableCell>
                </TableRow>
            </TableBody>
        </Table>
    </Form>;
}

// NOTE: the inventory-based "how long does my food last" estimate now lives only inside the inventory Summary
// (via RationEstimatePanel).  The standalone Calculators page is the generic FoodStorageCalculator instead.
