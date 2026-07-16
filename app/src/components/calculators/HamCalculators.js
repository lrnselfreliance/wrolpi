import React from "react";
import {TableBody, TableCell, TableHeader, TableHeaderCell, TableRow} from "semantic-ui-react";
import {Header, Table} from "../Theme";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {roundDigits} from "../Common";
import {ColoredInput} from "../Apps";

// ---------------------------------------------------------------------------
// Pure antenna math
//
// Wire antennas are shorter than free-space wavelength by ~5% (end effect).
// The ARRL / ham-radio constants are:
//   full-wave length (ft)  = 936 / f(MHz)
//   half-wave dipole (ft)  = 468 / f(MHz)   = full * 0.5
//   quarter-wave      (ft) = 234 / f(MHz)   = full * 0.25
//   5/8-wave          (ft) = 585 / f(MHz)   = full * 0.625
// Free-space wavelength uses the exact speed of light and is shown separately.
// ---------------------------------------------------------------------------

/** Speed of light in free space (m/s). */
export const SPEED_OF_LIGHT = 299792458;

/**
 * Feet of wire for one full electrical wavelength, including end-effect.
 * Free-space equivalent is ~984 / f; 936/984 ≈ 0.95 velocity factor.
 */
export const FULL_WAVE_FEET_PER_MHZ = 936;

/** Common antenna fractions shown in the calculator. */
export const ANTENNA_FRACTIONS = [
    {name: '½ Antenna Length', multiplier: 0.5},
    {name: '¼ Antenna Length', multiplier: 0.25},
    {name: '⅝ Antenna Length', multiplier: 0.625},
];

/**
 * Convert a decimal foot length into whole feet and inches.
 * Rounds to the nearest inch and carries 12 inches into an extra foot
 * (e.g. 3.96 ft → 4 ft 0 in, never "3 ft 12 in").
 *
 * @param {number} decimalFeet
 * @returns {[number, number]} [feet, inches]
 */
export function convertFeetToFeetAndInches(decimalFeet) {
    if (!Number.isFinite(decimalFeet) || decimalFeet < 0) {
        return [0, 0];
    }
    const totalInches = Math.round(decimalFeet * 12);
    const feet = Math.floor(totalInches / 12);
    const inches = totalInches % 12;
    return [feet, inches];
}

/**
 * Full-wave wire-antenna length in feet for a given frequency in MHz.
 * Returns null when frequency is not a positive finite number.
 *
 * @param {number} mhz
 * @returns {number|null}
 */
export function fullWaveFeet(mhz) {
    if (!Number.isFinite(mhz) || !(mhz > 0)) {
        return null;
    }
    return FULL_WAVE_FEET_PER_MHZ / mhz;
}

/**
 * Free-space wavelength in meters for a given frequency in MHz.
 * λ = c / f.  Returns null when frequency is not positive.
 *
 * @param {number} mhz
 * @returns {number|null}
 */
export function freeSpaceWavelengthMeters(mhz) {
    if (!Number.isFinite(mhz) || !(mhz > 0)) {
        return null;
    }
    return SPEED_OF_LIGHT / (mhz * 1e6);
}

/**
 * Frequency in MHz from a free-space wavelength in meters.
 * f = c / λ.  Returns null when wavelength is not positive.
 *
 * @param {number} meters
 * @returns {number|null}
 */
export function frequencyMhzFromWavelengthMeters(meters) {
    if (!Number.isFinite(meters) || !(meters > 0)) {
        return null;
    }
    return SPEED_OF_LIGHT / meters / 1e6;
}

/**
 * Convert a full-wave length in feet into the unit set used by the UI.
 *
 * @param {number} feetValue - full-wave length in feet
 * @returns {{feet: number, inches: number, meters: number, cm: number}}
 */
export function lengthUnitsFromFeet(feetValue) {
    const meters = feetValue * 0.3048;
    return {
        feet: feetValue,
        inches: feetValue * 12,
        meters,
        cm: meters * 100,
    };
}

/**
 * Scale a length-unit set by a fraction (0.5 half-wave, 0.25 quarter, etc.).
 *
 * @param {{feet: number, inches: number, meters: number, cm: number}} units
 * @param {number} multiplier
 * @returns {{feet: number, inches: number, meters: number, cm: number}}
 */
export function scaleLengthUnits(units, multiplier) {
    return {
        feet: units.feet * multiplier,
        inches: units.inches * multiplier,
        meters: units.meters * multiplier,
        cm: units.cm * multiplier,
    };
}

/**
 * All length units for the full-wave wire antenna at a given frequency.
 * Returns null when frequency is invalid.
 *
 * @param {number} mhz
 * @returns {{feet: number, inches: number, meters: number, cm: number}|null}
 */
export function fullWaveLengthUnits(mhz) {
    const feet = fullWaveFeet(mhz);
    if (feet === null) {
        return null;
    }
    return lengthUnitsFromFeet(feet);
}

/**
 * Antenna total length and per-leg length for a fraction of a full wave.
 * "Leg length" is half the total (center-fed dipole legs).
 *
 * @param {number} mhz
 * @param {number} multiplier - e.g. 0.5 for half-wave
 * @returns {{
 *   total: {feet: number, inches: number, meters: number, cm: number, feetInches: [number, number]},
 *   leg: {feet: number, inches: number, meters: number, cm: number, feetInches: [number, number]},
 * }|null}
 */
export function antennaFractionLengths(mhz, multiplier) {
    const full = fullWaveLengthUnits(mhz);
    if (full === null || !Number.isFinite(multiplier)) {
        return null;
    }
    const total = scaleLengthUnits(full, multiplier);
    const leg = scaleLengthUnits(total, 0.5);
    return {
        total: {
            ...total,
            feetInches: convertFeetToFeetAndInches(total.feet),
        },
        leg: {
            ...leg,
            feetInches: convertFeetToFeetAndInches(leg.feet),
        },
    };
}

