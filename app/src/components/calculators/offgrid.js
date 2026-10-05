// Pure calculation functions for the Solar calculator's off-grid sizing.  No React here.
//
// Off-grid systems are sized for the worst month, not the yearly average: the battery has to carry the
// loads through a run of cloudy days, and the panels have to refill it in the darkest month.
//
// Energy is Wh, power W, voltage V, current A, temperature °C, percentages 0-100.

const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));

// ---------------------------------------------------------------------------
// Loads
// ---------------------------------------------------------------------------

// Devices are stored in the URL as "name~watts~hours" joined by "|".
const ROW_SEPARATOR = '|';
const FIELD_SEPARATOR = '~';

export function parseLoads(text) {
    if (!text) {
        return [];
    }
    return text.split(ROW_SEPARATOR).map(row => {
        const [name = '', watts = '', hours = ''] = row.split(FIELD_SEPARATOR);
        return {name, watts, hours};
    });
}

export function formatLoads(rows) {
    // The separators cannot appear inside a name.
    const clean = value => `${value ?? ''}`.replace(/[|~]/g, ' ');
    return rows.map(r => [clean(r.name), clean(r.watts), clean(r.hours)].join(FIELD_SEPARATOR)).join(ROW_SEPARATOR);
}

// Watt-hours a device uses per day; blank or invalid values count as nothing.
export function loadWh({watts, hours}) {
    const w = Number(watts), h = Number(hours);
    return w > 0 && h > 0 ? w * Math.min(h, 24) : 0;
}

export function dailyLoadWh(rows) {
    return rows.reduce((acc, row) => acc + loadWh(row), 0);
}

// ---------------------------------------------------------------------------
// Battery
// ---------------------------------------------------------------------------

export const BATTERIES = {
    lfp: {
        label: 'Lithium iron phosphate (LiFePO4)',
        // Usable depth of discharge, and round-trip efficiency.
        dod: 80, efficiency: 95,
    },
    lead: {
        label: 'Lead-acid (flooded or AGM)',
        // Discharging below half shortens a lead-acid battery's life sharply.
        dod: 50, efficiency: 85,
    },
};

export const SYSTEM_VOLTAGES = [12, 24, 48];

// Charging voltage of a battery bank, used to judge PWM controllers and MPPT headroom.
export const chargeVoltage = systemVoltage => systemVoltage * 1.2;

// Share of rated capacity a cold lead-acid battery delivers: about 80% at 0 °C and 60% at -20 °C, as on
// typical manufacturer curves.  Lithium batteries are not derated here; they must not be CHARGED below
// 0 °C, which is a warning instead (see batteryWarnings).
export function leadAcidCapacityFactor(temperature) {
    if (!Number.isFinite(temperature) || temperature >= 20) {
        return 1;
    }
    return clamp(1 - 0.01 * (20 - temperature), 0.5, 1);
}

/**
 * Battery bank for `days` of the daily load with no sun.
 *
 * @returns {{usableWh: number, nominalWh: number, ah: number}}
 */
export function sizeBattery({loadWh: daily, days, dod, voltage, capacityFactor = 1}) {
    if (!(daily > 0) || !(days > 0) || !(dod > 0) || !(voltage > 0)) {
        return null;
    }
    const usableWh = daily * days;
    const nominalWh = usableWh / (dod / 100) / capacityFactor;
    return {usableWh, nominalWh, ah: nominalWh / voltage};
}

// ---------------------------------------------------------------------------
// Array
// ---------------------------------------------------------------------------

/**
 * kW of panels needed to supply the daily load in the worst month.
 *
 * @param {number} loadWh             daily energy the battery bank must supply
 * @param {number} worstDailyPerKwp   DC kWh per day per kW of panels in the worst month
 * @param {number} batteryEfficiency  round-trip efficiency, %; conservatively applied to all energy
 */
export function requiredKwp(loadWh, worstDailyPerKwp, batteryEfficiency) {
    if (!(loadWh > 0) || !(worstDailyPerKwp > 0) || !(batteryEfficiency > 0)) {
        return null;
    }
    return (loadWh / 1000) / (worstDailyPerKwp * batteryEfficiency / 100);
}

// ---------------------------------------------------------------------------
// Charge controller and strings
// ---------------------------------------------------------------------------

export const CONTROLLERS = {
    mppt: {label: 'MPPT'},
    pwm: {label: 'PWM'},
};

