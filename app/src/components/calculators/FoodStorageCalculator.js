import React from "react";
import {GridColumn, Input, Label, TableBody, TableCell, TableFooter, TableHeader, TableHeaderCell, TableRow} from "semantic-ui-react";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {Form, Header, Segment, Table} from "../Theme";
import {InfoPopup, roundDigits, Toggle, useLocalStorage} from "../Common";
import {ThemeContext} from "../../contexts/contexts";

// Generic food-storage planner: given a household, estimate how much of each food category to store for a chosen
// duration.  Independent of any inventory (like the Water calculator).  Defaults are a common one-year-per-adult
// food-storage plan (lbs per person per year); all amounts are editable.

// Each person's share of one adult man's ration, as a percent.  Defaults are derived from the Dietary Guidelines
// for Americans 2020-2025 moderate-activity calorie needs (man ~2,600 / woman ~2,000 / child ~1,800 kcal/day),
// since food-storage quantities scale with energy needs.  Editable.
export const DEFAULT_SHARES = {men: 100, women: 77, children: 69};

const countNum = (v) => {
    const x = Number(v);
    return x > 0 ? x : 0;
};

// Raw head count.
export function totalPeople(counts) {
    return countNum(counts.men) + countNum(counts.women) + countNum(counts.children);
}

// Adult-man-equivalents: each person weighted by their ration share (%), so women and children need less.
export function adultEquivalents(counts, shares) {
    const share = (v) => Math.max(0, Number(v) || 0) / 100;
    return countNum(counts.men) * share(shares.men)
        + countNum(counts.women) * share(shares.women)
        + countNum(counts.children) * share(shares.children);
}

// Total amount of a category needed: per-person-per-year amount, scaled by people and the duration in months.
export function amountNeeded(perPersonPerYear, people, months) {
    const a = Number(perPersonPerYear), m = Number(months);
    if (!(a > 0) || !(people > 0) || !(m > 0)) {
        return 0;
    }
    return a * people * (m / 12);
}

// Default per-person, per-year storage amounts (lbs), calibrated to a one-year supply for one adult man.
// Auxiliary foods and spices/condiments have no standard weight, so they default to 0 for the user to fill in.
export const FOOD_CATEGORIES = [
    {key: 'grains', label: 'Grains', perYear: 300},
    {key: 'legumes', label: 'Legumes', perYear: 60},
    {key: 'fruits', label: 'Fruits', perYear: 185},
    {key: 'vegetables', label: 'Vegetables', perYear: 185},
    {key: 'powdered_milk', label: 'Powdered Milk', perYear: 16},
    {key: 'cooking_oil', label: 'Cooking Oil', perYear: 25},
    {key: 'meats', label: 'Meats / Meat Substitutes', perYear: 20},
    {key: 'sugar', label: 'Sugar or Honey', perYear: 60},
    {key: 'salt', label: 'Salt', perYear: 8},
    {key: 'cooking_essentials', label: 'Cooking Essentials', perYear: 8},
    {key: 'auxiliary', label: 'Auxiliary Foods', perYear: 0},
    {key: 'condiments', label: 'Spices / Condiments', perYear: 0},
];

const DEFAULT_AMOUNTS = Object.fromEntries(FOOD_CATEGORIES.map(c => [c.key, String(c.perYear)]));

export const KG_PER_LB = 0.45359237;

// Convert all per-person amounts between lb and kg (used when the unit toggle flips), preserving the user's edits
// rather than resetting to defaults.
export function convertAmounts(amounts, toMetric) {
    const factor = toMetric ? KG_PER_LB : 1 / KG_PER_LB;
    const out = {};
    for (const [key, value] of Object.entries(amounts)) {
        out[key] = (value === '' || value == null) ? '' : String(roundDigits(Number(value) * factor, 2));
    }
    return out;
}

// Duration slider stops (months): monthly to a year, then to three years.
export const MONTH_STOPS = [1, 2, 3, 6, 9, 12, 18, 24, 36];

export function formatMonths(months) {
    const m = Math.round(Number(months));
    if (!(m > 0)) {
        return '—';
    }
    if (m % 12 === 0) {
        const y = m / 12;
        return `${y} year${y === 1 ? '' : 's'}`;
    }
    return `${m} month${m === 1 ? '' : 's'}`;
}

const CATEGORY_INFO = 'Default amounts are a one-year food-storage supply for one adult man (pounds per person '
    + 'per year). Totals scale by each person\'s ration share (women and children need less — see the shares '
    + 'above), and by the duration. Edit any amount to match your own plan. Water is not included — use the Water '
    + 'Storage calculator for that.';

const SHARES_INFO = 'Each person\'s share of one adult man\'s ration. Defaults follow the Dietary Guidelines for '
    + 'Americans 2020-2025 moderate-activity calorie needs (man ~2,600, woman ~2,000, child ~1,800 kcal/day) — '
    + 'food storage scales with calories. Children vary widely by age, so adjust as needed.';

const PEOPLE_META = [
    {key: 'men', label: 'Men', color: '#4477aa'},
    {key: 'women', label: 'Women', color: '#aa3377'},
    {key: 'children', label: 'Children', color: '#228833'},
];

function textColorFor(hex) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.6 ? '#000000' : '#ffffff';
}

