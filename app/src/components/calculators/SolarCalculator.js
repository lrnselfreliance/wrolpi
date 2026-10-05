import React from "react";
import {useSearchParams} from "react-router";
import {
    Accordion,
    Anchor,
    Button,
    Grid,
    Group,
    Header,
    IconButton,
    Loader,
    Message,
    NumberInput,
    Panel,
    Select,
    Statistic,
    StatisticGroup,
    Table,
    Tabs,
    TextInput,
    Toggle,
} from "../ui";
import {InfoPopup, roundDigits} from "../Common";
import {
    DEFAULT_LOSSES,
    defaultAzimuth,
    estimateProduction,
    formatMonthly,
    INVERTER_NOMINAL_EFFICIENCY,
    LOSS_CATEGORIES,
    MODULE_TYPES,
    MONTH_NAMES,
    MOUNTINGS,
    optimalTilt,
    parseCoordinate,
    parseMonthly,
    totalLoss,
    TRACKING,
} from "./solar";
import {
    CLIMATOLOGY_ACKNOWLEDGMENT,
    CLIMATOLOGY_CHANGES,
    CLIMATOLOGY_DATA_REFERENCE,
    CLIMATOLOGY_LICENSE,
    CLIMATOLOGY_SOURCE,
    lookupClimatology,
    useClimatology,
} from "./solarData";
import {SolarOffGrid} from "./SolarOffGrid";

// Every input lives in the URL query so the Share button (which shares window.location.href) shares
// the whole configuration.  Values equal to their default are left out to keep the URL, and its QR
// code, small.  Keys are short and must stay stable; shared links depend on them.
const DEFAULT_PANEL_WATTS = 400;
const DEFAULT_PANEL_COUNT = 1;

const COMPASS = [
    {value: '0', label: 'N'}, {value: '45', label: 'NE'}, {value: '90', label: 'E'}, {value: '135', label: 'SE'},
    {value: '180', label: 'S'}, {value: '225', label: 'SW'}, {value: '270', label: 'W'}, {value: '315', label: 'NW'},
];

const fToC = f => (f - 32) * 5 / 9;
const cToF = c => c * 9 / 5 + 32;

const numberOr = (value, fallback) => {
    if (value === null || value === undefined || value === '') {
        return fallback;
    }
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
};

const fmt = (value, digits = 2) => (Number.isFinite(value) ? `${roundDigits(value, digits)}` : '—');

// Read and write the calculator's query parameters.  Writes replace the history entry, so typing does
// not fill the Back button with one entry per keystroke.
export function useSolarParams() {
    const [searchParams, setSearchParams] = useSearchParams();

    const get = key => searchParams.get(key);

    // `updates` maps keys to values; null, undefined and '' remove the key.
    const set = updates => setSearchParams(prev => {
        const next = new URLSearchParams(prev);
        Object.entries(updates).forEach(([key, value]) => {
            if (value === null || value === undefined || value === '') {
                next.delete(key);
            } else {
                next.set(key, `${value}`);
            }
        });
        return next;
    }, {replace: true});

    // Store a number, or remove it when it equals the default.
    const setNumber = (key, value, fallback) =>
        set({[key]: value === '' || Number(value) === fallback ? null : value});

    return {searchParams, get, set, setNumber};
}

