import React from "react";
import {Button, Grid, Group, Header, IconButton, Loader, Message, NumberInput, Panel, Select, Statistic,
    StatisticGroup, Table, TextInput, Toggle} from "../ui";
import {roundDigits} from "../Common";
import {
    BATTERIES,
    batteryWarnings,
    CONTROLLERS,
    controllerSizing,
    dailyLoadWh,
    defaultColdest,
    formatLoads,
    leadAcidCapacityFactor,
    loadWh,
    parseLoads,
    requiredKwp,
    sizeBattery,
    SYSTEM_VOLTAGES,
} from "./offgrid";

// Defaults are typical of a 400 W residential panel; the user should copy their panel's label.
const PANEL_DEFAULTS = {voc: 37, vmp: 31, isc: 13.8, bvoc: -0.27};
const DEFAULT_LOAD_INVERTER_EFFICIENCY = 90;
const DEFAULT_DAYS = 2;
const DEFAULT_CONTROLLER_MAX_VOLTAGE = 100;
// Above this, a higher system voltage needs a much smaller controller and thinner wire.
const HIGH_CURRENT = 60;

const numberOr = (value, fallback) => {
    if (value === null || value === undefined || value === '') {
        return fallback;
    }
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
};

const fmt = (value, digits = 0) => (Number.isFinite(value) ? `${roundDigits(value, digits)}` : '—');

const Hint = ({children}) => <p style={{fontSize: '0.9em', opacity: 0.75, marginTop: 0}}>{children}</p>;

// The off-grid inputs, read from the URL like the rest of the calculator.  Invalid values fall back.
export function offGridFromParams(get, monthlyTemperatures) {
    const battery = BATTERIES[get('bat')] ? get('bat') : 'lfp';
    const systemVoltage = SYSTEM_VOLTAGES.includes(Number(get('sv'))) ? Number(get('sv')) : 12;
    const controller = CONTROLLERS[get('ctl')] ? get('ctl') : 'mppt';
    const coldestMonthly = (monthlyTemperatures || []).filter(Number.isFinite).length
        ? Math.min(...monthlyTemperatures.filter(Number.isFinite)) : null;
    const defaultTmin = defaultColdest(monthlyTemperatures);
    return {
        loads: parseLoads(get('load')),
        acLoads: get('ac') !== '0',
        loadInverterEfficiency: numberOr(get('leff'), DEFAULT_LOAD_INVERTER_EFFICIENCY),
        battery,
        systemVoltage,
        dod: numberOr(get('dod'), BATTERIES[battery].dod),
        days: Math.max(0, numberOr(get('aut'), DEFAULT_DAYS)),
        outdoors: get('bout') === '1',
        controller,
        voc: numberOr(get('voc'), PANEL_DEFAULTS.voc),
        vmp: numberOr(get('vmp'), PANEL_DEFAULTS.vmp),
        isc: numberOr(get('isc'), PANEL_DEFAULTS.isc),
        // Always negative for silicon panels; a missing minus sign must not hide the cold-weather rise.
        betaVoc: -Math.abs(numberOr(get('bvoc'), PANEL_DEFAULTS.bvoc)),
        series: Math.max(1, Math.round(numberOr(get('ns'), 1))),
        controllerMaxVoltage: numberOr(get('cmax'), DEFAULT_CONTROLLER_MAX_VOLTAGE),
        coldestMonthly,
        defaultTmin,
        coldest: numberOr(get('tmin'), defaultTmin),
    };
}

/**
 * Everything the off-grid tab shows, from its inputs.
 *
 * @param {Object} o              offGridFromParams()
 * @param {Object} worst          the worst month for a 1 kW array: {month, energyDaily}
 * @param {number} panelWatts
 * @param {number} panelCount
 */
