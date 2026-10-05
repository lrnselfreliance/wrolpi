import {
    ambientTemperature,
    ashraeIam,
    averageDaySteps,
    cellTemperature,
    compassToSolarAzimuth,
    DAYS_IN_MONTH,
    dcPower,
    declination,
    DEFAULT_LOSSES,
    defaultAzimuth,
    diffuseHourlyRatio,
    erbsMonthlyDiffuseFraction,
    estimateProduction,
    extraterrestrialDaily,
    formatMonthly,
    inverterOutput,
    KLEIN_DAYS,
    optimalTilt,
    parseCoordinate,
    parseMonthly,
    poaIrradiance,
    solarCalculatorPath,
    sunPosition,
    sunsetHourAngle,
    totalHourlyRatio,
    totalLoss,
} from "./solar";

// A sunny 40°N GHI profile, kWh/m²/day, with a clearness index of about 0.6 year-round (Denver-like).
const GHI_40N = [2.6, 3.5, 4.7, 5.8, 6.5, 7.2, 7.0, 6.2, 5.2, 4.0, 2.9, 2.3];
const TEMP_40N = [0, 2, 6, 10, 15, 21, 24, 23, 18, 11, 4, 0];

const system = (overrides = {}) => ({
    latitude: 40,
    ghi: GHI_40N,
    temperature: TEMP_40N,
    kwp: 1,
    tilt: 40,
    azimuth: 180,
    ...overrides,
});

const integrate = (ratio, ws) => {
    // Midpoint rule over the day, ratios are per hour.
    const n = 2000, dw = 2 * ws / n;
    let sum = 0;
    for (let i = 0; i < n; i++) {
        sum += ratio(-ws + (i + 0.5) * dw, ws) * dw / 15;
    }
    return sum;
};

describe('sun geometry', () => {
    test('declination matches Cooper at the solstices and equinox', () => {
        expect(declination(172)).toBeCloseTo(23.45, 1); // June 21
        expect(declination(355)).toBeCloseTo(-23.45, 1); // December 21
        expect(Math.abs(declination(81))).toBeLessThan(0.5); // March 22
        // Klein's February day (D&B Table 1.6.1 lists -13.0).
        expect(declination(KLEIN_DAYS[1])).toBeCloseTo(-12.95, 1);
    });

    test('sunset hour angle is 90° at the equator and handles polar day and night', () => {
        expect(sunsetHourAngle(0, 20)).toBeCloseTo(90, 5);
        expect(sunsetHourAngle(40, 0)).toBeCloseTo(90, 5);
        expect(sunsetHourAngle(80, 20)).toBe(180);
        expect(sunsetHourAngle(80, -20)).toBe(0);
    });

    test('extraterrestrial daily irradiation matches Duffie & Beckman Example 1.10.1', () => {
        // 43°N on April 15: H0 = 33.8 MJ/m² = 9.39 kWh/m².
        expect(extraterrestrialDaily(43, 105)).toBeCloseTo(33.8 / 3.6, 1);
        expect(extraterrestrialDaily(80, 355)).toBe(0); // polar night
    });

    test('sun is due south at solar noon and east in the morning (northern hemisphere)', () => {
        const noon = sunPosition(40, 0, 0);
        expect(noon.azimuth).toBeCloseTo(0, 5);
        expect(noon.zenith).toBeCloseTo(40, 5);
        expect(sunPosition(40, 0, -45).azimuth).toBeLessThan(0);
        expect(sunPosition(40, 0, 45).azimuth).toBeGreaterThan(0);
    });

    test('compass azimuth converts to the Duffie & Beckman convention', () => {
        expect(compassToSolarAzimuth(180)).toBe(0);
        expect(compassToSolarAzimuth(90)).toBe(-90);
        expect(compassToSolarAzimuth(270)).toBe(90);
        expect(compassToSolarAzimuth(0)).toBe(180);
        expect(compassToSolarAzimuth(360)).toBe(180);
        expect(defaultAzimuth(40)).toBe(180);
        expect(defaultAzimuth(-33)).toBe(0);
    });
});