// Turn the query parameters into the model's inputs.  Invalid values fall back to defaults, so a
// hand-edited or truncated link never crashes the page.
export function systemFromParams(get) {
    const latitude = parseCoordinate(get('lat'), 'lat');
    const longitude = parseCoordinate(get('lon'), 'lon');
    const fahrenheit = get('tu') === 'f';

    // Own sunlight data replaces the NASA data when present.
    const ownData = get('ghi') !== null;
    const ghi = parseMonthly(get('ghi')).map(v => (v !== null && v >= 0 ? v : null));
    const temperatureInput = parseMonthly(get('temp'));
    const temperature = temperatureInput.map(v => (v === null ? null : (fahrenheit ? fToC(v) : v)));

    const panelWatts = Math.max(0, numberOr(get('pw'), DEFAULT_PANEL_WATTS));
    const panelCount = Math.max(0, Math.round(numberOr(get('pn'), DEFAULT_PANEL_COUNT)));
    const kwp = panelWatts * panelCount / 1000;

    const tracking = TRACKING[get('track')] ? get('track') : 'fixed';
    const mounting = MOUNTINGS[get('mount')] ? get('mount') : 'open';
    const gamma = numberOr(get('gamma'), MODULE_TYPES.standard.gamma);
    const defaultTilt = latitude === null ? 0 : Math.round(Math.abs(latitude));
    const tilt = Math.min(90, Math.max(0, numberOr(get('tilt'), defaultTilt)));
    const azimuth = numberOr(get('az'), defaultAzimuth(latitude ?? 0));
    // Null means "use the monthly albedo from the data", which includes seasonal snow.
    const albedoInput = numberOr(get('alb'), null);
    const albedo = albedoInput === null ? null : Math.min(1, Math.max(0, albedoInput));

    const lossValues = parseMonthly(get('losses'));
    const losses = LOSS_CATEGORIES.map((c, i) => {
        const v = lossValues[i];
        return v !== null && v >= 0 && v <= 100 ? v : c.default;
    });

    const inverterOn = get('inv') === '1';
    const acRating = numberOr(get('iac'), roundDigits(kwp / 1.2, 2));
    const efficiency = numberOr(get('ieff'), INVERTER_NOMINAL_EFFICIENCY);

    return {
        latitude, longitude, fahrenheit, ownData, ghi, temperatureInput, temperature, panelWatts, panelCount,
        kwp, tracking, mounting, gamma, defaultTilt, tilt, azimuth, albedo, losses, inverterOn, acRating,
        efficiency,
    };
}

// The sunlight inputs for the model: the user's own values, or the NASA data at the location.
export function sunlightFor(s, grid) {
    if (s.ownData) {
        return {ghi: s.ghi, diffuse: null, temperature: s.temperature, albedo: null};
    }
    if (!grid || s.latitude === null || s.longitude === null) {
        return null;
    }
    return lookupClimatology(grid, s.latitude, s.longitude);
}

// What stops an estimate, or an empty list when it can run.
export function missingInputs(s, sunlight) {
    const missing = [];
    if (s.latitude === null) {
        missing.push('a latitude');
    }
    if (!s.ownData && s.longitude === null) {
        missing.push('a longitude');
    }
    if (s.ownData && s.ghi.some(v => v === null)) {
        missing.push('sunlight for all 12 months');
    }
    if (!(s.kwp > 0)) {
        missing.push('panel watts and count');
    }
    if (missing.length === 0 && (!sunlight || sunlight.ghi.some(v => v === null))) {
        missing.push('a location with sunlight data');
    }
    return missing;
}

const modelInputs = (s, sunlight) => ({
    latitude: s.latitude,
    ghi: sunlight.ghi,
    diffuse: sunlight.diffuse,
    temperature: sunlight.temperature,
    albedo: s.albedo ?? sunlight.albedo ?? undefined,
    kwp: s.kwp,
    tilt: s.tilt,
    azimuth: s.azimuth,
    tracking: s.tracking,
    mounting: s.mounting,
    gamma: s.gamma,
    losses: s.losses,
    inverter: s.inverterOn ? {acRating: s.acRating, efficiency: s.efficiency} : null,
});

const compassLabel = azimuth => {
    const exact = COMPASS.find(c => Number(c.value) === azimuth);
    return exact ? exact.label : `${azimuth}°`;
};

// Small explanatory text at the top of a collapsed section.
const Hint = ({children}) => <p style={{fontSize: '0.9em', opacity: 0.75, marginTop: 0}}>{children}</p>;

const ESTIMATE_INFO = 'A typical-year estimate from monthly averages. Real years vary; expect roughly ±10–15% '
    + 'over a year and more in any single month. Shading from trees and buildings is not modeled beyond the '
    + 'Shading loss.';

// Browsers only offer geolocation to pages served over HTTPS.
export const geolocationAvailable = () => Boolean(window.isSecureContext && navigator.geolocation);

const GEOLOCATION_ERRORS = {
    1: 'Location permission was denied. Allow it in your browser\'s settings for this site.',
    2: 'Your device could not find its location. Phones with GPS work offline; most computers need the Internet '
        + 'for this.',
    3: 'Finding your location took too long. Phones with GPS work offline; most computers need the Internet for '
        + 'this.',
};