function fmt(value, unit) {
    return Number.isFinite(value) && value > 0 ? `${roundDigits(value, 1)} ${unit}` : '—';
}

export function FoodStorageCalculator() {
    const [counts, setCounts] = useLocalStorage('food_storage_counts', {men: '1', women: '1', children: ''});
    const [shares, setShares] = useLocalStorage('food_storage_shares', DEFAULT_SHARES);
    const [monthsIndex, setMonthsIndex] = useLocalStorage('food_storage_months_index', MONTH_STOPS.indexOf(12));
    const [amounts, setAmounts] = useLocalStorage('food_storage_amounts', DEFAULT_AMOUNTS);
    const [metric, setMetric] = useLocalStorage('food_storage_metric', false);
    const {t} = React.useContext(ThemeContext);

    const unit = metric ? 'kg' : 'lb';
    // Convert the editable amounts when switching units so the user keeps their numbers.
    const toggleMetric = () => {
        setAmounts(prev => convertAmounts(prev, !metric));
        setMetric(!metric);
    };

    const equivalents = adultEquivalents(counts, shares);
    const monthStop = Math.min(Math.max(0, monthsIndex), MONTH_STOPS.length - 1);
    const months = MONTH_STOPS[monthStop];

    const inputProps = {fluid: true, type: 'number', min: 0, onSelect: e => e.target.select(), autoComplete: 'off'};

    const labelStyle = (color) =>
        ({backgroundColor: color, color: textColorFor(color), borderColor: color});

    const countInput = ({key, label, color}) =>
        <Input {...inputProps} step={1} name={`count-${key}`} labelPosition='left' value={counts[key]}
               onChange={e => setCounts({...counts, [key]: e.target.value})}
               label={<Label style={labelStyle(color)}>{label}</Label>}/>;

    const shareInput = ({key, label, color}) =>
        <Input {...inputProps} step={1} name={`share-${key}`} labelPosition='left' value={shares[key]}
               onChange={e => setShares({...shares, [key]: e.target.value})}
               label={<Label style={labelStyle(color)}>{label}</Label>}/>;

    const rows = FOOD_CATEGORIES.map(c => {
        const perYear = amounts[c.key] ?? '';
        const total = amountNeeded(perYear, equivalents, months);
        return {...c, perYear, total};
    });
    const grandTotal = rows.reduce((s, r) => s + r.total, 0);

    return <Form>
        <Header as='h1'>Food Storage</Header>
        <p {...t}>Estimate how much food to store for your household over time.</p>

        <div style={{marginBottom: '1em'}}>
            <Toggle label={metric ? 'Metric (kg)' : 'Imperial (lb)'} checked={metric} onChange={toggleMetric}/>
        </div>

        <Header as='h3'>People</Header>
        <Grid stackable columns={3}>
            {PEOPLE_META.map(meta => <GridColumn key={meta.key}>{countInput(meta)}</GridColumn>)}
        </Grid>

        <Header as='h4' style={{marginTop: '1em', marginBottom: '0.5em'}}>
            Ration share (% of an adult man) <InfoPopup content={SHARES_INFO}/>
        </Header>
        <Grid stackable columns={3}>
            {PEOPLE_META.map(meta => <GridColumn key={meta.key}>{shareInput(meta)}</GridColumn>)}
        </Grid>
        <p {...t} style={{...t.style, marginTop: '0.5em', opacity: 0.8}}>
            ≈ {roundDigits(equivalents, 2)} adult-equivalent{equivalents === 1 ? '' : 's'}
        </p>

        <Header as='h3' style={{marginTop: '1em'}}>How long?</Header>
        <div style={{padding: '0 0.5em'}}>
            <input type='range' min={0} max={MONTH_STOPS.length - 1} step={1} value={monthStop}
                   aria-label='Duration' onChange={e => setMonthsIndex(Number(e.target.value))}
                   style={{width: '100%'}}/>
            <Header as='h2' textAlign='center' style={{marginTop: '0.25em'}}>{formatMonths(months)}</Header>
        </div>

        <Header as='h3' style={{marginTop: '1em'}}>
            Amounts ({unit} per person per year) <InfoPopup content={CATEGORY_INFO}/>
        </Header>
        <Segment>
            <Table unstackable>
                <TableHeader>
                    <TableRow>
                        <TableHeaderCell width={7}>Category</TableHeaderCell>
                        <TableHeaderCell width={5}>{unit === 'kg' ? 'Kg' : 'Lbs'} / person / year</TableHeaderCell>
                        <TableHeaderCell width={4}>Total needed</TableHeaderCell>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {rows.map(r => <TableRow key={r.key}>
                        <TableCell>{r.label}</TableCell>
                        <TableCell>
                            <Input fluid type='number' min={0} value={r.perYear}
                                   aria-label={`${r.label} per person per year`}
                                   onChange={e => setAmounts({...amounts, [r.key]: e.target.value})}/>
                        </TableCell>
                        <TableCell>{fmt(r.total, unit)}</TableCell>
                    </TableRow>)}
                </TableBody>
                <TableFooter>
                    <TableRow>
                        <TableHeaderCell>Total</TableHeaderCell>
                        <TableHeaderCell/>
                        <TableHeaderCell>{fmt(grandTotal, unit)}</TableHeaderCell>
                    </TableRow>
                </TableFooter>
            </Table>
        </Segment>
    </Form>;
}
