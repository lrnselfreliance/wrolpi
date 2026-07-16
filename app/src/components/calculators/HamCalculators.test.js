import {
    ANTENNA_FRACTIONS,
    antennaFractionLengths,
    convertFeetToFeetAndInches,
    freeSpaceWavelengthMeters,
    frequencyMhzFromWavelengthMeters,
    FULL_WAVE_FEET_PER_MHZ,
    fullWaveFeet,
    fullWaveLengthUnits,
    lengthUnitsFromFeet,
    scaleLengthUnits,
    SPEED_OF_LIGHT,
} from "./HamCalculators";

// ---------------------------------------------------------------------------
// Constants and formula relationships
// ---------------------------------------------------------------------------

describe('antenna constants', () => {
    test('speed of light matches the SI definition', () => {
        expect(SPEED_OF_LIGHT).toBe(299792458);
    });

    test('full-wave constant is the standard ARRL 936 ft·MHz value', () => {
        expect(FULL_WAVE_FEET_PER_MHZ).toBe(936);
    });

    test('936 implies the classic half/quarter/5-8 constants', () => {
        // Half-wave dipole: 468 / f
        expect(FULL_WAVE_FEET_PER_MHZ * 0.5).toBe(468);
        // Quarter-wave: 234 / f
        expect(FULL_WAVE_FEET_PER_MHZ * 0.25).toBe(234);
        // 5/8-wave: 585 / f
        expect(FULL_WAVE_FEET_PER_MHZ * 0.625).toBe(585);
    });

    test('end-effect velocity factor is about 0.95 vs free-space 984', () => {
        // Free-space full-wave feet ≈ 984 / f (c ≈ 983.57 ft/µs).
        // Wire antennas use 936 / f → VF ≈ 0.951.
        expect(FULL_WAVE_FEET_PER_MHZ / 984).toBeCloseTo(0.95, 2);
    });

    test('ANTENNA_FRACTIONS cover half, quarter, and 5/8 wave', () => {
        const multipliers = ANTENNA_FRACTIONS.map(f => f.multiplier).sort();
        expect(multipliers).toEqual([0.25, 0.5, 0.625]);
    });
});

// ---------------------------------------------------------------------------
// convertFeetToFeetAndInches
// ---------------------------------------------------------------------------

describe('convertFeetToFeetAndInches', () => {
    test('splits whole feet with zero inches', () => {
        expect(convertFeetToFeetAndInches(10)).toEqual([10, 0]);
        expect(convertFeetToFeetAndInches(0)).toEqual([0, 0]);
    });

    test('converts fractional feet to nearest inch', () => {
        // 3.245 ft * 12 = 38.94 in → 3 ft 3 in
        expect(convertFeetToFeetAndInches(3.245)).toEqual([3, 3]);
        // 1.6227 ft * 12 = 19.47 in → 1 ft 7 in
        expect(convertFeetToFeetAndInches(1.6227)).toEqual([1, 7]);
        // 32.958 ft * 12 = 395.5 in → 32 ft 11 in (rounds half up via Math.round)
        expect(convertFeetToFeetAndInches(32.958)).toEqual([32, 11]);
    });

    test('never reports 12 inches — rolls over to the next foot', () => {
        // Values whose fractional part * 12 rounds to 12 (was a bug: "3 ft 12 in").
        expect(convertFeetToFeetAndInches(3.9584)).toEqual([4, 0]);
        expect(convertFeetToFeetAndInches(3.999)).toEqual([4, 0]);
        expect(convertFeetToFeetAndInches(399.99999999999994)).toEqual([400, 0]);
        // Exactly 11.5/12 feet fractional part rounds to 12 inches → +1 foot.
        expect(convertFeetToFeetAndInches(5 + 11.5 / 12)).toEqual([6, 0]);
    });

    test('handles just-under and just-over an inch boundary', () => {
        // 1/12 ft = 1 in exactly
        expect(convertFeetToFeetAndInches(1 / 12)).toEqual([0, 1]);
        // Slightly under half an inch rounds down
        expect(convertFeetToFeetAndInches(0.04)).toEqual([0, 0]); // 0.48 in
        // Slightly over half an inch rounds up
        expect(convertFeetToFeetAndInches(0.05)).toEqual([0, 1]); // 0.60 in
    });

    test('returns [0, 0] for non-positive or non-finite input', () => {
        expect(convertFeetToFeetAndInches(-1)).toEqual([0, 0]);
        expect(convertFeetToFeetAndInches(NaN)).toEqual([0, 0]);
        expect(convertFeetToFeetAndInches(Infinity)).toEqual([0, 0]);
        expect(convertFeetToFeetAndInches(-Infinity)).toEqual([0, 0]);
    });
});

