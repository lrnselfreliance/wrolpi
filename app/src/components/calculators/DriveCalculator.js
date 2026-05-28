import React from "react";
import {Form, Header, Segment, Table} from "../Theme";
import {Button, GridColumn, GridRow, Input, Label, TableBody, TableCell, TableRow} from "semantic-ui-react";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {ColoredInput} from "../Apps";
import {InfoPopup, roundDigits, Toggle, useLocalStorage} from "../Common";
import {Media} from "../../contexts/contexts";

// Pure calculation functions for the Drive Ratio calculator (pulleys, gears, sprockets).
//
// All three drive types obey one relation between a driver and a driven element:
//
//     s1 * n1 = s2 * n2
//
// where `s` is the element "size" (pitch diameter for pulleys, tooth count for gears
// and sprockets) and `n` is the rotational speed (RPM).  The driven element spins
// slower when it is larger, and its torque increases by the same ratio.
//
// These functions are intentionally unit-agnostic: callers must pass consistent units
// (e.g. all lengths in inches, or all in millimeters) and the result is returned in
// those same units.  The React component is responsible for unit selection/display.

// Divide `a` by `b`, returning null when the result would not be a finite number.
// This keeps empty/zero inputs from producing NaN or Infinity in the UI.
const safeDiv = (a, b) => {
    const result = a / b;
    return Number.isFinite(result) ? result : null;
};

// Solve for the one drive value the user has not recently edited, using s1*n1 = s2*n2.
// `target` is the field to compute ('s1' | 's2' | 'n1' | 'n2'); the remaining three are
// read from `values`.  Returns the computed value, or null when it cannot be determined.
export function computeDriveValue(target, {s1, s2, n1, n2}) {
    switch (target) {
        case 's1':
            return safeDiv(s2 * n2, n1);
        case 's2':
            return safeDiv(s1 * n1, n2);
        case 'n1':
            return safeDiv(s2 * n2, s1);
        case 'n2':
            return safeDiv(s1 * n1, s2);
        default:
            return null;
    }
}

// Speed/torque ratio of the drive: driven size over driver size (s2 / s1).
// Equals driverRPM / drivenRPM, and equals the factor by which torque is multiplied.
export function driveRatio(s1, s2) {
    return safeDiv(s2, s1);
}

// Output torque from an input torque, given the driver and driven sizes.
// Torque is multiplied by the drive ratio (s2 / s1).
export function torqueOut(torqueIn, s1, s2) {
    const ratio = driveRatio(s1, s2);
    return ratio === null ? null : torqueIn * ratio;
}

// Surface (pitch-line) velocity of a rotating element: pi * diameter * rpm.
// For a belt drive this is the belt speed; for gears/sprockets the pitch-line velocity.
// Returns length-units per minute (matching the units of `diameter`).
export function surfaceSpeed(diameter, rpm) {
    return Math.PI * diameter * rpm;
}

// Surface speed in a human-friendly unit: ft/min (imperial) or m/s (metric).
// `diameter` is in inches when metric is false, or millimeters when metric is true.
// Returns {value, unit}, or null when it cannot be computed.
export function surfaceSpeedDisplay(diameter, rpm, metric) {
    if (!(diameter > 0) || !(rpm > 0)) {
        return null;
    }
    const perMinute = surfaceSpeed(diameter, rpm); // in/min or mm/min
    return metric
        ? {value: perMinute / 60000, unit: 'm/s'}   // mm/min -> m/s
        : {value: perMinute / 12, unit: 'ft/min'};  // in/min -> ft/min
}