describe('monthly irradiation to steps', () => {
    test('Erbs monthly diffuse fraction follows both branches and clamps KT', () => {
        expect(erbsMonthlyDiffuseFraction(0.5, 80)).toBeCloseTo(0.3911, 4);
        expect(erbsMonthlyDiffuseFraction(0.5, 100)).toBeCloseTo(1.311 - 1.511 + 0.85675 - 0.227625, 4);
        expect(erbsMonthlyDiffuseFraction(0.95, 80)).toBeCloseTo(erbsMonthlyDiffuseFraction(0.8, 80), 10);
        expect(erbsMonthlyDiffuseFraction(0.1, 80)).toBeCloseTo(erbsMonthlyDiffuseFraction(0.3, 80), 10);
    });

    test('Liu & Jordan diffuse ratio integrates to one day', () => {
        for (const ws of [60, 90, 120, 180]) {
            expect(integrate(diffuseHourlyRatio, ws)).toBeCloseTo(1, 3);
        }
    });

    test('Collares-Pereira & Rabl total ratio integrates to about one day', () => {
        // The correlation is empirical, so it only approximately conserves the daily total; the
        // model normalizes it, but a large error here would mean a transcription mistake.
        for (const ws of [60, 90, 120]) {
            expect(Math.abs(integrate(totalHourlyRatio, ws) - 1)).toBeLessThan(0.03);
        }
    });

    test('average day steps add back up to the monthly GHI and diffuse', () => {
        const day = averageDaySteps(40, 5, 7.2);
        const sum = key => day.steps.reduce((acc, s) => acc + s[key] * s.hours, 0) / 1000;
        expect(sum('global')).toBeCloseTo(7.2, 6);
        expect(sum('diffuse')).toBeCloseTo(7.2 * day.diffuseFraction, 6);
        expect(day.steps.every(s => s.beam >= 0 && s.diffuse >= 0)).toBe(true);
        // Peak at solar noon.
        const peak = day.steps.reduce((a, b) => (b.global > a.global ? b : a));
        expect(Math.abs(peak.hourAngle)).toBeLessThan(5);
    });

    test('a supplied diffuse value is used instead of the Erbs estimate', () => {
        expect(averageDaySteps(40, 5, 7.2, 1.8).diffuseFraction).toBeCloseTo(0.25, 6);
    });

    test('polar night and missing GHI produce no steps', () => {
        expect(averageDaySteps(80, 11, 0.1).steps).toEqual([]);
        expect(averageDaySteps(40, 5, null).steps).toEqual([]);
    });
});

describe('plane of array', () => {
    test('a flat panel receives exactly the horizontal irradiance', () => {
        const day = averageDaySteps(40, 5, 7.2);
        const decl = day.decl;
        for (const step of day.steps) {
            const sun = sunPosition(40, decl, step.hourAngle);
            if (sun.zenith > 85) continue; // the DNI cap applies right at sunrise
            const poa = poaIrradiance(step, sun, {tilt: 0, azimuth: 0}, 0.2, KLEIN_DAYS[5]);
            expect(poa.total).toBeCloseTo(step.global, 6);
        }
    });

    test('a vertical panel sees half the ground', () => {
        const step = {global: 500, beam: 0, diffuse: 500};
        const sun = sunPosition(40, 0, 0);
        const poa = poaIrradiance(step, sun, {tilt: 90, azimuth: 0}, 0.2, 81);
        expect(poa.ground).toBeCloseTo(500 * 0.2 / 2, 6);
    });

    test('ASHRAE incidence angle modifier', () => {
        expect(ashraeIam(1)).toBe(1);
        expect(ashraeIam(0.5)).toBeCloseTo(0.95, 6); // 60°
        expect(ashraeIam(0)).toBe(0);
        expect(ashraeIam(0.01)).toBe(0); // never negative
    });
});

