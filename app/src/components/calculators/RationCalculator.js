import React from "react";
import {GridColumn, Input, Label, TableBody, TableCell, TableHeader, TableHeaderCell, TableRow} from "semantic-ui-react";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {Button, Form, Header, Icon, Table} from "../Theme";
import {InfoPopup, roundDigits, useLocalStorage} from "../Common";
import {formatDuration} from "./WaterCalculator";
import {findNameKey, planSupplyPurchase} from "../inventory/summarize";
import {downloadCSV, inventoryExportFilename, shoppingListCSV} from "../inventory/inventoryExport";
import {ThemeContext} from "../../contexts/contexts";
// Field-role detection lives in inventory/summarize.js (single source of truth); re-exported here for back-compat.
export {findCaloriesKey, findCountKey} from "../inventory/summarize";

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
export function RationEstimatePanel({name, items, fields, caloriesKey, countKey}) {
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

        <SupplyPlan name={name} items={items} fields={fields} caloriesKey={caloriesKey} countKey={countKey}
                    currentDays={days} total={total} daily={daily}/>
    </Form>;
}

// Print only the supply-plan shopping list (not the whole-inventory print block): toggle a body class that the
// `@media print` rules use to pick which printable block is visible, then open the print dialog.
function printShoppingList() {
    document.body.classList.add('printing-shopping');
    let timer;
    const cleanup = () => {
        clearTimeout(timer);   // ensure the backstop can't fire later and clear the class during a new print
        window.removeEventListener('afterprint', cleanup);
        document.body.classList.remove('printing-shopping');
    };
    window.addEventListener('afterprint', cleanup, {once: true});
    window.print();
    // Backstop in case afterprint never fires (cancelled above once afterprint runs), so a later whole-inventory
    // print isn't stuck in shopping mode.
    timer = setTimeout(cleanup, 1000);
}

// Length of a "month" used for the supply plan, matching formatDuration()'s 30-day months so the slider label and
// the duration text agree.
const PLAN_MONTH_DAYS = 30;

const PLAN_INFO = 'Drag the slider to a target duration longer than your current estimate to see what to buy. '
    + 'Your whole inventory is scaled up proportionally — every item grows by the same factor so the mix stays '
    + 'balanced — and any split package is rounded up to a whole one. The projection assumes you keep the same '
    + 'variety of food and the same household/activity settings above.';

/**
 * Extrapolation: a slider to pick a target duration longer than the current ration estimate, and a shopping list of
 * the additional packages to buy to reach it (the inventory scaled up proportionally — see planSupplyPurchase).
 */