function LocationSection({get, set, s, climatology}) {
    const [locating, setLocating] = React.useState(false);
    const [showAttribution, setShowAttribution] = React.useState(false);
    const [geoError, setGeoError] = React.useState(null);
    const latError = get('lat') && s.latitude === null ? 'Latitude must be between -90 and 90' : null;
    const lonError = get('lon') && s.longitude === null ? 'Longitude must be between -180 and 180' : null;

    const locate = () => {
        setLocating(true);
        setGeoError(null);
        navigator.geolocation.getCurrentPosition(
            ({coords}) => {
                setLocating(false);
                // 4 decimals (about 11 m) is far finer than the 1° data and keeps the shared URL short.
                set({lat: Number(coords.latitude.toFixed(4)), lon: Number(coords.longitude.toFixed(4))});
            },
            error => {
                setLocating(false);
                setGeoError(GEOLOCATION_ERRORS[error.code] || error.message);
            },
            {enableHighAccuracy: false, timeout: 20000, maximumAge: 10 * 60 * 1000},
        );
    };

    let source;
    if (s.ownData) {
        source = 'Using your own sunlight data.';
    } else if (climatology.loading) {
        source = <Loader size='xs' label='Loading sunlight data'/>;
    } else if (climatology.error) {
        source = <Message kind='warning' title='Sunlight data could not be loaded'>
            Enter your own monthly sunlight under "Use my own sunlight data" below.
        </Message>;
    } else {
        source = <>
            Sunlight and temperature: {CLIMATOLOGY_SOURCE}.{' '}
            <Anchor component='button' type='button' size='sm' onClick={() => setShowAttribution(!showAttribution)}>
                Data attribution
            </Anchor>
            {showAttribution && <div style={{marginTop: '0.5em'}}>
                <p>{CLIMATOLOGY_ACKNOWLEDGMENT} {CLIMATOLOGY_DATA_REFERENCE}</p>
                <p>License: {CLIMATOLOGY_LICENSE}</p>
                <p>{CLIMATOLOGY_CHANGES}</p>
            </div>}
        </>;
    }

    return <>
        <Header as='h3'>1. Location</Header>
        <Grid align='flex-end'>
            <Grid.Col span='content'>
                <IconButton icon='current location' label='Use my current location' size='input-sm'
                            loading={locating} disabled={!geolocationAvailable()} onClick={locate}/>
            </Grid.Col>
            <Grid.Col span='auto'>
                <TextInput label='Latitude' placeholder='40.015 or 40°0′54″N' name='lat'
                           value={get('lat') || ''} error={latError}
                           onChange={e => set({lat: e.target.value})}/>
            </Grid.Col>
            <Grid.Col span={{base: 12, xs: 'auto'}}>
                <TextInput label='Longitude' placeholder='-105.27 or 105°16′12″W' name='lon'
                           value={get('lon') || ''} error={lonError}
                           onChange={e => set({lon: e.target.value})}/>
            </Grid.Col>
        </Grid>
        {geoError && <Message kind='warning' title='Could not get your location'>{geoError}</Message>}
        <div style={{fontSize: '0.85em', opacity: 0.75, marginTop: '0.5em'}}>{source}</div>
    </>;
}

function PanelsSection({setNumber, s}) {
    return <>
        <Header as='h3' style={{marginTop: '1em'}}>2. Your panels</Header>
        <Grid>
            <Grid.Col span={{base: 6, sm: 3}}>
                <NumberInput label='Watts per panel' name='pw' value={s.panelWatts} min={0} step={10}
                             onChange={v => setNumber('pw', v, DEFAULT_PANEL_WATTS)}/>
            </Grid.Col>
            <Grid.Col span={{base: 6, sm: 3}}>
                <NumberInput label='Panels' name='pn' value={s.panelCount} min={0} step={1}
                             onChange={v => setNumber('pn', v, DEFAULT_PANEL_COUNT)}/>
            </Grid.Col>
            <Grid.Col span={{base: 12, sm: 6}} style={{display: 'flex', alignItems: 'flex-end'}}>
                <span style={{opacity: 0.75, paddingBottom: '0.5em'}}>
                    {fmt(s.kwp * 1000, 0)} W total ({fmt(s.kwp)} kW)
                </span>
            </Grid.Col>
        </Grid>
    </>;
}