// Length of an open belt around two pulleys of pitch diameters d1 and d2 whose centers
// are `centerDistance` apart.  Returns the belt length in the same units as the inputs,
// or null when the geometry is impossible (centers closer than the pulleys touching).
//
// This is the standard shop/textbook approximation:
//   L = 2C + (pi/2)(d1 + d2) + (d2 - d1)^2 / (4C)
// It is accurate when C is comfortably larger than (d1 + d2)/2 and degrades as the
// centers tighten toward that limit, where the pulleys would touch.
export function beltLength(d1, d2, centerDistance) {
    // Pulleys overlap when the centers are within the sum of their radii — no valid belt.
    if (!(d1 > 0) || !(d2 > 0) || !Number.isFinite(centerDistance) || centerDistance <= (d1 + d2) / 2) {
        return null;
    }
    return (
        2 * centerDistance +
        (Math.PI / 2) * (d1 + d2) +
        Math.pow(d2 - d1, 2) / (4 * centerDistance)
    );
}

// Pitch diameter of a chain sprocket with `teeth` teeth and a given chain `pitch`.
//   PD = pitch / sin(pi / teeth)
export function chainPitchDiameter(teeth, pitch) {
    if (!Number.isFinite(teeth) || teeth < 1) {
        return null;
    }
    return safeDiv(pitch, Math.sin(Math.PI / teeth));
}

// Exact chain length, expressed in pitches (links), for two sprockets t1/t2 teeth whose
// centers are `centerDistance` apart, using a chain of the given `pitch`.  Returns null
// when the geometry is impossible (centers closer than the sprockets touching).
//   L = (t1 + t2)/2 + 2*(C/p) + ((t2 - t1)/(2*pi))^2 / (C/p)
export function chainLengthPitches(t1, t2, centerDistance, pitch) {
    const pd1 = chainPitchDiameter(t1, pitch);
    const pd2 = chainPitchDiameter(t2, pitch);
    // Sprockets overlap when the centers are within the sum of their pitch radii.
    if (pd1 === null || pd2 === null || !Number.isFinite(centerDistance)
        || centerDistance <= (pd1 + pd2) / 2) {
        return null;
    }
    const centerPitches = safeDiv(centerDistance, pitch);
    if (centerPitches === null || centerPitches <= 0) {
        return null;
    }
    return (
        (t1 + t2) / 2 +
        2 * centerPitches +
        Math.pow((t2 - t1) / (2 * Math.PI), 2) / centerPitches
    );
}

// Chain length rounded up to the nearest even number of pitches (chains join in pairs).
export function chainLengthPitchesEven(t1, t2, centerDistance, pitch) {
    const exact = chainLengthPitches(t1, t2, centerDistance, pitch);
    return exact === null ? null : 2 * Math.ceil(exact / 2);
}

// Pitch diameter of a metric gear: teeth * module (module in mm).
export function gearPitchDiameterMetric(teeth, module) {
    return teeth * module;
}

// Pitch diameter of an imperial gear: teeth / diametralPitch (teeth per inch).
export function gearPitchDiameterImperial(teeth, diametralPitch) {
    return safeDiv(teeth, diametralPitch);
}

// Center distance between two meshing gears (or any two tangent pitch circles):
// half the sum of their pitch diameters.
export function centerDistanceFromPitchDiameters(d1, d2) {
    return (d1 + d2) / 2;
}

// ---------------------------------------------------------------------------
// Diagram geometry — pure helpers used to draw the schematic SVG.  No new
// dependencies: the component renders plain inline SVG from these numbers.
// ---------------------------------------------------------------------------