function SupplyPlan({name, items, fields, caloriesKey, countKey, currentDays, total, daily}) {
    const {t} = React.useContext(ThemeContext);
    const nameKey = findNameKey(fields);

    const currentMonths = (currentDays || 0) / PLAN_MONTH_DAYS;
    const minMonths = Math.max(1, Math.ceil(currentMonths));
    const maxMonths = minMonths + 24;
    const [targetMonths, setTargetMonths] = React.useState(minMonths);
    // Keep the target within range as the estimate shifts (editing the household above moves the current duration).
    React.useEffect(() => {
        setTargetMonths(m => Math.min(Math.max(m, minMonths), maxMonths));
    }, [minMonths, maxMonths]);
    // Default to largest purchase first; clicking a header re-sorts.
    const [sort, setSort] = React.useState({key: 'additional', dir: 'desc'});
    const toggleSort = (key) => setSort(prev =>
        prev.key === key
            ? {key, dir: prev.dir === 'asc' ? 'desc' : 'asc'}
            : {key, dir: key === 'name' ? 'asc' : 'desc'});

    if (!(currentDays > 0)) {
        return null;   // No usable estimate yet (no calories or no household) — nothing to extrapolate from.
    }

    const targetDays = targetMonths * PLAN_MONTH_DAYS;
    const scale = targetDays / currentDays;
    const {rows, addedCalories} = planSupplyPurchase(items, {countKey, nameKey, caloriesKey, scale});
    const projectedDays = daily > 0 ? (total + addedCalories) / daily : null;
    const totalToBuy = rows.reduce((sum, r) => sum + r.additional, 0);

    const sortedRows = [...rows].sort((a, b) => {
        const r = sort.key === 'name' ? a.name.localeCompare(b.name) : a[sort.key] - b[sort.key];
        return sort.dir === 'desc' ? -r : r;
    });
    const sortDir = (key) => sort.key === key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined;
    const headerCell = (key, label) =>
        <TableHeaderCell sorted={sortDir(key)} onClick={() => toggleSort(key)} style={{cursor: 'pointer'}}>
            {label}
        </TableHeaderCell>;

    return <div style={{marginTop: '2em'}}>
        <Header as='h3'>Plan More Supply <InfoPopup content={PLAN_INFO}/></Header>
        {!countKey
            ? <p {...t}>Add a <strong>Count</strong> field to this inventory to plan purchases.</p>
            : <>
                <div style={{padding: '0 0.5em'}}>
                    <input type='range' min={minMonths} max={maxMonths} step={1} value={targetMonths}
                           aria-label='Target duration (months)' style={{width: '100%'}}
                           onChange={e => setTargetMonths(Number(e.target.value))}/>
                    <Header as='h2' textAlign='center' style={{marginTop: '0.25em'}}>
                        Target: {formatDuration(targetDays)}
                    </Header>
                    <p {...t} style={{...t.style, textAlign: 'center', opacity: 0.8}}>
                        Currently {formatDuration(currentDays)}
                    </p>
                </div>

                {rows.length === 0
                    ? <p {...t}>Drag the slider above your current estimate to see a shopping list.</p>
                    : <>
                        <Table celled unstackable sortable>
                            <TableHeader>
                                <TableRow>
                                    {headerCell('name', 'Item')}
                                    {headerCell('current', 'Have')}
                                    {headerCell('additional', 'Buy')}
                                    {headerCell('target', 'New Total')}
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {sortedRows.map((r, i) => <TableRow key={`${r.name}-${i}`}>
                                    <TableCell>{r.name}</TableCell>
                                    <TableCell>{r.current}</TableCell>
                                    <TableCell><strong>+{r.additional}</strong></TableCell>
                                    <TableCell>{r.target}</TableCell>
                                </TableRow>)}
                            </TableBody>
                        </Table>
                        <p {...t}>
                            Buy <strong>{totalToBuy.toLocaleString()}</strong> additional package{totalToBuy === 1 ? '' : 's'}
                            {' '}across <strong>{rows.length}</strong> item{rows.length === 1 ? '' : 's'}
                            {projectedDays ? <> to reach about <strong>{formatDuration(projectedDays)}</strong> of food.</> : '.'}
                        </p>

                        <Button primary
                                onClick={() => downloadCSV(
                                    inventoryExportFilename(`${name || 'inventory'} shopping list`, 'csv'),
                                    shoppingListCSV(sortedRows))}>
                            <Icon name='download'/> Download CSV
                        </Button>
                        <Button onClick={printShoppingList}>
                            <Icon name='print'/> Print / Save as PDF
                        </Button>

                        {/* Hidden printable block — `printShoppingList` makes this the only thing printed. */}
                        <ShoppingListPrint name={name} rows={sortedRows}
                                           targetText={formatDuration(targetDays)}
                                           currentText={formatDuration(currentDays)}/>
                    </>}
            </>}
    </div>;
}

// Printable rendering of just the shopping list (no inventory or summary), shown only when printing via the
// `body.printing-shopping` toggle.  Reuses the `.inventory-print` styling for headings and the table.
function ShoppingListPrint({name, rows, targetText, currentText}) {
    return <div className='inventory-print shopping-print'>
        <h1>{name || 'Inventory'} — Shopping List</h1>
        <p className='inventory-print-meta'>
            Target {targetText} (currently {currentText}) · {rows.length} item{rows.length === 1 ? '' : 's'} to buy
        </p>
        <table>
            <thead>
                <tr><th>Item</th><th>Have</th><th>Buy</th><th>New Total</th></tr>
            </thead>
            <tbody>
                {rows.map((r, i) => <tr key={`${r.name}-${i}`}>
                    <td>{r.name}</td>
                    <td>{r.current}</td>
                    <td>+{r.additional}</td>
                    <td>{r.target}</td>
                </tr>)}
            </tbody>
        </table>
    </div>;
}

// NOTE: the inventory-based "how long does my food last" estimate now lives only inside the inventory Summary
// (via RationEstimatePanel).  The standalone Calculators page is the generic FoodStorageCalculator instead.