function Results({result, s}) {
    const unit = s.inverterOn ? 'kWh AC' : 'kWh DC';
    const rows = result.months.map(m => <Table.Row key={m.month}>
        <Table.Cell>{m.month}</Table.Cell>
        <Table.Cell>{fmt(m.energyDaily)}</Table.Cell>
        <Table.Cell>{fmt(m.energy, 0)}</Table.Cell>
        <Table.Cell>{fmt(m.poa)}</Table.Cell>
        <Table.Cell>{fmt(m.dayLength, 1)} h</Table.Cell>
    </Table.Row>);

    return <Panel style={{marginTop: '1em'}}>
        <Header as='h3'>Estimate <InfoPopup content={ESTIMATE_INFO}/></Header>
        <StatisticGroup>
            <Statistic value={fmt(result.annual, 0)} label={`${unit} per year`}/>
            <Statistic value={fmt(result.annual / 365, 1)} label={`${unit} per day, average`}/>
            <Statistic value={fmt(result.worst.energyDaily, 1)} label={`${unit} per day in ${result.worst.month}`}/>
            <Statistic value={fmt(result.specificYield, 0)} label='kWh per year per kW of panels'/>
        </StatisticGroup>
        <Table>
            <Table.Header>
                <Table.Row>
                    <Table.HeaderCell>Month</Table.HeaderCell>
                    <Table.HeaderCell>{unit}/day</Table.HeaderCell>
                    <Table.HeaderCell>{unit}/month</Table.HeaderCell>
                    <Table.HeaderCell>Sun hours on panel</Table.HeaderCell>
                    <Table.HeaderCell>Day length</Table.HeaderCell>
                </Table.Row>
            </Table.Header>
            <Table.Body>{rows}</Table.Body>
        </Table>
    </Panel>;
}

function AngleSection({setNumber, s, sunlight, ready}) {
    const compass = COMPASS.find(c => Number(c.value) === s.azimuth)?.value || null;
    const applyOptimal = goal => setNumber('tilt', optimalTilt(modelInputs(s, sunlight), goal), s.defaultTilt);
    const azimuthDefault = defaultAzimuth(s.latitude ?? 0);

    if (s.tracking !== 'fixed') {
        return <Hint>
            A tracking array turns to follow the sun, so it has no fixed angle. Change Tracking under Panel details
            to set one.
        </Hint>;
    }

    return <>
        <Hint>
            Leave these alone unless your panels are already mounted. The default (tilted to your latitude, facing
            the equator) is close to the best for the year. "Best for winter" suits off-grid systems that must get
            through the darkest month.
        </Hint>
        <Grid>
            <Grid.Col span={{base: 12, sm: 6}}>
                <NumberInput label='Tilt (degrees from flat)' name='tilt' value={s.tilt} min={0} max={90} step={1}
                             onChange={v => setNumber('tilt', v, s.defaultTilt)}/>
                <Group gap='xs' style={{marginTop: '0.25em'}}>
                    <Button type='button' size='small' disabled={!ready} onClick={() => applyOptimal('annual')}>
                        Best for the year
                    </Button>
                    <Button type='button' size='small' disabled={!ready} onClick={() => applyOptimal('winter')}>
                        Best for winter
                    </Button>
                </Group>
            </Grid.Col>
            <Grid.Col span={{base: 12, sm: 6}}>
                <Group gap='xs' wrap='nowrap' align='flex-end'>
                    <NumberInput label='Facing (compass degrees)' name='az' value={s.azimuth} min={0} max={359}
                                 step={5} style={{flex: 1}} onChange={v => setNumber('az', v, azimuthDefault)}/>
                    <Select aria-label='Compass direction' data={COMPASS} value={compass} placeholder='—'
                            style={{width: '5.5em'}} allowDeselect={false}
                            onChange={v => setNumber('az', v, azimuthDefault)}/>
                </Group>
            </Grid.Col>
        </Grid>
    </>;
}