// ---------------------------------------------------------------------------
// UI
// ---------------------------------------------------------------------------

const defaultMhzInputValue = '144.2';

export function DipoleAntennaCalculator() {
    const [mhz, setMhz] = React.useState(144.2);
    const [mhzInputValue, setMhzInputValue] = React.useState(defaultMhzInputValue);
    const [waveInputValue, setWaveInputValue] = React.useState(0);
    const [feet, setFeet] = React.useState(0);
    const [inches, setInches] = React.useState(0);
    const [meters, setMeters] = React.useState(0);
    const [cm, setCM] = React.useState(0);

    React.useEffect(() => {
        const units = fullWaveLengthUnits(mhz);
        if (!units) {
            setFeet(0);
            setInches(0);
            setMeters(0);
            setCM(0);
            setWaveInputValue('');
            return;
        }
        setFeet(units.feet);
        setInches(units.inches);
        setMeters(units.meters);
        setCM(units.cm);
        setWaveInputValue(roundDigits(freeSpaceWavelengthMeters(mhz)));
    }, [mhz]);

    const mhzStorageKey = 'dipole_mhz';
    const storageMhzValue = localStorage.getItem(mhzStorageKey);
    React.useEffect(() => {
        if (storageMhzValue) {
            const parsed = parseFloat(storageMhzValue);
            if (parsed > 0) {
                setMhz(parsed);
                setMhzInputValue(storageMhzValue);
            }
        }
    }, []);

    const handleMhzChange = (e, {value}) => {
        setMhzInputValue(value);
        const parsed = parseFloat(value);
        // Require a finite positive frequency so overflow (e.g. 1e999 → Infinity) does not stick.
        setMhz(value && Number.isFinite(parsed) && parsed > 0 ? parsed : 0);
        localStorage.setItem(mhzStorageKey, value);
    }

    const handleWaveChange = (e, {value}) => {
        setWaveInputValue(value);
        const parsed = parseFloat(value);
        if (value && Number.isFinite(parsed) && parsed > 0) {
            const newMhz = frequencyMhzFromWavelengthMeters(parsed);
            if (newMhz === null) {
                // Conversion failed (should not happen for finite positive λ); treat as invalid.
                setMhz(0);
                setMhzInputValue('');
                localStorage.setItem(mhzStorageKey, '');
                return;
            }
            setMhz(newMhz);
            setMhzInputValue(roundDigits(newMhz));
            localStorage.setItem(mhzStorageKey, String(roundDigits(newMhz)));
        } else {
            // Cleared / zero / non-finite wavelength: drop stale MHz and table results.
            setMhz(0);
            setMhzInputValue('');
            localStorage.setItem(mhzStorageKey, '');
        }
    }

    const [mhzSelected, setMhzSelected] = React.useState(true);
    const handleClick = (e, name) => {
        if (name === 'mhz') {
            setMhzSelected(true);
        } else {
            setMhzSelected(false);
        }
    }

    return <>
        <Header as='h2'>Dipole Antenna</Header>

        <Grid columns={2}>
            <Grid.Row>
                <Grid.Column>
                    <ColoredInput fluid
                                  label='MHz'
                                  labelPosition='right'
                                  value={mhzInputValue}
                                  onChange={handleMhzChange}
                                  onSelect={e => handleClick(e, 'mhz')}
                                  color={mhzSelected ? null : 'grey'}
                    />
                </Grid.Column>
                <Grid.Column>
                    <ColoredInput fluid
                                  label='Wavelength'
                                  labelPosition='right'
                                  value={waveInputValue}
                                  onChange={handleWaveChange}
                                  onSelect={e => handleClick(e, 'wave')}
                                  color={mhzSelected ? 'grey' : null}
                    />
                </Grid.Column>
            </Grid.Row>
        </Grid>

        {ANTENNA_FRACTIONS.map(i => {
            const [feet_, inches_] = convertFeetToFeetAndInches(feet * i.multiplier);
            const [half_feet, half_inches] = convertFeetToFeetAndInches(feet * i.multiplier / 2);
            return <Table key={i.name} size='large' striped unstackable>
                <TableHeader>
                    <TableRow>
                        <TableHeaderCell>{i.name}</TableHeaderCell>
                        <TableHeaderCell>Leg Length</TableHeaderCell>
                    </TableRow>
                </TableHeader>

                <TableBody>
                    <TableRow>
                        <TableCell>
                            {feet_} ft. {inches_} in.
                        </TableCell>
                        <TableCell>
                            {half_feet} ft. {half_inches} in.
                        </TableCell>
                    </TableRow>
                    <TableRow>
                        <TableCell>
                            {roundDigits(inches * i.multiplier)} inches
                        </TableCell>
                        <TableCell>
                            {roundDigits(inches * i.multiplier / 2)} inches
                        </TableCell>
                    </TableRow>
                    <TableRow>
                        <TableCell>
                            {roundDigits(meters * i.multiplier)} meters
                        </TableCell>
                        <TableCell>
                            {roundDigits(meters * i.multiplier / 2)} meters
                        </TableCell>
                    </TableRow>
                    <TableRow>
                        <TableCell>
                            {roundDigits(cm * i.multiplier)} cm.
                        </TableCell>
                        <TableCell>
                            {roundDigits(cm * i.multiplier / 2)} cm.
                        </TableCell>
                    </TableRow>
                </TableBody>
            </Table>
        })}
    </>
}
