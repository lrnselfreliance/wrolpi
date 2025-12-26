import {ratioReducer} from './RatioCalculator';
import {unit} from 'mathjs';

// The nullUnit is already created by RatioCalculator.js import, so we can reference it by name
const nullUnit = 'null';

describe('ratioReducer', () => {
    const createInitialState = () => ({
        base: null,
        lastUpdated: [],
        a: unit('', nullUnit),
        b: unit('', nullUnit),
        c: unit('', nullUnit),
        d: unit('', nullUnit),
        aUnit: nullUnit,
        bUnit: nullUnit,
        cUnit: nullUnit,
        dUnit: nullUnit,
        recentUnits: {},
    });

    describe('ratio calculations (A:B = C:D)', () => {
        test('calculates A = B*C/D when B, C, D are set', () => {
            let state = createInitialState();
            // Set B=2, C=6, D=3 → A should be 4 (2*6/3 = 4)
            state = ratioReducer(state, {name: 'b', value: '2'});
            state = ratioReducer(state, {name: 'c', value: '6'});
            state = ratioReducer(state, {name: 'd', value: '3'});

            expect(state.a.toNumber()).toBeCloseTo(4, 5);
        });

        test('calculates B = A*D/C when A, C, D are set', () => {
            let state = createInitialState();
            // Set A=4, C=6, D=3 → B should be 2 (4*3/6 = 2)
            state = ratioReducer(state, {name: 'a', value: '4'});
            state = ratioReducer(state, {name: 'c', value: '6'});
            state = ratioReducer(state, {name: 'd', value: '3'});

            expect(state.b.toNumber()).toBeCloseTo(2, 5);
        });

        test('calculates C = A*D/B when A, B, D are set', () => {
            let state = createInitialState();
            // Set A=4, B=2, D=3 → C should be 6 (4*3/2 = 6)
            state = ratioReducer(state, {name: 'a', value: '4'});
            state = ratioReducer(state, {name: 'b', value: '2'});
            state = ratioReducer(state, {name: 'd', value: '3'});

            expect(state.c.toNumber()).toBeCloseTo(6, 5);
        });

        test('calculates D = B*C/A when A, B, C are set', () => {
            let state = createInitialState();
            // Set A=4, B=2, C=6 → D should be 3 (2*6/4 = 3)
            state = ratioReducer(state, {name: 'a', value: '4'});
            state = ratioReducer(state, {name: 'b', value: '2'});
            state = ratioReducer(state, {name: 'c', value: '6'});

            expect(state.d.toNumber()).toBeCloseTo(3, 5);
        });

        test('does not calculate when only 2 values are set', () => {
            let state = createInitialState();
            state = ratioReducer(state, {name: 'a', value: '4'});
            state = ratioReducer(state, {name: 'b', value: '2'});

            // C and D should remain at 0 (empty)
            expect(state.c.toNumber()).toBe(0);
            expect(state.d.toNumber()).toBe(0);
        });

        test('recalculates when a value changes', () => {
            let state = createInitialState();
            // Initial: A=4, B=2, C=6 → D=3
            state = ratioReducer(state, {name: 'a', value: '4'});
            state = ratioReducer(state, {name: 'b', value: '2'});
            state = ratioReducer(state, {name: 'c', value: '6'});
            expect(state.d.toNumber()).toBeCloseTo(3, 5);

            // Change A to 8 → D should recalculate to 1.5 (2*6/8 = 1.5)
            state = ratioReducer(state, {name: 'a', value: '8'});
            expect(state.d.toNumber()).toBeCloseTo(1.5, 5);
        });
    });

    describe('unit conversions', () => {
        const createLengthState = () => ({
            base: 'length',
            lastUpdated: [],
            a: unit('', 'meter'),
            b: unit('', 'meter'),
            c: unit('', 'meter'),
            d: unit('', 'meter'),
            aUnit: 'meter',
            bUnit: 'meter',
            cUnit: 'meter',
            dUnit: 'meter',
            recentUnits: {length: 'meter'},
        });

        test('converts value when unit changes', () => {
            let state = createLengthState();
            // Set A = 1 meter
            state = ratioReducer(state, {name: 'a', value: '1'});
            expect(state.a.toNumber()).toBeCloseTo(1, 5);

            // Change unit to feet (1 meter ≈ 3.28084 feet)
            state = ratioReducer(state, {name: 'aUnit', value: 'feet'});
            expect(state.a.toNumber()).toBeCloseTo(3.28084, 3);
        });

        test('calculates ratio correctly with length units', () => {
            let state = createLengthState();
            // Set B=2m, C=3m, D=1m → A should be 6m
            state = ratioReducer(state, {name: 'b', value: '2'});
            state = ratioReducer(state, {name: 'c', value: '3'});
            state = ratioReducer(state, {name: 'd', value: '1'});

            expect(state.a.toNumber()).toBeCloseTo(6, 5);
        });

        test('preserves ratio after unit conversion', () => {
            let state = createLengthState();
            // Set up ratio: A=6, B=2, C=3, D=1 (6:2 = 3:1)
            state = ratioReducer(state, {name: 'b', value: '2'});
            state = ratioReducer(state, {name: 'c', value: '3'});
            state = ratioReducer(state, {name: 'd', value: '1'});
            expect(state.a.toNumber()).toBeCloseTo(6, 5);

            // Convert A to feet - the numeric value changes but ratio is preserved
            state = ratioReducer(state, {name: 'aUnit', value: 'feet'});
            // A is now in feet, but the ratio A:B should still equal C:D
            // A (in feet) / B (in meters) should equal C/D when converted to same units
            const ratioAB = state.a.toNumber() / state.b.toNumber();
            const ratioCD = state.c.toNumber() / state.d.toNumber();
            // Note: ratioAB won't equal ratioCD directly because units differ
            // But A converted back to meters / B should equal C/D
            expect(state.a.to('meter').toNumber() / state.b.toNumber()).toBeCloseTo(ratioCD, 5);
        });
    });
});