// The two external ("open", non-crossing) tangent lines of two circles.
// Returns two segments, each {a: [x,y], b: [x,y]}, touching circle 1 then circle 2.
// Used to draw a belt (pulleys) or chain (sprockets) wrapping both wheels.
export function externalBeltTangents(x1, y1, r1, x2, y2, r2) {
    const d = Math.hypot(x2 - x1, y2 - y1);
    if (d === 0) {
        return null;
    }
    const gamma = Math.atan2(y2 - y1, x2 - x1);
    // (r1 - r2) / d can drift slightly outside [-1, 1] from rounding; clamp it.
    const ratio = Math.max(-1, Math.min(1, (r1 - r2) / d));
    const beta = Math.asin(ratio);
    const point = (cx, cy, r, angle) => [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
    const a1 = gamma + (Math.PI / 2 - beta);
    const a2 = gamma - (Math.PI / 2 - beta);
    return [
        {a: point(x1, y1, r1, a1), b: point(x2, y2, r2, a1)},
        {a: point(x1, y1, r1, a2), b: point(x2, y2, r2, a2)},
    ];
}

// SVG polygon points for a schematic toothed wheel (gear or sprocket).
// Not an involute — `teeth` trapezoidal teeth alternating between rOuter (tip)
// and rInner (root).  `tipFrac` is the fraction of each tooth period spent at the tip.
// Returns a string suitable for an SVG <polygon points={...}/>.
export function gearPoints(cx, cy, rOuter, rInner, teeth, tipFrac = 0.5) {
    const count = Math.max(3, Math.round(teeth));
    const step = (2 * Math.PI) / count;
    const gap = (step * (1 - tipFrac)) / 2;
    const points = [];
    const push = (r, angle) =>
        points.push(`${(cx + r * Math.cos(angle)).toFixed(2)},${(cy + r * Math.sin(angle)).toFixed(2)}`);
    for (let i = 0; i < count; i++) {
        const a0 = i * step;
        push(rInner, a0);                       // root before the tooth
        push(rOuter, a0 + gap);                 // rising flank
        push(rOuter, a0 + gap + step * tipFrac);// tooth tip
        push(rInner, a0 + step);                // falling flank into next root
    }
    return points.join(' ');
}

// ---------------------------------------------------------------------------
// React component
// ---------------------------------------------------------------------------

// Per-mode wording.  All three drive types share the same math; only the size
// label (and the diagram) differ.
const MODES = {
    pulley: {button: 'Pulley', icon: 'circle outline', sizeLabel: 'Diameter', toothed: false},
    gear: {button: 'Gear', icon: 'cogs', sizeLabel: 'Teeth', toothed: true},
    sprocket: {button: 'Sprocket', icon: 'cog', sizeLabel: 'Teeth', toothed: true},
};

// Distinct, colorblind-friendly wheel colors (Paul Tol's bright palette):
// blue, red, green, yellow, cyan, purple.  Grey is reserved as a neutral.
const ELEMENT_COLORS = ['#4477aa', '#ee6677', '#228833', '#ccbb44', '#66ccee', '#aa3377'];

const MIN_ELEMENTS = 2;
const MAX_ELEMENTS = ELEMENT_COLORS.length;  // 6 — one per palette color

// Placeholder sizes so the diagram is visible before the user types anything.
const DEFAULT_DIAGRAM_SIZES = {
    pulley: [4, 8, 6, 10, 5, 7],
    toothed: [12, 24, 18, 30, 15, 21],
};

// Explanation shown in the Center Distance info popup (pulley and sprocket modes).
const CENTER_DISTANCE_INFO = 'The straight-line distance between the centers of the two shafts — '
    + 'the driver and driven axles. It sets how far apart the wheels are mounted, which '
    + 'determines the belt or chain length.';

// Disclaimer shown in the Output Torque info popup.
const TORQUE_INFO = 'Ideal output torque, assuming no losses. Real belt, chain, and gear drives '
    + 'lose a few percent to friction and slip, so actual output torque is somewhat lower.';

// Pick black or white label text for legibility on a given background color.
function textColorFor(hex) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    return luminance > 0.6 ? '#000000' : '#ffffff';
}

const emptyElement = () => ({size: '', rpm: ''});
const driveInitialState = {elements: [emptyElement(), emptyElement()], lastUpdated: []};