// ---------------------------------------------------------------------------
// fullWaveFeet / free-space wavelength / frequency conversion
// ---------------------------------------------------------------------------

describe('fullWaveFeet', () => {
    test('returns 936 / f for valid frequencies', () => {
        expect(fullWaveFeet(1)).toBe(936);
        expect(fullWaveFeet(144.2)).toBeCloseTo(936 / 144.2, 10);
        expect(fullWaveFeet(14.2)).toBeCloseTo(936 / 14.2, 10);
    });

    test('returns null for invalid frequencies', () => {
        expect(fullWaveFeet(0)).toBeNull();
        expect(fullWaveFeet(-7)).toBeNull();
        expect(fullWaveFeet(NaN)).toBeNull();
        expect(fullWaveFeet(Infinity)).toBeNull();
    });
});

describe('freeSpaceWavelengthMeters', () => {
    test('uses λ = c / f', () => {
        // 300 MHz → exactly 0.999308 m with the exact speed of light
        expect(freeSpaceWavelengthMeters(300)).toBeCloseTo(SPEED_OF_LIGHT / 3e8, 10);
        // 144.2 MHz 2 m band — free-space wavelength is a bit over 2 m
        expect(freeSpaceWavelengthMeters(144.2)).toBeCloseTo(2.0790, 3);
        // 14.2 MHz 20 m band
        expect(freeSpaceWavelengthMeters(14.2)).toBeCloseTo(21.1121, 3);
    });

    test('matches the common 300/f approximation within 0.1%', () => {
        // Amateur radio often approximates c as 300 m/µs.
        for (const mhz of [7.15, 14.2, 146, 440]) {
            const exact = freeSpaceWavelengthMeters(mhz);
            const approx = 300 / mhz;
            expect(Math.abs(exact - approx) / exact).toBeLessThan(0.001);
        }
    });

    test('returns null for invalid frequencies', () => {
        expect(freeSpaceWavelengthMeters(0)).toBeNull();
        expect(freeSpaceWavelengthMeters(-1)).toBeNull();
        expect(freeSpaceWavelengthMeters(NaN)).toBeNull();
    });
});

describe('frequencyMhzFromWavelengthMeters', () => {
    test('is the inverse of freeSpaceWavelengthMeters', () => {
        for (const mhz of [1.9, 7.15, 14.2, 28.5, 50.1, 144.2, 146, 440, 446]) {
            const lambda = freeSpaceWavelengthMeters(mhz);
            expect(frequencyMhzFromWavelengthMeters(lambda)).toBeCloseTo(mhz, 8);
        }
    });

    test('round-trips a known free-space wavelength', () => {
        // 2 m free-space → 149.896 MHz
        expect(frequencyMhzFromWavelengthMeters(2)).toBeCloseTo(SPEED_OF_LIGHT / 2e6, 8);
    });

    test('returns null for invalid wavelengths', () => {
        expect(frequencyMhzFromWavelengthMeters(0)).toBeNull();
        expect(frequencyMhzFromWavelengthMeters(-2)).toBeNull();
        expect(frequencyMhzFromWavelengthMeters(NaN)).toBeNull();
    });
});

// ---------------------------------------------------------------------------
// Unit conversion helpers
// ---------------------------------------------------------------------------

