import React from "react";
import {GridColumn, Input, Label, TableBody, TableCell, TableHeader, TableHeaderCell, TableRow} from "semantic-ui-react";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {Form, Header, Segment, Table} from "../Theme";
import {InfoPopup, roundDigits, Toggle, useLocalStorage} from "../Common";
import {Media} from "../../contexts/contexts";

// Pure calculation functions for the Water Storage calculator.
//
// The model is deliberately simple: a household of some men, women, and children each
// consume a per-day amount of water (drinking plus hygiene/dish use).  Over a chosen
// duration that becomes a total volume, which the user stores in some number of a chosen
// container (55-gallon drums, 5-gallon buckets, 2-liter bottles, ...).
//
// Functions are unit-agnostic: pass consistent units (all gallons, or all liters) and the
// result comes back in those same units.  The React component picks imperial vs metric and
// supplies the matching per-category rates and container capacities.

// Total water the household needs per day: sum of (count * rate) for each category.
// Missing/blank/non-positive counts or rates contribute nothing rather than NaN.
export function dailyDemand(counts, rates) {
    const term = (count, rate) => {
        const c = Number(count), r = Number(rate);
        return (c > 0 && r > 0) ? c * r : 0;
    };
    return term(counts.men, rates.men)
        + term(counts.women, rates.women)
        + term(counts.children, rates.children)
        + term(counts.pregnant, rates.pregnant);
}

// Total volume to store for `days` days at the given daily demand.
export function totalWater(daily, days) {
    if (!(daily > 0) || !(days > 0)) {
        return null;
    }
    return daily * days;
}

// Number of containers of `capacity` needed to hold `totalVolume`, rounded up because a
// partial container still has to be a whole container.  `leftover` is the unused capacity
// in the last container.  Returns null for impossible inputs.
export function containersNeeded(totalVolume, capacity) {
    if (!(totalVolume > 0) || !(capacity > 0)) {
        return null;
    }
    const count = Math.ceil(totalVolume / capacity);
    return {count, leftover: count * capacity - totalVolume};
}

// Approximate weight of a volume of water: ~8.345 lb per US gallon, or 1 kg per liter.
// Useful for shelving/vehicle planning.  Returns null when the volume is not positive.
export function waterWeight(volume, metric) {
    if (!(volume > 0)) {
        return null;
    }
    return metric ? volume * 1 : volume * 8.345;
}