// Solve a single shared belt/chain train: every wheel rides one belt, so size*rpm is the
// same constant K for all of them.  The most recently edited wheel that has both a size
// and an RPM anchors K; every other wheel's RPM follows from its size (or its size from
// its RPM).  Intermediate wheels set their own speed but do not change the overall
// first-to-last ratio (they are idlers).
//
// Re-anchoring is intentional and supported: if a user later provides both size+ rpm on
// a different wheel, that wheel becomes the new anchor and all other wheels (including
// ones the user had previously entered values for) are re-solved from the new K.
function solveTrain(elements, lastUpdated) {
    const num = (v) => (v === '' ? null : Number(v));
    const anchor = lastUpdated.find((i) =>
        elements[i] && num(elements[i].size) > 0 && num(elements[i].rpm) > 0);
    console.debug('[DriveCalc] solveTrain', {
        lastUpdated: [...lastUpdated],
        anchor,
        k: anchor !== undefined ? num(elements[anchor].size) * num(elements[anchor].rpm) : null
    });
    if (anchor === undefined) {
        return elements;
    }
    const k = num(elements[anchor].size) * num(elements[anchor].rpm);
    return elements.map((el, i) => {
        if (i === anchor) {
            return el;
        }
        const size = num(el.size), rpm = num(el.rpm);
        if (size > 0) {
            return {...el, rpm: String(roundDigits(k / size, 4))};
        }
        if (rpm > 0) {
            return {...el, size: String(roundDigits(k / rpm, 4))};
        }
        return el;
    });
}

function driveReducer(state, action) {
    if (action.type === 'add') {
        if (state.elements.length >= MAX_ELEMENTS) {
            return state;
        }
        return {...state, elements: [...state.elements, emptyElement()]};
    }
    if (action.type === 'remove') {
        if (state.elements.length <= MIN_ELEMENTS) {
            return state;
        }
        const elements = state.elements.filter((_, i) => i !== action.index);
        // Drop the removed index from the edit history and shift higher indices down.
        const lastUpdated = state.lastUpdated
            .filter((i) => i !== action.index)
            .map((i) => (i > action.index ? i - 1 : i));
        return {...state, elements: solveTrain(elements, lastUpdated), lastUpdated};
    }
    if (action.type === 'field') {
        const {index, field, value} = action;
        // Negative sizes/speeds are meaningless here; clamp to a positive magnitude.
        const clamped = value === '' ? '' : String(Math.abs(Number(value)));
        const elements = state.elements.map((el, i) =>
            i === index ? {...el, [field]: clamped} : el);
        const lastUpdated = [index, ...state.lastUpdated.filter((i) => i !== index)];
        console.debug('[DriveCalc] field', {index, field, value: clamped, lastUpdated: [...lastUpdated]});
        // Only update the field the user is actively typing. Solving is debounced in the component.
        return {...state, elements, lastUpdated};
    }
    if (action.type === 'solve') {
        return {...state, elements: solveTrain(state.elements, state.lastUpdated)};
    }
    return state;
}