export function offGridResults(o, worst, panelWatts, panelCount) {
    const devicesWh = dailyLoadWh(o.loads);
    // AC devices draw through an inverter, so the batteries supply more than the devices use.
    const batteryLoadWh = o.acLoads && o.loadInverterEfficiency > 0
        ? devicesWh / (o.loadInverterEfficiency / 100) : devicesWh;
    const capacityFactor = o.outdoors && o.battery === 'lead' ? leadAcidCapacityFactor(o.coldestMonthly) : 1;
    const bank = sizeBattery({
        loadWh: batteryLoadWh, days: o.days, dod: o.dod, voltage: o.systemVoltage, capacityFactor,
    });

    const sizing = controllerSizing({
        panelCount, panelWatts, series: o.series, voc: o.voc, vmp: o.vmp, isc: o.isc, betaVoc: o.betaVoc,
        coldest: o.coldest, controller: o.controller, controllerMaxVoltage: o.controllerMaxVoltage,
        systemVoltage: o.systemVoltage,
    });

    // A PWM controller wastes part of every panel's output, so more panels are needed.
    const worstPerKwp = worst ? worst.energyDaily * sizing.pwmFraction : null;
    const kwp = requiredKwp(batteryLoadWh, worstPerKwp, BATTERIES[o.battery].efficiency);
    const panelsNeeded = kwp && panelWatts > 0 ? Math.ceil(kwp * 1000 / panelWatts) : null;
    const yourArrayWh = worstPerKwp !== null
        ? worstPerKwp * (panelCount * panelWatts / 1000) * 1000 * BATTERIES[o.battery].efficiency / 100 : null;

    return {
        devicesWh, batteryLoadWh, bank, kwp, panelsNeeded, sizing,
        coverage: batteryLoadWh > 0 && yourArrayWh !== null ? yourArrayWh / batteryLoadWh : null,
        warnings: batteryWarnings({battery: o.battery, outdoors: o.outdoors, coldestMonthly: o.coldestMonthly}),
    };
}

function LoadsSection({o, r, set, setNumber}) {
    const rows = o.loads.length ? o.loads : [{name: '', watts: '', hours: ''}];
    const write = next => set({load: next.some(row => row.name || row.watts || row.hours) ? formatLoads(next) : null});
    const update = (index, field, value) => write(rows.map((row, i) => (i === index ? {...row, [field]: value} : row)));
    const remove = index => write(rows.filter((_, i) => i !== index));

    return <>
        <Header as='h3'>Your devices</Header>
        <Hint>
            List what you will run and for how long each day. The watts are on the device's label or power supply;
            a refrigerator cycles on and off, so use about a third of its rating for 24 hours.
        </Hint>
        <Table>
            <Table.Header>
                <Table.Row>
                    <Table.HeaderCell>Device</Table.HeaderCell>
                    <Table.HeaderCell>Watts</Table.HeaderCell>
                    <Table.HeaderCell>Hours per day</Table.HeaderCell>
                    <Table.HeaderCell>Wh per day</Table.HeaderCell>
                    <Table.HeaderCell/>
                </Table.Row>
            </Table.Header>
            <Table.Body>
                {rows.map((row, i) => <Table.Row key={i}>
                    <Table.Cell>
                        <TextInput aria-label={`Device ${i + 1} name`} placeholder='Refrigerator' value={row.name}
                                   onChange={e => update(i, 'name', e.target.value)}/>
                    </Table.Cell>
                    <Table.Cell>
                        <NumberInput aria-label={`Device ${i + 1} watts`} placeholder='50' value={row.watts} min={0}
                                     hideControls onChange={v => update(i, 'watts', v)}/>
                    </Table.Cell>
                    <Table.Cell>
                        <NumberInput aria-label={`Device ${i + 1} hours`} placeholder='24' value={row.hours} min={0}
                                     max={24} hideControls onChange={v => update(i, 'hours', v)}/>
                    </Table.Cell>
                    <Table.Cell>{fmt(loadWh(row))}</Table.Cell>
                    <Table.Cell>
                        <IconButton icon='trash' label={`Remove device ${i + 1}`} onClick={() => remove(i)}/>
                    </Table.Cell>
                </Table.Row>)}
            </Table.Body>
        </Table>
        <Group gap='md' style={{marginTop: '0.5em'}}>
            <Button type='button' size='small' icon='add'
                    onClick={() => write([...rows, {name: '', watts: '', hours: ''}])}>
                Add device
            </Button>
            <span><b>{fmt(r.devicesWh)} Wh</b> per day</span>
        </Group>
        <Group gap='lg' align='flex-end' style={{marginTop: '0.75em'}}>
            <Toggle label='Devices run on AC, through an inverter' checked={o.acLoads}
                    onChange={e => set({ac: e.currentTarget.checked ? null : '0'})}/>
            {o.acLoads && <NumberInput label='Inverter efficiency (%)' name='leff' value={o.loadInverterEfficiency}
                                       min={50} max={100} step={1} style={{width: '12em'}}
                                       onChange={v => setNumber('leff', v, DEFAULT_LOAD_INVERTER_EFFICIENCY)}/>}
        </Group>
    </>;
}