describe('lengthUnitsFromFeet / scaleLengthUnits', () => {
    test('converts feet to inches, meters, and cm with standard factors', () => {
        const units = lengthUnitsFromFeet(10);
        expect(units.feet).toBe(10);
        expect(units.inches).toBe(120);
        expect(units.meters).toBeCloseTo(3.048, 10);
        expect(units.cm).toBeCloseTo(304.8, 10);
    });

    test('scaleLengthUnits multiplies every unit by the same factor', () => {
        const full = lengthUnitsFromFeet(100);
        const half = scaleLengthUnits(full, 0.5);
        expect(half.feet).toBe(50);
        expect(half.inches).toBe(600);
        expect(half.meters).toBeCloseTo(15.24, 10);
        expect(half.cm).toBeCloseTo(1524, 10);
    });

    test('scaling is linear across the standard antenna fractions', () => {
        const full = lengthUnitsFromFeet(936); // 1 MHz full-wave
        for (const {multiplier} of ANTENNA_FRACTIONS) {
            const scaled = scaleLengthUnits(full, multiplier);
            expect(scaled.feet).toBeCloseTo(936 * multiplier, 10);
            expect(scaled.inches).toBeCloseTo(full.inches * multiplier, 10);
            expect(scaled.meters).toBeCloseTo(full.meters * multiplier, 10);
            expect(scaled.cm).toBeCloseTo(full.cm * multiplier, 10);
        }
    });
});

describe('fullWaveLengthUnits', () => {
    test('returns consistent unit set for a valid frequency', () => {
        const units = fullWaveLengthUnits(144.2);
        expect(units.feet).toBeCloseTo(936 / 144.2, 10);
        expect(units.inches).toBeCloseTo(units.feet * 12, 10);
        expect(units.meters).toBeCloseTo(units.feet * 0.3048, 10);
        expect(units.cm).toBeCloseTo(units.meters * 100, 10);
    });

    test('returns null for invalid frequency', () => {
        expect(fullWaveLengthUnits(0)).toBeNull();
        expect(fullWaveLengthUnits(-14.2)).toBeNull();
    });
});

// ---------------------------------------------------------------------------
// Half / quarter / 5/8 wave lengths (the UI tables)
// ---------------------------------------------------------------------------

describe('antennaFractionLengths — half-wave dipole (468/f)', () => {
    // Published / well-known half-wave dipole lengths.
    test.each([
        // [MHz, expected total feet, expected leg feet]
        [1.9, 468 / 1.9, 234 / 1.9],       // 160 m
        [3.8, 468 / 3.8, 234 / 3.8],       // 80 m
        [7.15, 468 / 7.15, 234 / 7.15],    // 40 m
        [14.2, 468 / 14.2, 234 / 14.2],    // 20 m
        [21.2, 468 / 21.2, 234 / 21.2],    // 15 m
        [28.5, 468 / 28.5, 234 / 28.5],    // 10 m
        [50.1, 468 / 50.1, 234 / 50.1],    // 6 m
        [144.2, 468 / 144.2, 234 / 144.2], // 2 m (default in UI)
        [146, 468 / 146, 234 / 146],       // 2 m simplex
        [440, 468 / 440, 234 / 440],       // 70 cm
    ])('half-wave at %s MHz is 468/f total and 234/f per leg', (mhz, totalFeet, legFeet) => {
        const result = antennaFractionLengths(mhz, 0.5);
        expect(result.total.feet).toBeCloseTo(totalFeet, 8);
        expect(result.leg.feet).toBeCloseTo(legFeet, 8);
        // Leg is exactly half the total.
        expect(result.leg.feet).toBeCloseTo(result.total.feet / 2, 10);
    });

    test('default 144.2 MHz half-wave displays as 3 ft 3 in total, 1 ft 7 in per leg', () => {
        const result = antennaFractionLengths(144.2, 0.5);
        expect(result.total.feetInches).toEqual([3, 3]);
        expect(result.leg.feetInches).toEqual([1, 7]);
    });

    test('14.2 MHz half-wave is about 32 ft 11 in total', () => {
        const result = antennaFractionLengths(14.2, 0.5);
        expect(result.total.feetInches).toEqual([32, 11]);
    });
});

describe('antennaFractionLengths — quarter-wave (234/f)', () => {
    test.each([
        [146, 234 / 146],
        [144.2, 234 / 144.2],
        [14.2, 234 / 14.2],
        [7.15, 234 / 7.15],
    ])('quarter-wave at %s MHz is 234/f', (mhz, expectedFeet) => {
        const result = antennaFractionLengths(mhz, 0.25);
        expect(result.total.feet).toBeCloseTo(expectedFeet, 8);
        // "Leg" is still half of the shown total (center-fed construction).
        expect(result.leg.feet).toBeCloseTo(expectedFeet / 2, 8);
    });
});