function DetailsSection({set, setNumber, s}) {
    const moduleType = Object.entries(MODULE_TYPES).find(([, m]) => m.gamma === s.gamma)?.[0] || 'custom';
    return <>
        <Hint>
            The defaults suit a typical ground or pole mounted array of ordinary panels. The temperature coefficient
            is on your panel's datasheet; panels lose this much power for each °C they run above 25 °C.
        </Hint>
        <Grid>
            <Grid.Col span={{base: 12, sm: 6}}>
                <Select label='Panel type'
                        data={[
                            ...Object.entries(MODULE_TYPES).map(([value, m]) => ({value, label: m.label})),
                            {value: 'custom', label: 'Custom (from datasheet)'},
                        ]}
                        value={moduleType} allowDeselect={false}
                        onChange={v => v !== 'custom' && setNumber('gamma', MODULE_TYPES[v].gamma,
                            MODULE_TYPES.standard.gamma)}/>
            </Grid.Col>
            <Grid.Col span={{base: 12, sm: 6}}>
                <NumberInput label='Temperature coefficient of power (%/°C)' name='gamma' value={s.gamma}
                             max={0} step={0.01} decimalScale={3}
                             onChange={v => setNumber('gamma', v, MODULE_TYPES.standard.gamma)}/>
            </Grid.Col>
            <Grid.Col span={{base: 12, sm: 6}}>
                <Select label='Mounting' data={Object.entries(MOUNTINGS).map(([value, m]) => ({value, label: m.label}))}
                        value={s.mounting} allowDeselect={false}
                        onChange={v => set({mount: v === 'open' ? null : v})}/>
            </Grid.Col>
            <Grid.Col span={{base: 12, sm: 6}}>
                <Select label='Tracking' data={Object.entries(TRACKING).map(([value, t]) => ({value, label: t.label}))}
                        value={s.tracking} allowDeselect={false}
                        onChange={v => set({track: v === 'fixed' ? null : v})}/>
            </Grid.Col>
            <Grid.Col span={{base: 12, sm: 6}}>
                <NumberInput label='Ground reflectance (albedo)' name='alb' value={s.albedo ?? ''}
                             placeholder='From the data (monthly, includes snow)' min={0} max={1} step={0.05}
                             decimalScale={2} onChange={v => set({alb: v === '' ? null : v})}/>
            </Grid.Col>
        </Grid>
    </>;
}

function LossesSection({set, s}) {
    const setLoss = (index, value) => {
        const next = [...s.losses];
        next[index] = value === '' ? LOSS_CATEGORIES[index].default : Number(value);
        const isDefault = next.every((v, i) => v === DEFAULT_LOSSES[i]);
        set({losses: isDefault ? null : formatMonthly(next)});
    };

    return <>
        <Hint>
            Real systems lose some power to dirt, wiring, shading and more. These are PVWatts' defaults. Raise Shading
            if trees or buildings shade your panels, or Snow if snow sits on them for weeks.
        </Hint>
        <Grid>
            {LOSS_CATEGORIES.map((c, i) => <Grid.Col key={c.key} span={{base: 6, sm: 4}}>
                <NumberInput label={`${c.label} (%)`} name={`loss-${c.key}`} value={s.losses[i]}
                             min={0} max={100} step={0.5} onChange={v => setLoss(i, v)}/>
            </Grid.Col>)}
        </Grid>
        <Button type='button' size='small' style={{marginTop: '0.5em'}} onClick={() => set({losses: null})}>
            Reset to PVWatts defaults
        </Button>
    </>;
}

function InverterSection({set, setNumber, s}) {
    return <>
        <Hint>
            Leave this off if your panels charge batteries through a charge controller. Turn it on to see AC output
            from a grid-tie or hybrid inverter.
        </Hint>
        <Toggle label='Include an inverter (AC output)' checked={s.inverterOn}
                onChange={e => set({inv: e.currentTarget.checked ? '1' : null})}/>
        {s.inverterOn && <Grid style={{marginTop: '0.5em'}}>
            <Grid.Col span={{base: 6}}>
                <NumberInput label='AC rating (kW)' name='iac' value={s.acRating} min={0} step={0.1} decimalScale={2}
                             onChange={v => setNumber('iac', v, roundDigits(s.kwp / 1.2, 2))}/>
            </Grid.Col>
            <Grid.Col span={{base: 6}}>
                <NumberInput label='Efficiency (%)' name='ieff' value={s.efficiency} min={50} max={100} step={0.5}
                             onChange={v => setNumber('ieff', v, INVERTER_NOMINAL_EFFICIENCY)}/>
            </Grid.Col>
        </Grid>}
    </>;
}