// Schematic, dependency-free SVG of the drive train.  Draws one colored wheel per
// element, connected by a single belt/chain (or meshing teeth for gears).  Sizes fall
// back to placeholders so a diagram is always visible, even before the user types.
function DriveDiagram({mode, sizes}) {
    const toothed = MODES[mode].toothed;
    const defaults = toothed ? DEFAULT_DIAGRAM_SIZES.toothed : DEFAULT_DIAGRAM_SIZES.pulley;
    const nums = sizes.map((s, i) => (Number(s) > 0 ? Number(s) : defaults[i % defaults.length]));
    const maxSize = Math.max(...nums);

    // Map each size onto a drawn pitch radius, keeping small wheels visible.
    const MAX_R = 60, MIN_R = 22, TOOTH = 6, PAD = 16;
    const radii = nums.map((s) => MIN_R + (MAX_R - MIN_R) * (s / maxSize));
    const extent = (r) => (toothed ? r + TOOTH : r);
    const maxExtent = Math.max(...radii.map(extent));
    const cy = PAD + maxExtent;

    // Lay wheels left to right.  Gears mesh (pitch circles touch); belts/chains leave a gap.
    const gap = mode === 'gear' ? 0 : 54;
    const centers = [PAD + extent(radii[0])];
    for (let i = 1; i < radii.length; i++) {
        centers.push(centers[i - 1] + radii[i - 1] + radii[i] + gap);
    }
    const width = centers[centers.length - 1] + extent(radii[radii.length - 1]) + PAD;
    const height = cy + maxExtent + PAD;

    const wheel = (cx, r, size, color) => {
        if (toothed) {
            const teeth = Math.max(6, Math.min(40, Math.round(size)));
            return <g>
                <polygon points={gearPoints(cx, cy, r + TOOTH, r - TOOTH, teeth)}
                         fill={color} stroke={color} strokeWidth={1} fillOpacity={0.9}/>
                <circle cx={cx} cy={cy} r={Math.max(6, r * 0.22)} fill='none' stroke='#fff' strokeWidth={2}/>
            </g>;
        }
        return <g>
            <circle cx={cx} cy={cy} r={r} fill={color} fillOpacity={0.9} stroke={color}/>
            <circle cx={cx} cy={cy} r={Math.max(5, r * 0.2)} fill='#fff'/>
        </g>;
    };

    return <svg viewBox={`0 0 ${width} ${height}`} width='100%'
                style={{maxWidth: `${width}px`, height: 'auto'}}>
        {mode !== 'gear' && centers.slice(1).map((_, idx) => {
            // Belt/chain between each adjacent pair of wheels, drawn behind the wheels.
            const segs = externalBeltTangents(centers[idx], cy, radii[idx], centers[idx + 1], cy, radii[idx + 1]);
            return segs && segs.map((seg, j) =>
                <line key={`${idx}-${j}`} x1={seg.a[0]} y1={seg.a[1]} x2={seg.b[0]} y2={seg.b[1]}
                      stroke='#999' strokeWidth={mode === 'sprocket' ? 5 : 7} strokeLinecap='round'/>);
        })}
        {centers.map((cx, i) =>
            <g key={i}>{wheel(cx, radii[i], nums[i], ELEMENT_COLORS[i % ELEMENT_COLORS.length])}</g>)}
    </svg>;
}

// Format the drive ratio as "N : 1" (reduction) or "1 : N" (overdrive).
function formatRatio(ratio) {
    if (ratio === null || !Number.isFinite(ratio) || ratio <= 0) {
        return '—';
    }
    return ratio >= 1
        ? `${roundDigits(ratio, 3)} : 1`
        : `1 : ${roundDigits(1 / ratio, 3)}`;
}

// Format a positive length/number with a unit, or an em-dash when unavailable.
function fmt(value, unit) {
    if (!Number.isFinite(value) || value <= 0) {
        return '—';
    }
    return unit ? `${roundDigits(value, 3)} ${unit}` : `${roundDigits(value, 3)}`;
}

// Format a {value, unit} surface-speed result, or an em-dash when unavailable.
function fmtSpeed(speed) {
    return speed ? `${roundDigits(speed.value, 3)} ${speed.unit}` : '—';
}