// A PWM controller connects a string of `series` panels straight to the battery, holding it at the battery's
// charging voltage instead of its best voltage (Vmp), so only this share of its power is used:
//  - charging voltage at or above the string's Voc: no current flows, nothing is delivered;
//  - between Vmp and Voc: the current falls from its maximum toward zero at Voc (taken as linear);
//  - below Vmp: full current at the lower voltage, charging voltage / Vmp of the power.
export function pwmUsableFraction(vmp, voc, series, systemVoltage) {
    const stringVmp = vmp * series, stringVoc = voc * series;
    if (!(stringVmp > 0) || !(stringVoc > 0)) {
        return 1;
    }
    const charge = chargeVoltage(systemVoltage);
    if (charge >= stringVoc) {
        return 0;
    }
    if (charge > stringVmp) {
        return (charge / stringVmp) * (stringVoc - charge) / (stringVoc - stringVmp);
    }
    return charge / stringVmp;
}

// Panel open-circuit voltage rises as it gets colder.  `betaVoc` is its temperature coefficient, %/°C, which is
// negative for every silicon panel; a coefficient typed without its minus sign is treated as negative, because
// a positive one would hide the cold-weather rise that destroys controllers.
export function coldVoc(voc, betaVoc, temperature) {
    return voc * (1 - (Math.abs(betaVoc) / 100) * (temperature - 25));
}

/**
 * Wiring and controller checks for an array of `panelCount` panels, `series` of them per string.
 */
export function controllerSizing({
                                     panelCount, panelWatts, series, voc, vmp, isc, betaVoc, coldest,
                                     controller, controllerMaxVoltage, systemVoltage,
                                 }) {
    const strings = series > 0 ? Math.ceil(panelCount / series) : 0;
    const arrayWatts = panelCount * panelWatts;
    const stringColdVoc = coldVoc(voc, betaVoc, coldest) * series;
    const maxSeries = Math.floor(controllerMaxVoltage / coldVoc(voc, betaVoc, coldest));

    let current;
    if (controller === 'pwm') {
        // Panel current passes straight through, plus the usual 25% margin.
        current = isc * strings * 1.25;
    } else {
        current = arrayWatts / systemVoltage * 1.25;
    }
    return {
        strings,
        arrayWatts,
        stringColdVoc,
        maxSeries,
        current,
        overVoltage: stringColdVoc > controllerMaxVoltage,
        // An MPPT controller needs the string's voltage, which sags about 15% in summer heat, to stay above the
        // battery's charging voltage with some headroom.  A PWM controller loses power as soon as the string's
        // Vmp is below the charging voltage, and all of it once its Voc is.
        lowVoltage: controller === 'mppt'
            ? vmp * series * 0.85 < chargeVoltage(systemVoltage) + 5
            : vmp * series < chargeVoltage(systemVoltage),
        unevenStrings: series > 0 && panelCount % series !== 0,
        pwmFraction: controller === 'pwm' ? pwmUsableFraction(vmp, voc, series, systemVoltage) : 1,
    };
}

// Default for the coldest morning when the user has not entered one: well below the coldest monthly
// average, because monthly averages hide cold snaps.  Errs cold, since underestimating the cold is what
// destroys controllers.
export const COLD_MARGIN = 25;

export function defaultColdest(monthlyTemperatures) {
    const known = (monthlyTemperatures || []).filter(Number.isFinite);
    if (known.length === 0) {
        return -20;
    }
    return Math.round(Math.min(...known) - COLD_MARGIN);
}

// Advice about the battery for the site's climate.  `coldestMonthly` is the coldest monthly average, °C.
export function batteryWarnings({battery, outdoors, coldestMonthly}) {
    const warnings = [];
    if (!outdoors || !Number.isFinite(coldestMonthly)) {
        return warnings;
    }
    if (battery === 'lfp' && coldestMonthly < 5) {
        warnings.push('Lithium (LiFePO4) batteries are damaged by charging below 0 °C. Keep them indoors, or buy '
            + 'batteries with built-in heaters or low-temperature charge protection.');
    }
    if (battery === 'lead' && coldestMonthly < 20) {
        warnings.push(`Cold lead-acid batteries hold less: the bank is enlarged to deliver ` +
            `${Math.round(leadAcidCapacityFactor(coldestMonthly) * 100)}% of its rating in the coldest month. ` +
            'Discharged lead-acid batteries can also freeze and crack; keep them charged.');
    }
    return warnings;
}