function OwnDataSection({set, s, nasa}) {
    const unit = s.fahrenheit ? '°F' : '°C';

    // Start from the NASA values, when available, so the user edits rather than types all 24.
    const enable = on => {
        if (!on) {
            set({ghi: null, temp: null});
            return;
        }
        const ghi = nasa ? nasa.ghi.map(v => (v === null ? '' : roundDigits(v, 2))) : Array(12).fill('');
        const temp = nasa
            ? nasa.temperature.map(v => (v === null ? '' : roundDigits(s.fahrenheit ? cToF(v) : v, 1)))
            : Array(12).fill('');
        // An all-blank list is still written for sunlight, so the section stays on for typing.
        set({ghi: formatMonthly(ghi), temp: nasa ? formatMonthly(temp) : null});
    };

    // Convert the temperatures with the unit, so they stay the same physical temperatures.
    const switchUnits = toFahrenheit => {
        const temps = s.temperatureInput.map(v => (v === null ? null
            : roundDigits(toFahrenheit ? cToF(v) : fToC(v), 1)));
        set({tu: toFahrenheit ? 'f' : null, temp: temps.some(v => v !== null) ? formatMonthly(temps) : null});
    };

    const setMonth = (key, values, index, value) => {
        const next = [...values];
        next[index] = value === '' ? null : value;
        set({[key]: formatMonthly(next)});
    };

    const rows = MONTH_NAMES.map((name, i) => <Table.Row key={name}>
        <Table.Cell>{name}</Table.Cell>
        <Table.Cell>
            <NumberInput name={`ghi-${i}`} aria-label={`${name} sunlight`} value={s.ghi[i] ?? ''} min={0}
                         step={0.1} hideControls onChange={v => setMonth('ghi', s.ghi, i, v)}/>
        </Table.Cell>
        <Table.Cell>
            <NumberInput name={`temp-${i}`} aria-label={`${name} temperature`}
                         placeholder={s.fahrenheit ? '68' : '20'} value={s.temperatureInput[i] ?? ''} step={1}
                         hideControls onChange={v => setMonth('temp', s.temperatureInput, i, v)}/>
        </Table.Cell>
    </Table.Row>);

    return <>
        <Hint>
            Only needed if you have better local measurements than the built-in data, for example in mountains, where
            a 1° grid cell (about 69 miles across) can average very different terrain. Sunlight is global horizontal
            irradiance in kWh/m²/day, the same as "peak sun hours" on flat ground. Blank temperatures use 20 °C.
        </Hint>
        <Group gap='lg'>
            <Toggle label='Use my own sunlight data' checked={s.ownData}
                    onChange={e => enable(e.currentTarget.checked)}/>
            {s.ownData && <Toggle label='Fahrenheit' checked={s.fahrenheit}
                                  onChange={e => switchUnits(e.currentTarget.checked)}/>}
        </Group>
        {s.ownData && <Table style={{marginTop: '0.5em'}}>
            <Table.Header>
                <Table.Row>
                    <Table.HeaderCell>Month</Table.HeaderCell>
                    <Table.HeaderCell>Sunlight (kWh/m²/day)</Table.HeaderCell>
                    <Table.HeaderCell>Avg. temp ({unit})</Table.HeaderCell>
                </Table.Row>
            </Table.Header>
            <Table.Body>{rows}</Table.Body>
        </Table>}
    </>;
}

