import React from "react";
import {Button, Grid, Header, Table} from "../ui";
import {ColoredInput} from "../Apps";
import {InfoPopup, roundDigits, useLocalStorage} from "../Common";
import {formatDuration} from "./WaterCalculator";
import {findNameKey, planSupplyPurchase} from "../inventory/summarize";
import {downloadCSV, inventoryExportFilename, shoppingListCSV} from "../inventory/inventoryExport";
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

// Category colors are theme tokens (not hex) so the tags stay legible — and become outlines instead of fills — in
// night mode.
const CATEGORY_META = [
    {key: 'men', label: 'Men', color: 'blue'},
    {key: 'women', label: 'Women', color: 'pink'},
    {key: 'children', label: 'Children', color: 'green'},
];

const DEMAND_INFO = 'Per-person daily calorie needs come from the Dietary Guidelines for Americans 2020-2025 '
    + '(Appendix 2), by sex and physical activity level. Adult values are representative for ages 19-60; the '
    + 'children figure is a mid-childhood approximation since needs vary widely with age (1,000-3,200 kcal/day). '
    + 'The Survival preset is a short-term emergency ration floor, below maintenance. All values are editable — '
    + 'adjust the household and activity level to see how long the stored food lasts.';

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
        <ColoredInput {...inputProps} min={0} step={1} name={`count-${key}`} label={label} color={color}
                      value={counts[key]} onChange={e => setCounts({...counts, [key]: e.target.value})}/>;

    const rateInput = ({key, label, color}) =>
        <ColoredInput {...inputProps} min={0} step={50} name={`rate-${key}`} label={label} color={color}
                      value={rates[key]} onChange={e => setRates({...rates, [key]: e.target.value})}/>;

    return <div>
        <Header as='h3'>People</Header>
        <Grid>
            {CATEGORY_META.map(meta =>
                <Grid.Col key={meta.key} span={{base: 12, sm: 4}}>{countInput(meta)}</Grid.Col>)}
        </Grid>

        <Header as='h3' style={{marginTop: '1em'}}>
            Daily Calories (per person) <InfoPopup content={DEMAND_INFO}/>
        </Header>
        <div style={{marginBottom: '1em', display: 'flex', flexWrap: 'wrap', gap: '0.5em'}}>
            {Object.entries(RATION_PRESETS).map(([key, p]) => (
                <Button key={key} role={preset === key ? 'primary' : 'cancel'} onClick={() => setPreset(key)}>
                    <strong>{p.label}</strong> — {p.description}
                </Button>
            ))}
        </div>
        <Grid>
            {CATEGORY_META.map(meta =>
                <Grid.Col key={meta.key} span={{base: 12, sm: 4}}>{rateInput(meta)}</Grid.Col>)}
        </Grid>

        <Table style={{marginTop: '1em'}}>
            <Table.Body>
                <Table.Row>
                    <Table.Cell>Total Stored Calories</Table.Cell>
                    <Table.Cell>{fmt(total, 'kcal')}</Table.Cell>
                </Table.Row>
                <Table.Row>
                    <Table.Cell>Daily Demand</Table.Cell>
                    <Table.Cell>{fmt(daily, 'kcal/day')}</Table.Cell>
                </Table.Row>
                <Table.Row>
                    <Table.Cell>Food Lasts</Table.Cell>
                    <Table.Cell>{days ? formatDuration(days) : '—'}</Table.Cell>
                </Table.Row>
            </Table.Body>
        </Table>

        <SupplyPlan name={name} items={items} fields={fields} caloriesKey={caloriesKey} countKey={countKey}
                    currentDays={days} total={total} daily={daily}/>
    </div>;
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
        <Table.HeaderCell sorted={sortDir(key)} onSort={() => toggleSort(key)}>{label}</Table.HeaderCell>;

    return <div style={{marginTop: '2em'}}>
        <Header as='h3'>Plan More Supply <InfoPopup content={PLAN_INFO}/></Header>
        {!countKey
            ? <p>Add a <strong>Count</strong> field to this inventory to plan purchases.</p>
            : <>
                <div style={{padding: '0 0.5em'}}>
                    <input type='range' min={minMonths} max={maxMonths} step={1} value={targetMonths}
                           aria-label='Target duration (months)' style={{width: '100%'}}
                           onChange={e => setTargetMonths(Number(e.target.value))}/>
                    <Header as='h2' style={{marginTop: '0.25em', textAlign: 'center'}}>
                        Target: {formatDuration(targetDays)}
                    </Header>
                    <p style={{textAlign: 'center', opacity: 0.8}}>
                        Currently {formatDuration(currentDays)}
                    </p>
                </div>

                {rows.length === 0
                    ? <p>Drag the slider above your current estimate to see a shopping list.</p>
                    : <>
                        <Table className='shopping-list-table'>
                            <Table.Header>
                                <Table.Row>
                                    {headerCell('name', 'Item')}
                                    {headerCell('current', 'Have')}
                                    {headerCell('additional', 'Buy')}
                                    {headerCell('target', 'New Total')}
                                </Table.Row>
                            </Table.Header>
                            <Table.Body>
                                {sortedRows.map((r, i) => <Table.Row key={`${r.name}-${i}`}>
                                    <Table.Cell>{r.name}</Table.Cell>
                                    <Table.Cell>{r.current}</Table.Cell>
                                    <Table.Cell><strong>+{r.additional}</strong></Table.Cell>
                                    <Table.Cell>{r.target}</Table.Cell>
                                </Table.Row>)}
                            </Table.Body>
                        </Table>
                        <p>
                            Buy <strong>{totalToBuy.toLocaleString()}</strong> additional package{totalToBuy === 1 ? '' : 's'}
                            {' '}across <strong>{rows.length}</strong> item{rows.length === 1 ? '' : 's'}
                            {projectedDays ? <> to reach about <strong>{formatDuration(projectedDays)}</strong> of food.</> : '.'}
                        </p>

                        <Button role='primary' icon='download'
                                onClick={() => downloadCSV(
                                    inventoryExportFilename(`${name || 'inventory'} shopping list`, 'csv'),
                                    shoppingListCSV(sortedRows))}>
                            Download CSV
                        </Button>
                        <Button icon='print' onClick={printShoppingList}>
                            Print / Save as PDF
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