function BatterySection({o, set, setNumber}) {
    return <>
        <Header as='h3' style={{marginTop: '1.5em'}}>Batteries</Header>
        <Hint>
            Days without sun is how long the batteries must carry your devices through cloudy weather. Two or three
            days is typical. Larger systems (over about 1,500 W of panels) usually use 24 or 48 volts.
        </Hint>
        <Grid>
            <Grid.Col span={{base: 12, sm: 6}}>
                <Select label='Battery type'
                        data={Object.entries(BATTERIES).map(([value, b]) => ({value, label: b.label}))}
                        value={o.battery} allowDeselect={false}
                        onChange={v => set({bat: v === 'lfp' ? null : v, dod: null})}/>
            </Grid.Col>
            <Grid.Col span={{base: 6, sm: 3}}>
                <Select label='System voltage' data={SYSTEM_VOLTAGES.map(v => ({value: `${v}`, label: `${v} V`}))}
                        value={`${o.systemVoltage}`} allowDeselect={false}
                        onChange={v => set({sv: v === '12' ? null : v})}/>
            </Grid.Col>
            <Grid.Col span={{base: 6, sm: 3}}>
                <NumberInput label='Days without sun' name='aut' value={o.days} min={0} step={0.5}
                             onChange={v => setNumber('aut', v, DEFAULT_DAYS)}/>
            </Grid.Col>
            <Grid.Col span={{base: 12, sm: 6}}>
                <NumberInput label='Usable depth of discharge (%)' name='dod' value={o.dod} min={10} max={100} step={5}
                             onChange={v => setNumber('dod', v, BATTERIES[o.battery].dod)}/>
            </Grid.Col>
            <Grid.Col span={{base: 12, sm: 6}} style={{display: 'flex', alignItems: 'flex-end'}}>
                <Toggle label='Batteries are outdoors or unheated' checked={o.outdoors}
                        onChange={e => set({bout: e.currentTarget.checked ? '1' : null})}/>
            </Grid.Col>
        </Grid>
    </>;
}

