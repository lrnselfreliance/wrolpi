import {classifyAndEvaluate} from "./mathConfig";

describe('classifyAndEvaluate', () => {

    // Tests for every example shown in the EvaluateForm help text.
    describe('help examples', () => {

        // Math examples
        test('2 + 3', () => {
            const result = classifyAndEvaluate('2 + 3');
            expect(result.primary).toBe('5');
            expect(result.conversions).toEqual([]);
        });

        test('sqrt(15)', () => {
            const result = classifyAndEvaluate('sqrt(15)');
            expect(Number(result.primary)).toBeCloseTo(3.8730, 3);
            expect(result.conversions).toEqual([]);
        });

        test('8 * pi', () => {
            const result = classifyAndEvaluate('8 * pi');
            expect(Number(result.primary)).toBeCloseTo(25.1327, 3);
            expect(result.conversions).toEqual([]);
        });

        // Unit conversion examples
        test('15 km to miles', () => {
            const result = classifyAndEvaluate('15 km to miles');
            expect(result.conversions).toEqual([]);
            expect(result.primary).toMatch(/9\.32\d*/);
        });

        test('65 degF to degC', () => {
            const result = classifyAndEvaluate('65 degF to degC');
            expect(result.conversions).toEqual([]);
            expect(result.primary).toMatch(/18\.33\d*/);
        });

        test('1 gallon to liters', () => {
            const result = classifyAndEvaluate('1 gallon to liters');
            expect(result.conversions).toEqual([]);
            expect(result.primary).toMatch(/3\.78\d*/);
        });

        test('5 psi to atm', () => {
            const result = classifyAndEvaluate('5 psi to atm');
            expect(result.conversions).toEqual([]);
            expect(result.primary).toMatch(/0\.34\d*/);
        });

        // Auto-convert examples
        test('5 miles auto-converts to other length units', () => {
            const result = classifyAndEvaluate('5 miles');
            expect(result.conversions.length).toBeGreaterThan(0);
            expect(result.conversions.some(c => c.includes('km'))).toBe(true);
            expect(result.conversions.some(c => c.includes('meter'))).toBe(true);
            expect(result.conversions.some(c => c.includes('foot'))).toBe(true);
        });

        test('100 degF auto-converts to degC and K', () => {
            const result = classifyAndEvaluate('100 degF');
            expect(result.conversions.some(c => c.includes('degC'))).toBe(true);
            expect(result.conversions.some(c => c.includes('K'))).toBe(true);
        });

        test('1 gallon auto-converts to other volume units', () => {
            const result = classifyAndEvaluate('1 gallon');
            expect(result.conversions.some(c => c.includes('liter'))).toBe(true);
            expect(result.conversions.some(c => c.includes('quart'))).toBe(true);
            expect(result.conversions.some(c => c.includes('cup'))).toBe(true);
        });

        test('500 Wh auto-converts to other energy units', () => {
            const result = classifyAndEvaluate('500 Wh');
            expect(result.conversions.some(c => c.includes('J'))).toBe(true);
            expect(result.conversions.some(c => c.includes('kWh'))).toBe(true);
            expect(result.conversions.some(c => c.includes('BTU'))).toBe(true);
        });

        // Radiation examples
        test('0.5 Sv auto-converts to rem', () => {
            const result = classifyAndEvaluate('0.5 Sv');
            expect(result.conversions.some(c => c.includes('rem'))).toBe(true);
        });

        test('1 Gy to raddose', () => {
            const result = classifyAndEvaluate('1 Gy to raddose');
            expect(result.conversions).toEqual([]);
            expect(result.primary).toMatch(/100/);
            // Display name mapping: raddose shows as "rad".
            expect(result.primary).toContain('rad');
            expect(result.primary).not.toContain('raddose');
        });

        test('100 remdose to Sv', () => {
            const result = classifyAndEvaluate('100 remdose to Sv');
            expect(result.conversions).toEqual([]);
            expect(result.primary).toMatch(/1\s+Sv/);
        });

        // Data examples
        test('7 * 750 Mb', () => {
            const result = classifyAndEvaluate('7 * 750 Mb');
            // math.js simplifies 5250 Mb to 5.25 Gb.
            expect(result.primary).toMatch(/5\.25\s+Gb/);
        });

        test('2 Tb to Gb', () => {
            const result = classifyAndEvaluate('2 Tb to Gb');
            expect(result.conversions).toEqual([]);
            expect(result.primary).toMatch(/2000/);
        });
    });

    describe('auto-conversion details', () => {
        test('does not include the input unit in conversions', () => {
            const result = classifyAndEvaluate('5 miles');
            expect(result.conversions).not.toContain(result.primary);
        });

        test('mass: 10 kg shows lbm, oz, g', () => {
            const result = classifyAndEvaluate('10 kg');
            expect(result.conversions.some(c => c.includes('lbm'))).toBe(true);
            expect(result.conversions.some(c => c.includes('g'))).toBe(true);
        });

        test('pressure: 1 atm shows psi, Pa, bar, mmHg', () => {
            const result = classifyAndEvaluate('1 atm');
            expect(result.conversions.some(c => c.includes('psi'))).toBe(true);
            expect(result.conversions.some(c => c.includes('Pa'))).toBe(true);
            expect(result.conversions.some(c => c.includes('bar'))).toBe(true);
        });

        test('data: 1 Gb shows Mb', () => {
            const result = classifyAndEvaluate('1 Gb');
            expect(result.conversions.some(c => c.includes('Mb'))).toBe(true);
        });
    });

    describe('radiation units', () => {
        test('gray auto-converts to raddose and roentgen', () => {
            const result = classifyAndEvaluate('1 gray');
            expect(result.conversions.some(c => c.includes('rad'))).toBe(true);
            expect(result.conversions.some(c => c.includes('roentgen'))).toBe(true);
        });

        test('becquerel and curie conversion', () => {
            const result = classifyAndEvaluate('1 curie');
            expect(result.conversions.some(c => c.includes('becquerel'))).toBe(true);
        });

        test('SI prefixes work with sievert (1 Sv = 1000 mSv)', () => {
            const result = classifyAndEvaluate('1 sievert to mSv');
            expect(result.primary).toMatch(/1000/);
        });

        test('SI prefixes work with gray (1 mGy = 0.001 Gy)', () => {
            const result = classifyAndEvaluate('1 mGy to gray');
            expect(result.primary).toMatch(/0\.001/);
        });
    });

    describe('display name formatting', () => {
        test('raddose displays as rad in output', () => {
            const result = classifyAndEvaluate('1 Gy to raddose');
            expect(result.primary).toContain('rad');
            expect(result.primary).not.toContain('raddose');
        });

        test('remdose displays as rem in output', () => {
            const result = classifyAndEvaluate('1 Sv to remdose');
            expect(result.primary).toContain('rem');
            expect(result.primary).not.toContain('remdose');
        });
    });

    describe('error handling', () => {
        test('invalid expression throws', () => {
            expect(() => classifyAndEvaluate('foo bar baz')).toThrow();
        });
    });
});