describe('antennaFractionLengths — 5/8-wave (585/f)', () => {
    test.each([
        [146, 585 / 146],
        [144.2, 585 / 144.2],
        [50.1, 585 / 50.1],
        [440, 585 / 440],
    ])('5/8-wave at %s MHz is 585/f', (mhz, expectedFeet) => {
        const result = antennaFractionLengths(mhz, 0.625);
        expect(result.total.feet).toBeCloseTo(expectedFeet, 8);
        expect(result.leg.feet).toBeCloseTo(expectedFeet / 2, 8);
    });
});

describe('antennaFractionLengths — metric consistency', () => {
    test('inches, meters, and cm are consistent with feet for every fraction', () => {
        for (const {multiplier} of ANTENNA_FRACTIONS) {
            const result = antennaFractionLengths(14.2, multiplier);
            for (const part of [result.total, result.leg]) {
                expect(part.inches).toBeCloseTo(part.feet * 12, 8);
                expect(part.meters).toBeCloseTo(part.feet * 0.3048, 8);
                expect(part.cm).toBeCloseTo(part.meters * 100, 8);
                // feetInches display matches the decimal feet value.
                const [ft, inch] = part.feetInches;
                expect(ft * 12 + inch).toBeCloseTo(Math.round(part.feet * 12), 0);
            }
        }
    });

    test('returns null for invalid frequency or multiplier', () => {
        expect(antennaFractionLengths(0, 0.5)).toBeNull();
        expect(antennaFractionLengths(-14, 0.5)).toBeNull();
        expect(antennaFractionLengths(NaN, 0.5)).toBeNull();
        expect(antennaFractionLengths(144.2, NaN)).toBeNull();
    });
});

// ---------------------------------------------------------------------------
// Cross-checks against free-space physics
// ---------------------------------------------------------------------------

describe('end-effect relationship to free space', () => {
    test('wire half-wave is ~95% of free-space half-wavelength in feet', () => {
        for (const mhz of [7.15, 14.2, 28.5, 144.2, 440]) {
            const freeSpaceMeters = freeSpaceWavelengthMeters(mhz);
            const freeSpaceHalfFeet = (freeSpaceMeters / 2) / 0.3048;
            const wireHalfFeet = antennaFractionLengths(mhz, 0.5).total.feet;
            // 468/f vs 492/f ≈ 0.951 (same VF as 936/984)
            expect(wireHalfFeet / freeSpaceHalfFeet).toBeCloseTo(0.95, 2);
        }
    });

    test('wire lengths are always shorter than free-space equivalents', () => {
        for (const mhz of [3.8, 14.2, 146]) {
            const freeSpaceFeet = freeSpaceWavelengthMeters(mhz) / 0.3048;
            const wireFullFeet = fullWaveFeet(mhz);
            expect(wireFullFeet).toBeLessThan(freeSpaceFeet);
            expect(wireFullFeet).toBeCloseTo(freeSpaceFeet * (936 / (SPEED_OF_LIGHT * 3.280839895 / 1e6)), 2);
        }
    });
});

// ---------------------------------------------------------------------------
// Sanity across the HF / VHF / UHF amateur bands
// ---------------------------------------------------------------------------

describe('band sanity checks', () => {
    test('higher frequency always yields shorter antennas', () => {
        const bands = [1.9, 3.8, 7.15, 14.2, 21.2, 28.5, 50.1, 144.2, 440];
        for (let i = 1; i < bands.length; i++) {
            const lower = fullWaveFeet(bands[i - 1]);
            const higher = fullWaveFeet(bands[i]);
            expect(higher).toBeLessThan(lower);
        }
    });

    test('half-wave is exactly twice quarter-wave at every frequency', () => {
        for (const mhz of [7.15, 14.2, 146, 440]) {
            const half = antennaFractionLengths(mhz, 0.5).total.feet;
            const quarter = antennaFractionLengths(mhz, 0.25).total.feet;
            expect(half).toBeCloseTo(quarter * 2, 10);
        }
    });

    test('5/8-wave is 1.25× half-wave at every frequency', () => {
        for (const mhz of [50.1, 146, 440]) {
            const half = antennaFractionLengths(mhz, 0.5).total.feet;
            const fiveEighths = antennaFractionLengths(mhz, 0.625).total.feet;
            expect(fiveEighths).toBeCloseTo(half * 1.25, 10);
        }
    });
});