function NeedsSection({o, r, worst, s, setNumber}) {
    if (!(r.devicesWh > 0)) {
        return <div style={{marginTop: '1em'}}>
            <Message kind='info' title='Add your devices'>List your devices above to size the system.</Message>
        </div>;
    }
    const coverage = r.coverage;
    return <Panel style={{marginTop: '1.5em'}}>
        <Header as='h3'>What you need</Header>
        <StatisticGroup>
            <Statistic value={fmt(r.panelsNeeded)} label={`${s.panelWatts} W panels for ${worst.month}`}/>
            <Statistic value={fmt(r.bank?.ah)} label={`Ah of ${o.systemVoltage} V battery`}/>
            <Statistic value={fmt(r.bank ? r.bank.nominalWh / 1000 : null, 1)} label='kWh of battery'/>
            <Statistic value={fmt(r.batteryLoadWh)} label='Wh per day from the batteries'/>
        </StatisticGroup>
        <p>
            Sized for {worst.month}, your darkest month, when each kW of panels makes about{' '}
            {fmt(worst.energyDaily, 1)} kWh a day at the angle chosen under Fine-tune.
            {o.controller === 'pwm' && r.sizing.pwmFraction > 0 && ` The PWM controller uses only `
                + `${fmt(r.sizing.pwmFraction * 100)}% of the panels' power, so more panels are needed.`}
            {o.controller === 'pwm' && r.sizing.pwmFraction === 0 && ' These panels cannot charge this battery '
                + 'through a PWM controller; see the warning below.'}
        </p>
        {coverage !== null && <p>
            Your {s.panelCount} panel{s.panelCount === 1 ? '' : 's'} would supply about{' '}
            <b>{fmt(Math.min(coverage, 9.99) * 100)}%</b> of your use in {worst.month}.{' '}
            {r.panelsNeeded !== s.panelCount && r.panelsNeeded > 0 &&
                <Button type='button' size='small' onClick={() => setNumber('pn', r.panelsNeeded, 1)}>
                    Use {r.panelsNeeded} panels
                </Button>}
        </p>}
        {r.warnings.map(w => <Message key={w} kind='warning' title='Battery'>{w}</Message>)}
    </Panel>;
}

function ControllerSection({o, r, set, setNumber, temperaturesKnown}) {
    const z = r.sizing;
    const panelField = (key, label, value, fallback, step, max) => <Grid.Col span={{base: 6, sm: 3}}>
        <NumberInput label={label} name={key} value={value} step={step} decimalScale={3} max={max}
                     onChange={v => setNumber(key, v, fallback)}/>
    </Grid.Col>;

    return <>
        <Header as='h3' style={{marginTop: '1.5em'}}>Charge controller and wiring</Header>
        <Hint>
            Copy these from the label on the back of your panel. Panels make a higher voltage when cold; too many in
            series can exceed the controller's limit on a cold morning and destroy it. The coldest morning starts
            25 °C below your coldest monthly average, because averages hide cold snaps; enter your area's record
            low if you know it.
        </Hint>
        <Grid>
            {panelField('voc', 'Open-circuit voltage, Voc (V)', o.voc, PANEL_DEFAULTS.voc, 0.1)}
            {panelField('vmp', 'Max-power voltage, Vmp (V)', o.vmp, PANEL_DEFAULTS.vmp, 0.1)}
            {panelField('isc', 'Short-circuit current, Isc (A)', o.isc, PANEL_DEFAULTS.isc, 0.1)}
            {panelField('bvoc', 'Voc temperature coefficient (%/°C)', o.betaVoc, PANEL_DEFAULTS.bvoc, 0.01, 0)}
            <Grid.Col span={{base: 6, sm: 3}}>
                <Select label='Controller type'
                        data={Object.entries(CONTROLLERS).map(([value, c]) => ({value, label: c.label}))}
                        value={o.controller} allowDeselect={false}
                        onChange={v => set({ctl: v === 'mppt' ? null : v})}/>
            </Grid.Col>
            <Grid.Col span={{base: 6, sm: 3}}>
                <NumberInput label='Controller max PV voltage (V)' name='cmax' value={o.controllerMaxVoltage} min={0}
                             step={10} onChange={v => setNumber('cmax', v, DEFAULT_CONTROLLER_MAX_VOLTAGE)}/>
            </Grid.Col>
            <Grid.Col span={{base: 6, sm: 3}}>
                <NumberInput label='Panels in series' name='ns' value={o.series} min={1} step={1}
                             onChange={v => setNumber('ns', v, 1)}/>
            </Grid.Col>
            <Grid.Col span={{base: 6, sm: 3}}>
                <NumberInput label='Coldest morning (°C)' name='tmin' value={o.coldest} step={1}
                             onChange={v => setNumber('tmin', v, o.defaultTmin)}/>
            </Grid.Col>
        </Grid>
        {/* The cold-morning limit depends on the site's temperatures; do not show a placeholder's verdict. */}
        {!temperaturesKnown && <div style={{marginTop: '1em'}}><Loader size='xs' label='Loading temperatures'/></div>}
        {temperaturesKnown && <>
            <Table style={{marginTop: '1em'}}>
                <Table.Body>
                    <Table.Row>
                        <Table.Cell>Strings</Table.Cell>
                        <Table.Cell>{z.strings} of {o.series} panel{o.series === 1 ? '' : 's'} in series</Table.Cell>
                    </Table.Row>
                    <Table.Row>
                        <Table.Cell>String voltage on the coldest morning</Table.Cell>
                        <Table.Cell>{fmt(z.stringColdVoc, 1)} V (most panels in series: {z.maxSeries})</Table.Cell>
                    </Table.Row>
                    <Table.Row>
                        <Table.Cell>Controller current rating, at least</Table.Cell>
                        <Table.Cell>{fmt(z.current)} A</Table.Cell>
                    </Table.Row>
                </Table.Body>
            </Table>
            {z.overVoltage && <Message kind='error' title='Too much voltage for the controller'>
                {o.series} panels in series reach {fmt(z.stringColdVoc, 1)} V on a {o.coldest} °C morning,
                over the controller's {o.controllerMaxVoltage} V limit. Use at most {z.maxSeries} in series, or a
                controller rated for more voltage.
            </Message>}
            {z.lowVoltage && <Message kind='warning' title='Too little voltage to charge'>
                {o.controller === 'pwm' && z.pwmFraction === 0
                    ? `${o.series} panel${o.series === 1 ? '' : 's'} in series cannot reach the ${o.systemVoltage} V `
                    + 'battery\'s charging voltage, so a PWM controller cannot charge it at all.'
                    : `On a hot day ${o.series} panel${o.series === 1 ? '' : 's'} in series may not stay far enough `
                    + 'above the battery\'s charging voltage for the controller to charge well.'}
                {' '}Put more panels in series, or use a lower system voltage.
            </Message>}
            {z.unevenStrings && <Message kind='warning' title='Uneven strings'>
                Your panel count does not divide evenly into strings of {o.series}. Every string should have the same
                number of panels.
            </Message>}
            {o.controller === 'mppt' && z.current > HIGH_CURRENT && o.systemVoltage < 48 &&
                <Message kind='info' title='High current'>
                    {fmt(z.current)} A needs a large controller and thick wire. A higher system voltage would cut the
                    current.
                </Message>}
        </>}
    </>;
}

