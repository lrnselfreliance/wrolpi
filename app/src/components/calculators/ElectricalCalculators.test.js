import {
    ALUMINUM_TEMP_COEFFICIENT,
    calcKelvinMilliVoltDrop,
    calcPowerLossPercent,
    resistancesPerKFeet,
    resistancesPerKm,
} from "./ElectricalCalculators";

describe('calcPowerLossPercent Function Tests', () => {
    test('should correctly calculate power loss percentage', () => {
        // Parameters: isSAE, volts, amps, resistancePerKm, length
        const percent = calcPowerLossPercent(true, 120, 8.33, 2.58, 200);
        expect(percent).toBeCloseTo(7.16, 2); // Use expected correct value and precision
    });
});

describe('calcKelvinMilliVoltDrop Function Tests', () => {
    test('should correctly calculate millivolt drop', () => {
        // Parameters: amps, resistancePerKiloLength, length
        // 100 feet of 10 AWG solid copper (0.9987 Ω/kft) at 1A: 0.09987 Ω * 1A = 99.87 mV
        expect(calcKelvinMilliVoltDrop(1, 0.9987, 100)).toBeCloseTo(99.87, 2);
        // Same wire at 10A: 998.7 mV
        expect(calcKelvinMilliVoltDrop(10, 0.9987, 100)).toBeCloseTo(998.7, 1);
        // Length is not doubled: 50 feet at 5A is a quarter of 100 feet at 10A.
        expect(calcKelvinMilliVoltDrop(5, 0.9987, 50)).toBeCloseTo(calcKelvinMilliVoltDrop(10, 0.9987, 100) / 4, 5);
    });

    test('should return zero for zero length or amps', () => {
        expect(calcKelvinMilliVoltDrop(0, 0.9987, 100)).toBe(0);
        expect(calcKelvinMilliVoltDrop(1, 0.9987, 0)).toBe(0);
    });

    test('should correct resistance for temperature', () => {
        // At the 20°C reference temperature, no correction is applied.
        expect(calcKelvinMilliVoltDrop(1, 0.9987, 100, 20)).toBeCloseTo(99.87, 2);
        // Warmer wire has more resistance: 30°C is a 3.93% increase.
        expect(calcKelvinMilliVoltDrop(1, 0.9987, 100, 30)).toBeCloseTo(99.87 * 1.0393, 2);
        // Colder wire has less resistance: 0°C is a 7.86% decrease.
        expect(calcKelvinMilliVoltDrop(1, 0.9987, 100, 0)).toBeCloseTo(99.87 * 0.9214, 2);
    });

    test('should use the given temperature coefficient', () => {
        // 100 feet of 10 AWG solid aluminum (1.64 Ω/kft) at 1A and 30°C: 164 mV plus aluminum's 4.03% increase.
        expect(calcKelvinMilliVoltDrop(1, 1.64, 100, 30, ALUMINUM_TEMP_COEFFICIENT))
            .toBeCloseTo(164 * 1.0403, 2);
    });
});

describe('Resistance Table Sanity Tests', () => {
    // The tables list wire sizes from largest to smallest, so resistance must strictly increase.
    test.each([
        ...Object.entries(resistancesPerKFeet),
        ...Object.entries(resistancesPerKm),
    ])('%s resistances increase as the wire gets smaller', (wireType, resistances) => {
        const values = Object.values(resistances);
        for (let i = 1; i < values.length; i++) {
            expect(values[i]).toBeGreaterThan(values[i - 1]);
        }
    });

    test('solid copper matches published values', () => {
        // Published solid copper resistance at 20°C is 0.3951 Ω/kft for 6 AWG.
        expect(resistancesPerKFeet.solid['6 AWG']).toBeCloseTo(0.3951, 2);
    });

    test('stranded copper is a consistent ratio of solid copper', () => {
        // The stranded copper table was built as solid × 1.24; every entry must match that ratio.
        for (const [size, resistance] of Object.entries(resistancesPerKFeet.stranded)) {
            const solid = resistancesPerKFeet.solid[size];
            if (solid === undefined) {
                continue; // Stranded has 18 AWG which solid does not.
            }
            expect(resistance / solid).toBeCloseTo(1.24, 1);
        }
    });
});