describe('temperature, power, losses, inverter', () => {
    test('SAPM cell temperature, open rack glass/polymer', () => {
        // 1000 * exp(-3.56 - 0.075) + 25 = 51.38, plus deltaT 3.
        expect(cellTemperature(1000, 25, 'open', 1)).toBeCloseTo(54.38, 2);
        expect(cellTemperature(1000, 25, 'flush', 1)).toBeGreaterThan(cellTemperature(1000, 25, 'open', 1));
        expect(cellTemperature(0, 10, 'open')).toBe(10);
    });

    test('air temperature peaks at 3 pm and averages to the mean', () => {
        expect(ambientTemperature(20, 45)).toBeCloseTo(25, 6);
        expect(ambientTemperature(20, -135)).toBeCloseTo(15, 6);
    });

    test('DC power scales with irradiance and loses power when hot', () => {
        expect(dcPower(1000, 25, 1, -0.37)).toBeCloseTo(1, 6);
        expect(dcPower(500, 25, 2, -0.37)).toBeCloseTo(1, 6);
        expect(dcPower(1000, 35, 1, -0.37)).toBeCloseTo(0.963, 6);
        expect(dcPower(0, 25, 1, -0.37)).toBe(0);
    });

    test('PVWatts default losses combine to 14.08%', () => {
        expect(totalLoss(DEFAULT_LOSSES)).toBeCloseTo(14.08, 2);
        expect(totalLoss([])).toBe(0);
        expect(totalLoss([50, 50])).toBeCloseTo(75, 6);
    });

    test('PVWatts inverter is at nominal efficiency at full load and clips', () => {
        // At zeta = 1 the curve evaluates to exactly the nominal efficiency.
        const ac = 1, pdc0 = ac / 0.96;
        expect(inverterOutput(pdc0, ac) / pdc0).toBeCloseTo(0.96, 4);
        expect(inverterOutput(5, ac)).toBe(ac);
        expect(inverterOutput(0, ac)).toBe(0);
        // Part load is less efficient.
        expect(inverterOutput(pdc0 * 0.05, ac) / (pdc0 * 0.05)).toBeLessThan(0.96);
    });
});

describe('estimateProduction', () => {
    test('a 1 kWp south-facing array at 40°N gives a plausible annual yield', () => {
        const result = estimateProduction(system());
        // A clear 40°N site yields roughly 1500-1900 kWh/kWp DC after 14% losses.
        expect(result.annual).toBeGreaterThan(1500);
        expect(result.annual).toBeLessThan(1900);
        // Performance ratio (energy over plane-of-array sun-hours): losses plus temperature.
        const poaAnnual = result.months.reduce((acc, m, i) => acc + m.poa * DAYS_IN_MONTH[i], 0);
        expect(result.annual / poaAnnual).toBeGreaterThan(0.75);
        expect(result.annual / poaAnnual).toBeLessThan(0.88);
        expect(result.specificYield).toBeCloseTo(result.annual, 6);
        expect(result.months).toHaveLength(12);
        expect(result.totalLoss).toBeCloseTo(14.08, 2);
    });

    test('tilting toward the equator gains in winter and loses in summer', () => {
        const flat = estimateProduction(system({tilt: 0}));
        const tilted = estimateProduction(system({tilt: 40}));
        expect(tilted.months[11].poa).toBeGreaterThan(flat.months[11].poa * 1.5);
        expect(tilted.months[5].poa).toBeLessThan(flat.months[5].poa);
        expect(flat.months[5].poa).toBeCloseTo(GHI_40N[5], 1);
    });

    test('tracking beats fixed, and dual-axis beats single-axis', () => {
        const fixed = estimateProduction(system()).annual;
        const single = estimateProduction(system({tracking: 'single'})).annual;
        const dual = estimateProduction(system({tracking: 'dual'})).annual;
        expect(single).toBeGreaterThan(fixed);
        expect(dual).toBeGreaterThan(single);
        // Dual-axis is commonly 30-45% over a well-tilted fixed array.
        expect(dual / fixed).toBeLessThan(1.6);
    });

    test('facing away from the equator produces less', () => {
        const south = estimateProduction(system()).annual;
        const north = estimateProduction(system({azimuth: 0})).annual;
        expect(north).toBeLessThan(south * 0.7);
    });

    test('the southern hemisphere mirrors the northern', () => {
        // Same GHI shifted 6 months, panel facing north.
        const shifted = [...GHI_40N.slice(6), ...GHI_40N.slice(0, 6)];
        const north = estimateProduction(system({temperature: null}));
        const south = estimateProduction(system({latitude: -40, ghi: shifted, azimuth: 0, temperature: null}));
        expect(south.annual / north.annual).toBeGreaterThan(0.97);
        expect(south.annual / north.annual).toBeLessThan(1.03);
    });

    test('hot weather reduces output', () => {
        const cool = estimateProduction(system({temperature: Array(12).fill(0)})).annual;
        const hot = estimateProduction(system({temperature: Array(12).fill(35)})).annual;
        expect(hot).toBeLessThan(cool * 0.95);
    });

    test('the inverter costs a few percent and clips an oversized array', () => {
        const dc = estimateProduction(system()).annual;
        const ac = estimateProduction(system({inverter: {acRating: 1, efficiency: 96}})).annual;
        expect(ac / dc).toBeGreaterThan(0.93);
        expect(ac / dc).toBeLessThan(0.97);
        const clipped = estimateProduction(system({inverter: {acRating: 0.3, efficiency: 96}})).annual;
        expect(clipped).toBeLessThan(ac * 0.7);
    });

    test('polar night months produce nothing without errors', () => {
        const result = estimateProduction(system({latitude: 75, tilt: 75}));
        expect(result.months[11].energy).toBe(0);
        expect(Number.isFinite(result.annual)).toBe(true);
    });

    test('missing months count as zero', () => {
        const ghi = [...GHI_40N];
        ghi[0] = null;
        expect(estimateProduction(system({ghi})).months[0].energy).toBe(0);
    });

    test('the best annual tilt is near the latitude; the best winter tilt is steeper', () => {
        const annual = optimalTilt(system());
        const winter = optimalTilt(system(), 'winter');
        expect(annual).toBeGreaterThanOrEqual(30);
        expect(annual).toBeLessThanOrEqual(44);
        expect(winter).toBeGreaterThan(annual + 8);
    });
});

