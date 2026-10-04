import {
    BATTERIES,
    batteryWarnings,
    chargeVoltage,
    coldVoc,
    controllerSizing,
    dailyLoadWh,
    defaultColdest,
    formatLoads,
    leadAcidCapacityFactor,
    loadWh,
    parseLoads,
    pwmUsableFraction,
    requiredKwp,
    sizeBattery,
} from "./offgrid";

describe('loads', () => {
    test('round-trip through the URL format', () => {
        const rows = [{name: 'Fridge', watts: '60', hours: '24'}, {name: 'Lights', watts: '20', hours: '5'}];
        expect(formatLoads(rows)).toBe('Fridge~60~24|Lights~20~5');
        expect(parseLoads(formatLoads(rows))).toEqual(rows);
        expect(parseLoads('')).toEqual([]);
        expect(parseLoads(null)).toEqual([]);
    });

    test('separators are removed from names', () => {
        expect(parseLoads(formatLoads([{name: 'A|B~C', watts: '1', hours: '1'}]))[0].name).toBe('A B C');
    });

    test('daily energy is watts times hours, ignoring blanks and capping at 24 hours', () => {
        expect(loadWh({watts: '60', hours: '24'})).toBe(1440);
        expect(loadWh({watts: '60', hours: '30'})).toBe(1440);
        expect(loadWh({watts: '', hours: '5'})).toBe(0);
        expect(loadWh({watts: '-5', hours: '5'})).toBe(0);
        expect(dailyLoadWh(parseLoads('Fridge~60~24|Lights~20~5|~~'))).toBe(1540);
    });
});

describe('battery', () => {
    test('a bank for 2 days of 1 kWh at 50% depth of discharge holds 4 kWh', () => {
        const bank = sizeBattery({loadWh: 1000, days: 2, dod: 50, voltage: 12});
        expect(bank.usableWh).toBe(2000);
        expect(bank.nominalWh).toBe(4000);
        expect(bank.ah).toBeCloseTo(333.3, 1);
    });

    test('a cold lead-acid bank must be bigger', () => {
        expect(leadAcidCapacityFactor(25)).toBe(1);
        expect(leadAcidCapacityFactor(0)).toBeCloseTo(0.8, 6);
        expect(leadAcidCapacityFactor(-20)).toBeCloseTo(0.6, 6);
        expect(leadAcidCapacityFactor(-60)).toBe(0.5);
        const warm = sizeBattery({loadWh: 1000, days: 1, dod: 50, voltage: 12});
        const cold = sizeBattery({loadWh: 1000, days: 1, dod: 50, voltage: 12, capacityFactor: 0.8});
        expect(cold.nominalWh).toBeCloseTo(warm.nominalWh / 0.8, 6);
    });

    test('lithium needs a smaller bank than lead-acid for the same load', () => {
        const lfp = sizeBattery({loadWh: 1000, days: 2, dod: BATTERIES.lfp.dod, voltage: 24});
        const lead = sizeBattery({loadWh: 1000, days: 2, dod: BATTERIES.lead.dod, voltage: 24});
        expect(lfp.nominalWh).toBeLessThan(lead.nominalWh);
    });

    test('no bank without a load', () => {
        expect(sizeBattery({loadWh: 0, days: 2, dod: 50, voltage: 12})).toBeNull();
    });
});

describe('array', () => {
    test('panels needed for the worst month', () => {
        // 2 kWh/day, 3 kWh/kWp/day in the worst month, 95% battery efficiency: 2 / 2.85 = 0.702 kW.
        expect(requiredKwp(2000, 3, 95)).toBeCloseTo(0.7018, 4);
        expect(requiredKwp(2000, 0, 95)).toBeNull();
    });
});

describe('charge controller', () => {
    test('a PWM controller wastes most of a high-voltage panel on a 12 V battery', () => {
        expect(chargeVoltage(12)).toBeCloseTo(14.4, 6);
        // 14.4 V / 31 V: under half the panel's power.
        expect(pwmUsableFraction(31, 12)).toBeCloseTo(0.4645, 3);
        // A "12 V" panel (Vmp ~18 V) suits PWM much better.
        expect(pwmUsableFraction(18, 12)).toBeCloseTo(0.8, 6);
        expect(pwmUsableFraction(10, 12)).toBe(1);
    });

    test('open-circuit voltage rises in the cold', () => {
        // -0.27 %/°C at -25 °C (50 °C below the 25 °C rating): +13.5%.
        expect(coldVoc(37, -0.27, -25)).toBeCloseTo(41.995, 3);
        expect(coldVoc(37, -0.27, 25)).toBe(37);
    });

    const typical = {
        panelCount: 4, panelWatts: 400, series: 2, voc: 37, vmp: 31, isc: 13.8, betaVoc: -0.27, coldest: -25,
        controller: 'mppt', controllerMaxVoltage: 100, systemVoltage: 24,
    };

    test('two 400 W panels in series on a 100 V MPPT controller are safe', () => {
        const result = controllerSizing(typical);
        expect(result.strings).toBe(2);
        expect(result.stringColdVoc).toBeCloseTo(83.99, 2);
        expect(result.overVoltage).toBe(false);
        expect(result.maxSeries).toBe(2);
        // 1600 W / 24 V x 1.25.
        expect(result.current).toBeCloseTo(83.33, 2);
        expect(result.lowVoltage).toBe(false);
        expect(result.unevenStrings).toBe(false);
    });

    test('three in series exceed 100 V on a cold morning', () => {
        const result = controllerSizing({...typical, series: 3});
        expect(result.overVoltage).toBe(true);
        expect(result.unevenStrings).toBe(true);
    });

    test('one panel per string is too little voltage to charge 48 V through MPPT', () => {
        expect(controllerSizing({...typical, series: 1, systemVoltage: 48}).lowVoltage).toBe(true);
    });

    test('PWM current is the panels\' short-circuit current plus 25%', () => {
        const result = controllerSizing({...typical, controller: 'pwm', series: 1, systemVoltage: 12});
        expect(result.current).toBeCloseTo(13.8 * 4 * 1.25, 6);
        expect(result.pwmFraction).toBeCloseTo(0.4645, 3);
        expect(result.lowVoltage).toBe(false);
    });
});

describe('defaultColdest', () => {
    test('is well below the coldest monthly average', () => {
        expect(defaultColdest([-1, 0, 5, 10, 15, 20, 24, 22, 18, 10, 4, -1])).toBe(-26);
        expect(defaultColdest([null, null])).toBe(-20);
        expect(defaultColdest(null)).toBe(-20);
    });
});

describe('batteryWarnings', () => {
    test('warn about charging lithium in the cold, only when the batteries are outdoors', () => {
        expect(batteryWarnings({battery: 'lfp', outdoors: true, coldestMonthly: -5})[0]).toMatch(/below 0 °C/);
        expect(batteryWarnings({battery: 'lfp', outdoors: false, coldestMonthly: -5})).toEqual([]);
        expect(batteryWarnings({battery: 'lfp', outdoors: true, coldestMonthly: 15})).toEqual([]);
    });

    test('explain the cold lead-acid enlargement', () => {
        expect(batteryWarnings({battery: 'lead', outdoors: true, coldestMonthly: 0})[0]).toMatch(/80% of its rating/);
    });
});