/**
 * The off-grid sizing tab.
 *
 * @param {Object} worst   the worst month for a 1 kW DC array, or null when there is no estimate
 * @param {number[]} temperatures  monthly average temperatures at the site, °C
 * @param {boolean} loading       the built-in sunlight and temperature data is still downloading
 */
export function SolarOffGrid({get, set, setNumber, s, worst, temperatures, loading}) {
    const o = offGridFromParams(get, temperatures);
    const r = offGridResults(o, worst, s.panelWatts, s.panelCount);

    return <div style={{marginTop: '1em'}}>
        <Hint>
            Size a battery system to run your devices through the darkest month. Production here is DC; the
            Inverter section under Fine-tune is for grid-tie systems and does not apply.
        </Hint>
        <LoadsSection o={o} r={r} set={set} setNumber={setNumber}/>
        <BatterySection o={o} set={set} setNumber={setNumber}/>
        {worst && <NeedsSection o={o} r={r} worst={worst} s={s} setNumber={setNumber}/>}
        {!worst && loading && <div style={{marginTop: '1em'}}><Loader size='xs' label='Loading sunlight data'/></div>}
        {!worst && !loading && <div style={{marginTop: '1em'}}>
            <Message kind='info' title='Almost there'>Enter a location above to size the system.</Message>
        </div>}
        <ControllerSection o={o} r={r} set={set} setNumber={setNumber}
                           temperaturesKnown={!loading || get('tmin') !== null}/>
    </div>;
}