describe('input parsing', () => {
    test('decimal and DMS coordinates', () => {
        expect(parseCoordinate('40.015')).toBeCloseTo(40.015, 6);
        expect(parseCoordinate('-105.27', 'lon')).toBeCloseTo(-105.27, 6);
        expect(parseCoordinate('40°0\'54"N')).toBeCloseTo(40.015, 6);
        expect(parseCoordinate('105 16 12 W', 'lon')).toBeCloseTo(-105.27, 6);
        expect(parseCoordinate('33.9 S')).toBeCloseTo(-33.9, 6);
        expect(parseCoordinate('-0.5')).toBeCloseTo(-0.5, 6);
    });

    test('invalid coordinates are null', () => {
        expect(parseCoordinate('')).toBeNull();
        expect(parseCoordinate(null)).toBeNull();
        expect(parseCoordinate('91')).toBeNull();
        expect(parseCoordinate('181', 'lon')).toBeNull();
        expect(parseCoordinate('40 E')).toBeNull();
        expect(parseCoordinate('abc')).toBeNull();
        expect(parseCoordinate('40 75 0')).toBeNull();
    });

    test('monthly lists round-trip and tolerate blanks', () => {
        expect(parseMonthly('1,2,,4')).toEqual([1, 2, null, 4, null, null, null, null, null, null, null, null]);
        expect(parseMonthly(null)).toHaveLength(12);
        expect(parseMonthly(formatMonthly(GHI_40N))).toEqual(GHI_40N);
    });
});

describe('solarCalculatorPath', () => {
    test('links to the calculator with the location rounded to 4 decimals', () => {
        expect(solarCalculatorPath(40.0153812, -105.2705456))
            .toBe('/more/calculators?calc=solar&lat=40.0154&lon=-105.2705');
    });

    test('wraps a longitude from a map that has been panned around the world', () => {
        expect(solarCalculatorPath(10, 190)).toBe('/more/calculators?calc=solar&lat=10&lon=-170');
        expect(solarCalculatorPath(10, -540.5)).toBe('/more/calculators?calc=solar&lat=10&lon=179.5');
        expect(solarCalculatorPath(10, 180)).toBe('/more/calculators?calc=solar&lat=10&lon=180');
    });
});