export function DriveCalculator() {
    const [mode, setMode] = React.useState('pulley');
    const [metric, setMetric] = useLocalStorage('drive_calculator_metric', false);
    const [state, dispatch] = React.useReducer(driveReducer, driveInitialState);
    const [torqueIn, setTorqueIn] = React.useState('');
    // Mode-specific auxiliary inputs (do not participate in the size*rpm solver).
    const [centerDistance, setCenterDistance] = React.useState('');
    const [gearTooth, setGearTooth] = React.useState('');  // module (metric) or diametral pitch (imperial)
    const [chainPitch, setChainPitch] = React.useState('');

    // Debounce solving so that typing a multi-digit number doesn't cause constant
    // re-solving + overwriting of other wheels with partial K values.
    const solveTimeoutRef = React.useRef(null);
    const scheduleSolve = React.useCallback(() => {
        if (solveTimeoutRef.current) clearTimeout(solveTimeoutRef.current);
        solveTimeoutRef.current = setTimeout(() => {
            dispatch({ type: 'solve' });
        }, 280);
    }, [dispatch]);

    React.useEffect(() => {
        return () => {
            if (solveTimeoutRef.current) clearTimeout(solveTimeoutRef.current);
        };
    }, []);

    const {sizeLabel, button, toothed} = MODES[mode];
    const {elements} = state;
    const twoElements = elements.length === 2;
    console.debug('[DriveCalc] render', elements.map((e, i) => ({i, size: e.size, rpm: e.rpm})), 'lastUpdated:', state.lastUpdated);
    const lengthUnit = metric ? 'mm' : 'in';
    const torqueUnit = metric ? 'N·m' : 'lb·ft';
    // Pulley diameters carry a length unit; gear/sprocket teeth are unitless.
    const sizeUnit = mode === 'pulley' ? ` (${lengthUnit})` : '';

    // Overall ratio is the first wheel -> the last wheel (intermediate wheels are idlers).
    const firstSize = Number(elements[0].size);
    const lastSize = Number(elements[elements.length - 1].size);
    const ratio = driveRatio(firstSize, lastSize);
    const outTorque = torqueIn !== '' ? torqueOut(Number(torqueIn), firstSize, lastSize) : null;

    const inputProps = {
        fluid: true,
        type: 'number',
        onSelect: e => e.target.select(),
        autoComplete: 'off',
    };
    // Each wheel's inputs use its diagram color so the form and the picture line up.
    const coloredField = (hex, labelText, value, onChange, extraProps = {}, name) =>
        <Input {...inputProps} {...extraProps} name={name} labelPosition='left' value={value} onChange={onChange}
               label={<Label style={{backgroundColor: hex, color: textColorFor(hex), borderColor: hex}}>
                   {labelText}</Label>}/>;
    // Auxiliary (non-solver) numeric input.
    const auxInput = (label, value, setter, name) =>
        <ColoredInput {...inputProps} name={name} label={label} value={value}
                      onChange={e => setter(e.target.value)}/>;

    // Pitch diameter of a wheel given the mode's extra parameter.  Pulley size IS the
    // pitch diameter; gears need a module/diametral-pitch, sprockets a chain pitch.
    const pitchDiameter = (size) => {
        if (mode === 'gear') {
            return metric ? gearPitchDiameterMetric(size, Number(gearTooth))
                : gearPitchDiameterImperial(size, Number(gearTooth));
        }
        if (mode === 'sprocket') {
            return chainPitchDiameter(size, Number(chainPitch));
        }
        return size;
    };

    // Belt/chain speed is constant across the train; compute it from any complete wheel.
    const speedEl = elements.find(el => Number(el.size) > 0 && Number(el.rpm) > 0);
    const trainSpeed = speedEl
        ? surfaceSpeedDisplay(pitchDiameter(Number(speedEl.size)), Number(speedEl.rpm), metric)
        : null;

    const modeButtons = <Button.Group style={{marginBottom: '1em', flexWrap: 'wrap'}}>
        {Object.entries(MODES).map(([key, m]) =>
            <Button key={key} type='button' icon={m.icon} content={m.button}
                    primary={mode === key} onClick={() => setMode(key)}/>)}
    </Button.Group>;

    // One row of inputs per wheel: size, RPM, and a remove button (above the minimum).
    const elementRows = elements.map((el, i) => {
        const hex = ELEMENT_COLORS[i % ELEMENT_COLORS.length];
        const onField = (field) => (e) => {
            dispatch({type: 'field', index: i, field, value: e.target.value});
            scheduleSolve();
        };
        // Teeth are whole numbers; pulley diameters stay continuous.
        const onSize = toothed
            ? (e) => {
                dispatch({type: 'field', index: i, field: 'size',
                    value: e.target.value === '' ? '' : String(Math.round(Math.abs(Number(e.target.value))))});
                scheduleSolve();
              }
            : onField('size');
        return {
            hex,
            sizeField: coloredField(hex, `#${i + 1} ${sizeLabel}${sizeUnit}`, el.size, onSize,
                toothed ? {step: 1, min: 1} : {}, `size-${i}`),
            rpmField: coloredField(hex, `#${i + 1} RPM`, el.rpm, onField('rpm'), {}, `rpm-${i}`),
            removeBtn: elements.length > MIN_ELEMENTS
                ? <Button type='button' basic color='red' icon='close' size='small'
                          aria-label={`Remove #${i + 1}`} onClick={() => dispatch({type: 'remove', index: i})}/>
                : null,
        };
    });

    const addButton = <Button type='button' icon='plus' primary content={`Add ${button}`}
                              disabled={elements.length >= MAX_ELEMENTS}
                              onClick={() => dispatch({type: 'add'})}
                              style={{marginTop: '0.5em'}}/>;

    // Small colored swatch matching a wheel, used to label its detail rows.
    const swatch = (hex) => <span style={{
        display: 'inline-block', width: '0.8em', height: '0.8em', borderRadius: '2px',
        backgroundColor: hex, marginRight: '0.5em', verticalAlign: 'middle',
    }}/>;

    // Per-wheel pitch-diameter rows (gear/sprocket only).
    const pitchDiameterRows = toothed ? elements.map((el, i) =>
        <TableRow key={i}>
            <TableCell>{swatch(ELEMENT_COLORS[i % ELEMENT_COLORS.length])}#{i + 1} Pitch Diameter</TableCell>
            <TableCell>{fmt(pitchDiameter(Number(el.size)), lengthUnit)}</TableCell>
        </TableRow>) : null;

    // Pairwise belt/chain length and center distance only make sense for a two-wheel
    // drive; with 3+ wheels they depend on the physical layout, so they are omitted.
    let detailRows;
    if (mode === 'pulley') {
        const belt = twoElements ? beltLength(firstSize, lastSize, Number(centerDistance)) : null;
        detailRows = <>
            {twoElements && <>
                <TableRow>
                    <TableCell width={6}>Center Distance <InfoPopup content={CENTER_DISTANCE_INFO}/></TableCell>
                    <TableCell>{auxInput(`Center Distance (${lengthUnit})`, centerDistance, setCenterDistance, "centerDistance")}</TableCell>
                </TableRow>
                <TableRow>
                    <TableCell>Belt Length</TableCell>
                    <TableCell>{fmt(belt, lengthUnit)}</TableCell>
                </TableRow>
            </>}
            <TableRow>
                <TableCell width={6}>Belt Speed</TableCell>
                <TableCell>{fmtSpeed(trainSpeed)}</TableCell>
            </TableRow>
        </>;
    } else if (mode === 'gear') {
        const paramLabel = metric ? 'Module (mm)' : 'Diametral Pitch (1/in)';
        const pd1 = pitchDiameter(firstSize), pd2 = pitchDiameter(lastSize);
        const cd = twoElements && pd1 > 0 && pd2 > 0 ? centerDistanceFromPitchDiameters(pd1, pd2) : null;
        detailRows = <>
            <TableRow>
                <TableCell width={6}>{paramLabel}</TableCell>
                <TableCell>{auxInput(paramLabel, gearTooth, setGearTooth, "gearParam")}</TableCell>
            </TableRow>
            {pitchDiameterRows}
            {twoElements && <TableRow>
                <TableCell>Center Distance</TableCell>
                <TableCell>{fmt(cd, lengthUnit)}</TableCell>
            </TableRow>}
            <TableRow>
                <TableCell>Pitch-Line Velocity</TableCell>
                <TableCell>{fmtSpeed(trainSpeed)}</TableCell>
            </TableRow>
        </>;
    } else {  // sprocket
        const pitch = Number(chainPitch);
        const links = twoElements && pitch > 0
            ? chainLengthPitchesEven(firstSize, lastSize, Number(centerDistance), pitch)
            : null;
        detailRows = <>
            <TableRow>
                <TableCell width={6}>Chain Pitch</TableCell>
                <TableCell>{auxInput(`Chain Pitch (${lengthUnit})`, chainPitch, setChainPitch, "chainPitch")}</TableCell>
            </TableRow>
            {twoElements && <TableRow>
                <TableCell>Center Distance <InfoPopup content={CENTER_DISTANCE_INFO}/></TableCell>
                <TableCell>{auxInput(`Center Distance (${lengthUnit})`, centerDistance, setCenterDistance, "centerDistance")}</TableCell>
            </TableRow>}
            {pitchDiameterRows}
            {twoElements && <TableRow>
                <TableCell>Chain Length</TableCell>
                <TableCell>{links === null ? '—' : `${links} pitches`}</TableCell>
            </TableRow>}
            <TableRow>
                <TableCell>Chain Speed</TableCell>
                <TableCell>{fmtSpeed(trainSpeed)}</TableCell>
            </TableRow>
        </>;
    }

    return <Form>
        <Header as='h1'>Drive Ratio</Header>

        <div style={{marginBottom: '1em'}}>{modeButtons}</div>
        <div style={{marginBottom: '1em'}}>
            <Toggle label={metric ? 'Metric (mm)' : 'Imperial (in)'}
                    checked={metric} onChange={() => setMetric(!metric)}/>
        </div>

        <Media at='mobile'>
            {elementRows.map(({sizeField, rpmField, removeBtn}, i) =>
                <div key={i} style={{marginBottom: '0.5em'}}>
                    <div style={{marginBottom: '0.25em'}}>{sizeField}</div>
                    <div style={{marginBottom: '0.25em'}}>{rpmField}</div>
                    {removeBtn}
                    {i < elementRows.length - 1 && <hr/>}
                </div>)}
        </Media>

        <Media greaterThanOrEqual='tablet'>
            <Grid verticalAlign='middle'>
                {elementRows.map(({sizeField, rpmField, removeBtn}, i) =>
                    <GridRow key={i}>
                        <GridColumn width={7}>{sizeField}</GridColumn>
                        <GridColumn width={7}>{rpmField}</GridColumn>
                        <GridColumn width={2}>{removeBtn}</GridColumn>
                    </GridRow>)}
            </Grid>
        </Media>

        <div>{addButton}</div>

        <Segment style={{textAlign: 'center', overflowX: 'auto'}}>
            <DriveDiagram mode={mode} sizes={elements.map(el => el.size)}/>
        </Segment>

        <Table definition unstackable>
            <TableBody>
                <TableRow>
                    <TableCell width={6}>Drive Ratio{' '}
                        <span style={{fontWeight: 'normal', opacity: 0.7}}>(#1 → #{elements.length})</span>
                    </TableCell>
                    <TableCell>{formatRatio(ratio)}</TableCell>
                </TableRow>
                <TableRow>
                    <TableCell>Torque Multiplier</TableCell>
                    <TableCell>{ratio === null ? '—' : `${roundDigits(ratio, 3)}×`}</TableCell>
                </TableRow>
                <TableRow>
                    <TableCell>Output Torque <InfoPopup content={TORQUE_INFO}/></TableCell>
                    <TableCell>
                        <ColoredInput {...inputProps} name="torqueIn" label={`Input Torque (${torqueUnit})`}
                                      value={torqueIn}
                                      onChange={e => setTorqueIn(e.target.value)}/>
                        {outTorque !== null && <span style={{marginLeft: '1em'}}>
                            = <b>{roundDigits(outTorque, 3)} {torqueUnit}</b>
                        </span>}
                    </TableCell>
                </TableRow>
            </TableBody>
        </Table>

        <Header as='h3' style={{marginTop: '1em'}}>{button} Details</Header>
        <Table definition unstackable>
            <TableBody>{detailRows}</TableBody>
        </Table>
    </Form>;
}

// Exported for testing
export {driveReducer};