// Human-friendly label for a duration in days: days up to a week, then weeks, then months,
// then whole years.  Keeps the slider from showing awkward values like "68 days".
export function formatDuration(days) {
    const d = Math.round(Number(days));
    if (!(d > 0)) {
        return '—';
    }
    if (d <= 7) {
        return `${d} day${d === 1 ? '' : 's'}`;
    }
    if (d < 30) {
        const weeks = Math.round(d / 7);
        return `${weeks} week${weeks === 1 ? '' : 's'}`;
    }
    if (d < 360) {
        const months = Math.round(d / 30);
        return `${months} month${months === 1 ? '' : 's'}`;
    }
    const years = d / 360;
    if (Number.isInteger(years)) {
        return `${years} year${years === 1 ? '' : 's'}`;
    }
    const months = Math.round(d / 30);
    return `${months} months`;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

// Per-category daily water need, including drinking plus hygiene and dish use.  These are
// editable starting points.  "Minimum" sits at the CDC/FEMA emergency floor of ~1 gallon
// per person per day (half drinking, half hygiene/cooking); men/women/children are scaled
// by the drinking portion using the National Academies adequate-intake figures (men ~3.7 L,
// women ~2.7 L of total water/day), while the hygiene/cooking half is shared.  Pregnant and
// nursing women get the extra CDC/Ready.gov calls out (~+0.5 gal pregnant, ~+1 gal nursing;
// NAS lactating ~3.8 L).  "Comfortable" roughly doubles the floor to allow real washing,
// cooking, and dishes.  Metric values are the imperial values converted to liters and
// rounded; the component swaps tables on toggle.
export const WATER_PRESETS = {
    minimum: {
        label: 'Minimum',
        description: 'CDC emergency floor (~1 gal/person/day)',
        imperial: {men: 1.0, women: 0.9, children: 0.8, pregnant: 1.6},   // gallons/day
        metric: {men: 3.8, women: 3.4, children: 3.0, pregnant: 6.1},     // liters/day
    },
    comfortable: {
        label: 'Comfortable',
        description: 'Adds real washing, cooking, and dishes',
        imperial: {men: 2.0, women: 1.8, children: 1.5, pregnant: 2.8},
        metric: {men: 7.6, women: 6.8, children: 5.7, pregnant: 10.6},
    },
};

// Common water-storage containers, capacity in both gallons and liters.  Ordered large to
// small so the dropdown reads from bulk storage down to single bottles.
export const CONTAINERS = [
    {key: 'ibc', label: 'IBC tote', gallons: 275, liters: 1041},
    {key: 'drum55', label: '55-gallon drum', gallons: 55, liters: 208},
    {key: 'drum30', label: '30-gallon drum', gallons: 30, liters: 114},
    {key: 'jug7', label: '7-gallon jug', gallons: 7, liters: 26.5},
    {key: 'bucket5', label: '5-gallon bucket', gallons: 5, liters: 18.9},
    {key: 'waterbrick', label: 'WaterBrick', gallons: 3.5, liters: 13.2},
    {key: 'jug1', label: '1-gallon jug', gallons: 1, liters: 3.785},
    {key: 'bottle2l', label: '2-liter soda bottle', gallons: 0.528, liters: 2},
    {key: 'bottle1l', label: '1-liter bottle', gallons: 0.264, liters: 1},
    {key: 'bottle500', label: '500 mL water bottle', gallons: 0.132, liters: 0.5},
];

// Slider stops in days: daily for the first week, then weekly, then monthly (grouped by 30
// per the "no awkward 68-day values" rule), out to a couple of years.
export const DURATION_STOPS = [
    1, 2, 3, 4, 5, 6, 7,
    14, 21,
    30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330, 360,
    540, 720,
];

// Explanation shown in the "Daily Use" info popup.  Cites the figures the presets are
// built from so the numbers are traceable offline.
const DEMAND_INFO = 'Per-person daily water includes drinking plus basic hygiene and dish '
    + 'washing — not just drinking. The Minimum preset follows the CDC/FEMA emergency floor '
    + 'of about 1 gallon (3.8 L) per person per day (roughly half for drinking, half for '
    + 'hygiene and cooking), and both agencies recommend storing a 2-week supply. The '
    + 'men/women/children split scales the drinking portion using the U.S. National Academies '
    + 'adequate-intake figures (men ~3.7 L, women ~2.7 L of total water per day). The '
    + 'Pregnant/Nursing category adds the extra CDC/Ready.gov calls out — about +0.5 gallon '
    + 'for pregnant and +1 gallon for nursing women. CDC also advises storing more for sick '
    + 'people, pets, and hot climates. Use the "Additional daily demand" field below for pets, '
    + 'livestock, or other needs not covered by the per-person categories.';

// Per-category colors (Paul Tol bright palette) so the count inputs read at a glance.
const CATEGORY_META = [
    {key: 'men', label: 'Men', icon: 'man', color: '#4477aa'},
    {key: 'women', label: 'Women', icon: 'woman', color: '#aa3377'},
    {key: 'children', label: 'Children', icon: 'child', color: '#228833'},
    {key: 'pregnant', label: 'Pregnant/Nursing', icon: 'heart', color: '#ee6677'},
];

// Pick black or white label text for legibility on a given background color.
function textColorFor(hex) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    return luminance > 0.6 ? '#000000' : '#ffffff';
}

// Format a positive number with a unit, or an em-dash when unavailable.
function fmt(value, unit) {
    if (!Number.isFinite(value) || value <= 0) {
        return '—';
    }
    return unit ? `${roundDigits(value, 2)} ${unit}` : `${roundDigits(value, 2)}`;
}