export function SolarCalculator() {
    const {searchParams, get, set, setNumber} = useSolarParams();
    const climatology = useClimatology();
    const queryString = searchParams.toString();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    const s = React.useMemo(() => systemFromParams(get), [queryString]);
    const nasa = React.useMemo(
        () => (climatology.grid && s.latitude !== null && s.longitude !== null
            ? lookupClimatology(climatology.grid, s.latitude, s.longitude) : null),
        [climatology.grid, s.latitude, s.longitude]);
    const sunlight = s.ownData ? sunlightFor(s, null) : nasa;
    const missing = missingInputs(s, sunlight);
    const ready = missing.length === 0;
    const result = React.useMemo(
        () => (ready ? estimateProduction(modelInputs(s, sunlight)) : null),
        // eslint-disable-next-line react-hooks/exhaustive-deps
        [s, sunlight, ready]);
    // Off-grid sizing works from DC production per kW of panels, whatever the inverter setting.
    const worstPerKwp = React.useMemo(
        () => (ready ? estimateProduction({...modelInputs(s, sunlight), kwp: 1, inverter: null}).worst : null),
        // eslint-disable-next-line react-hooks/exhaustive-deps
        [s, sunlight, ready]);
    const tab = get('tab') === 'offgrid' ? 'offgrid' : 'estimate';

    const angleTitle = s.tracking === 'fixed'
        ? `Panel angle: ${s.tilt}° tilt, facing ${compassLabel(s.azimuth)}`
        : 'Panel angle: follows the sun';
    const detailsTitle = `Panel details: ${TRACKING[s.tracking].label.toLowerCase()}, `
        + `${MOUNTINGS[s.mounting].label.toLowerCase()}`;
    const waitingForData = climatology.loading && !s.ownData;

    return <div>
        <Header as='h1'>Solar</Header>
        <p>
            Estimate what solar panels will produce over a typical year. Enter a location and your panels; everything
            else has sensible defaults. Settings are saved in the page address, so you can bookmark or share them.
        </p>

        <LocationSection get={get} set={set} s={s} climatology={climatology}/>
        <PanelsSection setNumber={setNumber} s={s}/>

        <Tabs value={tab} onChange={v => set({tab: v === 'offgrid' ? v : null})} keepMounted={false}
              style={{marginTop: '1.5em'}}>
            <Tabs.List>
                <Tabs.Tab value='estimate'>Estimate</Tabs.Tab>
                <Tabs.Tab value='offgrid'>Off-grid sizing</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value='estimate'>
                {ready && <Results result={result} s={s}/>}
                {!ready && !waitingForData && <div style={{marginTop: '1em'}}>
                    <Message kind='info' title='Almost there'>Enter {missing.join(', ')} to see an estimate.</Message>
                </div>}
            </Tabs.Panel>
            <Tabs.Panel value='offgrid'>
                <SolarOffGrid get={get} set={set} setNumber={setNumber} s={s} worst={worstPerKwp}
                              temperatures={sunlight?.temperature} loading={waitingForData}/>
            </Tabs.Panel>
        </Tabs>

        <Header as='h3' style={{marginTop: '1.5em'}}>Fine-tune (optional)</Header>
        <Accordion multiple>
            <Accordion.Item value='angle'>
                <Accordion.Control>{angleTitle}</Accordion.Control>
                <Accordion.Panel>
                    <AngleSection setNumber={setNumber} s={s} sunlight={sunlight} ready={ready}/>
                </Accordion.Panel>
            </Accordion.Item>
            <Accordion.Item value='details'>
                <Accordion.Control>{detailsTitle}</Accordion.Control>
                <Accordion.Panel><DetailsSection set={set} setNumber={setNumber} s={s}/></Accordion.Panel>
            </Accordion.Item>
            <Accordion.Item value='losses'>
                <Accordion.Control>System losses: {fmt(totalLoss(s.losses))}%</Accordion.Control>
                <Accordion.Panel><LossesSection set={set} s={s}/></Accordion.Panel>
            </Accordion.Item>
            <Accordion.Item value='inverter'>
                <Accordion.Control>Inverter: {s.inverterOn ? 'on (AC output)' : 'off (DC output)'}</Accordion.Control>
                <Accordion.Panel><InverterSection set={set} setNumber={setNumber} s={s}/></Accordion.Panel>
            </Accordion.Item>
            <Accordion.Item value='own'>
                <Accordion.Control>Use my own sunlight data: {s.ownData ? 'on' : 'off'}</Accordion.Control>
                <Accordion.Panel><OwnDataSection set={set} s={s} nasa={nasa}/></Accordion.Panel>
            </Accordion.Item>
        </Accordion>
    </div>;
}