// Keep a numeric input non-negative without disrupting in-progress decimal entry.
// A <input type=number> can only become negative via a leading "-", so stripping it is
// enough; returning the raw string otherwise lets the user finish typing "1.5".
function clampNonNegative(value) {
    if (value === '') {
        return '';
    }
    return value.startsWith('-') ? value.slice(1) : value;
}

export function WaterCalculator() {
    const [metric, setMetric] = useLocalStorage('water_calculator_metric', false);
    const [preset, setPreset] = useLocalStorage('water_calculator_preset', 'minimum');
    const [counts, setCounts] = useLocalStorage('water_calculator_counts',
        {men: '1', women: '1', children: '', pregnant: ''});
    const [extra, setExtra] = useLocalStorage('water_calculator_extra', '');
    const [rates, setRates] = React.useState({...WATER_PRESETS.minimum.imperial});
    const [durationIndex, setDurationIndex] = useLocalStorage('water_calculator_duration_index',
        DURATION_STOPS.indexOf(14));

    // Reset the editable rates to the preset's defaults whenever the preset or unit changes.
    React.useEffect(() => {
        const p = WATER_PRESETS[preset];
        setRates(metric ? {...p.metric} : {...p.imperial});
    }, [preset, metric]);

    const volumeUnit = metric ? 'L' : 'gal';
    const rateUnit = metric ? 'L/day' : 'gal/day';
    const weightUnit = metric ? 'kg' : 'lb';
    // A persisted index could fall out of range if DURATION_STOPS ever changes; clamp it.
    const durationStop = Math.min(Math.max(0, durationIndex), DURATION_STOPS.length - 1);
    const days = DURATION_STOPS[durationStop];

    const baseDaily = dailyDemand(counts, rates);
    const extraDaily = Number(extra) > 0 ? Number(extra) : 0;
    const daily = baseDaily + extraDaily;
    const total = totalWater(daily, days);
    const weight = waterWeight(total, metric);

    const inputProps = {fluid: true, type: 'number', onSelect: e => e.target.select(), autoComplete: 'off'};

    // One count input per category, label colored to match.
    const countInput = ({key, label, icon, color}) =>
        <Input {...inputProps} min={0} step={1} name={`count-${key}`}
               labelPosition='left' value={counts[key]}
               onChange={e => setCounts({...counts, [key]: e.target.value === '' ? '' : String(Math.max(0, Math.round(Number(e.target.value))))})}
               label={<Label style={{backgroundColor: color, color: textColorFor(color), borderColor: color}}>
                   <i className={`${icon} icon`} style={{marginRight: '0.4em'}}/>{label}</Label>}/>;

    // One editable rate input per category, sharing the category color.
    const rateInput = ({key, label, color}) =>
        <Input {...inputProps} min={0} step={0.1} name={`rate-${key}`}
               labelPosition='left' value={rates[key]}
               onChange={e => setRates({...rates, [key]: clampNonNegative(e.target.value)})}
               label={<Label style={{backgroundColor: color, color: textColorFor(color), borderColor: color}}>
                   {label}</Label>}/>;

    const presetButtons = (
        <div>
            {Object.entries(WATER_PRESETS).map(([key, p]) => (
                <button
                    key={key}
                    type="button"
                    onClick={() => setPreset(key)}
                    style={{
                        marginRight: '0.5em',
                        padding: '0.4em 0.8em',
                        border: preset === key ? '2px solid #2185d0' : '1px solid #ccc',
                        background: preset === key ? '#e8f4fc' : 'white',
                        borderRadius: '4px',
                        cursor: 'pointer'
                    }}
                >
                    <strong>{p.label}</strong> — {p.description}
                </button>
            ))}
            <span style={{fontSize: '0.85em', opacity: 0.7, marginLeft: '0.5em'}}>
                (switching resets rates to preset defaults)
            </span>
        </div>
    );

    // One row per container: how many of it the total water would fill, and the spare
    // capacity in the last one.  Shown for every container so the user can compare.
    const containerRows = CONTAINERS.map(c => {
        const capacity = metric ? c.liters : c.gallons;
        const need = total !== null ? containersNeeded(total, capacity) : null;
        return <TableRow key={c.key}>
            <TableCell>{c.label}</TableCell>
            <TableCell>{capacity} {volumeUnit}</TableCell>
            <TableCell>
                {need === null
                    ? '—'
                    : <span><b>{need.count}</b>
                        {need.leftover > 0 &&
                            <span style={{opacity: 0.7}}> ({fmt(need.leftover, volumeUnit)} spare)</span>}
                    </span>}
            </TableCell>
        </TableRow>;
    });

    return <Form>
        <Header as='h1'>Water Storage</Header>

        <div style={{marginBottom: '1em'}}>
            <Toggle label={metric ? 'Metric (liters)' : 'Imperial (gallons)'}
                    checked={metric} onChange={() => setMetric(!metric)}/>
        </div>
        <div style={{marginBottom: '1em'}}>{presetButtons}</div>

        <Header as='h3'>People</Header>
        <Grid stackable columns={2}>
            {CATEGORY_META.map(meta =>
                <GridColumn key={meta.key}>{countInput(meta)}</GridColumn>)}
        </Grid>

        <Header as='h3' style={{marginTop: '1em'}}>
            Daily Use ({rateUnit} per person) <InfoPopup content={DEMAND_INFO}/>
        </Header>
        <Grid stackable columns={2}>
            {CATEGORY_META.map(meta =>
                <GridColumn key={meta.key}>{rateInput(meta)}</GridColumn>)}
        </Grid>

        <Header as='h3' style={{marginTop: '1em'}}>Additional daily demand</Header>
        <div style={{maxWidth: '320px'}}>
            <Input {...inputProps} min={0} step={0.1} name="extra"
                   labelPosition='left' value={extra}
                   onChange={e => setExtra(clampNonNegative(e.target.value))}
                   label={<Label>Extra {rateUnit}</Label>}/>
            <p style={{fontSize: '0.85em', opacity: 0.7, marginTop: '0.25em'}}>
                Pets, livestock, guests, sick household members, or anything else not covered above.
            </p>
        </div>

        <Header as='h3' style={{marginTop: '1em'}}>How long?</Header>
        <div style={{padding: '0 0.5em'}}>
            <input type='range' min={0} max={DURATION_STOPS.length - 1} step={1}
                   value={durationStop} aria-label='Duration'
                   onChange={e => setDurationIndex(Number(e.target.value))}
                   style={{width: '100%'}}/>
            <Header as='h2' textAlign='center' style={{marginTop: '0.25em'}}>
                {formatDuration(days)}
            </Header>
        </div>

        <Segment style={{marginTop: '1em'}}>
            <Table definition unstackable>
                <TableBody>
                    <TableRow>
                        <TableCell width={6}>Daily Use</TableCell>
                        <TableCell>{fmt(daily, `${volumeUnit}/day`)}</TableCell>
                    </TableRow>
                    <TableRow>
                        <TableCell>Total Water for {formatDuration(days)}</TableCell>
                        <TableCell>{fmt(total, volumeUnit)}</TableCell>
                    </TableRow>
                    <TableRow>
                        <TableCell>Water Weight</TableCell>
                        <TableCell>{fmt(weight, weightUnit)}</TableCell>
                    </TableRow>
                </TableBody>
            </Table>

            <Header as='h3'>Containers Needed</Header>
            <Table unstackable>
                <TableHeader>
                    <TableRow>
                        <TableHeaderCell>Container</TableHeaderCell>
                        <TableHeaderCell>Capacity</TableHeaderCell>
                        <TableHeaderCell>Needed</TableHeaderCell>
                    </TableRow>
                </TableHeader>
                <TableBody>{containerRows}</TableBody>
            </Table>
        </Segment>
    </Form>;
}
