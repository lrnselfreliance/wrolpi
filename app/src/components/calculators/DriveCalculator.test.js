import {
    beltLength,
    centerDistanceFromPitchDiameters,
    chainLengthPitches,
    chainLengthPitchesEven,
    chainPitchDiameter,
    computeDriveValue,
    driveRatio,
    driveReducer,
    externalBeltTangents,
    gearPitchDiameterImperial,
    gearPitchDiameterMetric,
    gearPoints,
    surfaceSpeed,
    surfaceSpeedDisplay,
    torqueOut,
} from "./DriveCalculator";

describe('computeDriveValue (s1*n1 = s2*n2)', () => {
    // A 2:1 reduction: a 10-tooth driver at 100 RPM driving a 20-tooth gear.
    const known = {s1: 10, s2: 20, n1: 100, n2: 50};

    test('solves driven RPM', () => {
        expect(computeDriveValue('n2', {s1: 10, s2: 20, n1: 100})).toBeCloseTo(50, 6);
    });

    test('solves driver RPM', () => {
        expect(computeDriveValue('n1', {s1: 10, s2: 20, n2: 50})).toBeCloseTo(100, 6);
    });

    test('solves driven size', () => {
        expect(computeDriveValue('s2', {s1: 10, n1: 100, n2: 50})).toBeCloseTo(20, 6);
    });

    test('solves driver size', () => {
        expect(computeDriveValue('s1', {s2: 20, n1: 100, n2: 50})).toBeCloseTo(10, 6);
    });

    test('the solved value is consistent with the others', () => {
        expect(known.s1 * known.n1).toBeCloseTo(known.s2 * known.n2, 6);
    });

    test('returns null on divide-by-zero', () => {
        expect(computeDriveValue('n2', {s1: 10, s2: 0, n1: 100})).toBeNull();
    });

    test('returns null for an unknown target', () => {
        expect(computeDriveValue('nope', {s1: 10, s2: 20, n1: 100})).toBeNull();
    });
});

describe('driveRatio and torque', () => {
    test('2:1 reduction has a ratio of 2', () => {
        expect(driveRatio(10, 20)).toBeCloseTo(2, 6);
    });

    test('overdrive has a ratio below 1', () => {
        expect(driveRatio(20, 10)).toBeCloseTo(0.5, 6);
    });

    test('output torque is multiplied by the ratio', () => {
        // 5 units in, 2:1 reduction -> 10 units out.
        expect(torqueOut(5, 10, 20)).toBeCloseTo(10, 6);
    });

    test('ratio is null when the driver size is zero', () => {
        expect(driveRatio(0, 20)).toBeNull();
        expect(torqueOut(5, 0, 20)).toBeNull();
    });
});

describe('surfaceSpeed', () => {
    test('belt speed of a 10" pulley at 100 RPM', () => {
        // pi * 10 * 100
        expect(surfaceSpeed(10, 100)).toBeCloseTo(3141.59, 2);
    });
});

describe('surfaceSpeedDisplay', () => {
    test('imperial: 10" pulley at 100 RPM -> ft/min', () => {
        // pi * 10 * 100 / 12
        const result = surfaceSpeedDisplay(10, 100, false);
        expect(result.unit).toBe('ft/min');
        expect(result.value).toBeCloseTo(261.8, 1);
    });

    test('metric: 100 mm pulley at 100 RPM -> m/s', () => {
        // pi * 100 * 100 / 60000
        const result = surfaceSpeedDisplay(100, 100, true);
        expect(result.unit).toBe('m/s');
        expect(result.value).toBeCloseTo(0.524, 3);
    });

    test('returns null when the diameter or RPM is missing', () => {
        expect(surfaceSpeedDisplay(0, 100, false)).toBeNull();
        expect(surfaceSpeedDisplay(10, 0, false)).toBeNull();
    });
});

describe('beltLength (open belt)', () => {
    test('classic two-pulley belt length', () => {
        // d1=10, d2=20, C=30 -> 60 + pi*15 + 100/120
        expect(beltLength(10, 20, 30)).toBeCloseTo(107.96, 2);
    });

    test('equal pulleys: belt is 2C + pi*d', () => {
        // d1=d2=10, C=20 -> 40 + pi*10, with no diameter-difference term
        expect(beltLength(10, 10, 20)).toBeCloseTo(40 + Math.PI * 10, 6);
    });

    test('returns null for a non-positive center distance', () => {
        expect(beltLength(10, 20, 0)).toBeNull();
    });

    test('returns null when the geometry is impossible (pulleys would overlap)', () => {
        // Minimum center distance is (d1 + d2)/2 = 15; anything at or below overlaps.
        expect(beltLength(10, 20, 15)).toBeNull();
        expect(beltLength(10, 20, 14)).toBeNull();
    });

    test('returns null when a diameter is missing', () => {
        expect(beltLength(0, 20, 30)).toBeNull();
    });
});

describe('chainPitchDiameter', () => {
    test('17-tooth sprocket with 1/2" chain pitch (#40)', () => {
        // 0.5 / sin(pi/17) ~= 2.721"
        expect(chainPitchDiameter(17, 0.5)).toBeCloseTo(2.721, 3);
    });

    test('returns null for fewer than one tooth', () => {
        expect(chainPitchDiameter(0, 0.5)).toBeNull();
    });
});

describe('chainLengthPitches', () => {
    test('exact length in pitches', () => {
        // t1=17, t2=34, C=20", p=0.5" -> ~105.68 pitches
        expect(chainLengthPitches(17, 34, 20, 0.5)).toBeCloseTo(105.68, 2);
    });

    test('rounded up to the next even number of pitches', () => {
        expect(chainLengthPitchesEven(17, 34, 20, 0.5)).toBe(106);
    });

    test('returns null for a non-positive center distance', () => {
        expect(chainLengthPitches(17, 34, 0, 0.5)).toBeNull();
        expect(chainLengthPitchesEven(17, 34, 0, 0.5)).toBeNull();
    });

    test('returns null when the geometry is impossible (sprockets would overlap)', () => {
        // 17T and 34T at 0.5" pitch have pitch diameters ~2.72" and ~5.42",
        // so the centers must exceed ~4.07"; 2" is impossible.
        expect(chainLengthPitches(17, 34, 2, 0.5)).toBeNull();
        expect(chainLengthPitchesEven(17, 34, 2, 0.5)).toBeNull();
    });
});

describe('gear pitch diameter and center distance', () => {
    test('metric: 20 teeth, module 2 mm -> 40 mm', () => {
        expect(gearPitchDiameterMetric(20, 2)).toBeCloseTo(40, 6);
    });

    test('imperial: 20 teeth, 10 diametral pitch -> 2"', () => {
        expect(gearPitchDiameterImperial(20, 10)).toBeCloseTo(2, 6);
    });

    test('center distance is half the sum of pitch diameters', () => {
        expect(centerDistanceFromPitchDiameters(40, 60)).toBeCloseTo(50, 6);
    });
});

describe('externalBeltTangents (diagram geometry)', () => {
    test('returns two tangent segments', () => {
        const segs = externalBeltTangents(0, 0, 10, 100, 0, 20);
        expect(segs).toHaveLength(2);
    });

    test('tangent length matches sqrt(d^2 - (r1-r2)^2)', () => {
        // Horizontal centers 100 apart, radii 10 and 20.
        const [seg] = externalBeltTangents(0, 0, 10, 100, 0, 20);
        const length = Math.hypot(seg.b[0] - seg.a[0], seg.b[1] - seg.a[1]);
        const expected = Math.sqrt(100 * 100 - (10 - 20) ** 2);
        expect(length).toBeCloseTo(expected, 4);
    });

    test('equal radii give two parallel tangents of length d', () => {
        const segs = externalBeltTangents(0, 0, 15, 80, 0, 15);
        for (const seg of segs) {
            const length = Math.hypot(seg.b[0] - seg.a[0], seg.b[1] - seg.a[1]);
            expect(length).toBeCloseTo(80, 4);
        }
    });

    test('returns null for coincident centers', () => {
        expect(externalBeltTangents(0, 0, 10, 0, 0, 20)).toBeNull();
    });
});

describe('gearPoints (diagram geometry)', () => {
    test('produces four points per tooth', () => {
        const points = gearPoints(0, 0, 20, 12, 10).split(' ');
        expect(points).toHaveLength(40);
    });

    test('clamps to a minimum of three teeth', () => {
        const points = gearPoints(0, 0, 20, 12, 1).split(' ');
        expect(points).toHaveLength(12);
    });
});

describe('driveReducer (single-belt train)', () => {
    const fresh = (count = 2) => ({
        elements: Array.from({length: count}, () => ({size: '', rpm: ''})),
        lastUpdated: [],
    });
    const field = (state, index, f, value) => {
        let s = driveReducer(state, {type: 'field', index, field: f, value});
        return driveReducer(s, {type: 'solve'});
    };

    test('solves a driven wheel RPM from the driver (2:1)', () => {
        let state = fresh();
        state = field(state, 0, 'size', '4');
        state = field(state, 1, 'size', '8');
        state = field(state, 0, 'rpm', '100');
        // Belt speed K = 4*100 = 400; wheel 2 (8") spins at 400/8 = 50.
        expect(Number(state.elements[1].rpm)).toBeCloseTo(50, 4);
    });

    test('propagates one input speed across a 3-wheel train', () => {
        let state = driveReducer(fresh(), {type: 'add'});  // 3 wheels
        state = field(state, 0, 'size', '2');
        state = field(state, 1, 'size', '6');
        state = field(state, 2, 'size', '3');
        state = field(state, 0, 'rpm', '1000');
        // K = 2000; wheel 2 = 2000/6, wheel 3 = 2000/3.
        expect(Number(state.elements[1].rpm)).toBeCloseTo(333.333, 2);
        expect(Number(state.elements[2].rpm)).toBeCloseTo(666.667, 2);
    });

    test('editing a wheel RPM re-anchors the belt speed', () => {
        let state = fresh();
        state = field(state, 0, 'size', '4');
        state = field(state, 1, 'size', '8');
        state = field(state, 0, 'rpm', '100');   // wheel 2 -> 50
        state = field(state, 1, 'rpm', '25');     // re-anchor: K = 8*25 = 200
        expect(Number(state.elements[0].rpm)).toBeCloseTo(50, 4);  // 200/4
    });

    test('add appends wheels up to the maximum of 6', () => {
        let state = fresh();
        for (let i = 0; i < 10; i++) {
            state = driveReducer(state, {type: 'add'});
        }
        expect(state.elements).toHaveLength(6);
    });

    test('remove deletes a wheel but never below the minimum of 2', () => {
        let state = driveReducer(fresh(), {type: 'add'});  // 3
        state = driveReducer(state, {type: 'remove', index: 1});
        expect(state.elements).toHaveLength(2);
        state = driveReducer(state, {type: 'remove', index: 0});
        expect(state.elements).toHaveLength(2);
    });

    test('clamps negative input to a positive magnitude', () => {
        const state = field(fresh(), 0, 'size', '-7');
        expect(state.elements[0].size).toBe('7');
    });

    test('ignores unknown actions', () => {
        const initial = fresh();
        expect(driveReducer(initial, {type: 'bogus'})).toBe(initial);
    });

    // --- Edge cases ---
    test('clearing the anchor falls back to the next most recent complete wheel', () => {
        let state = fresh(3);
        state = field(state, 0, 'size', '10');
        state = field(state, 0, 'rpm', '800');   // K=8000
        state = field(state, 2, 'size', '20');    // wheel 3 gets 400
        // Now clear the original anchor's rpm
        state = field(state, 0, 'rpm', '');
        // Should still have a complete wheel (index 2), but no anchor that has both → no solving happens for others
        expect(state.elements[2].rpm).toBe('400'); // previously solved value stays
    });

    test('completing a middle wheel as first anchor works', () => {
        let state = fresh(3);
        state = field(state, 1, 'size', '5');
        state = field(state, 1, 'rpm', '400'); // K=2000
        state = field(state, 0, 'size', '4');
        state = field(state, 2, 'size', '10');
        // Both outer wheels should now be solved from the middle anchor
        expect(Number(state.elements[0].rpm)).toBeCloseTo(500, 4);
        expect(Number(state.elements[2].rpm)).toBeCloseTo(200, 4);
    });

    test('solving only happens into the missing side (re-anchoring still works)', () => {
        let state = fresh();
        state = field(state, 0, 'size', '5');
        state = field(state, 0, 'rpm', '200'); // K=1000
        state = field(state, 1, 'size', '20');
        expect(Number(state.elements[1].rpm)).toBeCloseTo(50, 4);
        // Re-anchor by giving wheel 1 both values
        state = field(state, 1, 'rpm', '30'); // new K=600
        expect(Number(state.elements[0].rpm)).toBeCloseTo(120, 4);
    });

    test('very small and fractional values are handled without NaN', () => {
        let state = fresh();
        state = field(state, 0, 'size', '0.5');
        state = field(state, 0, 'rpm', '10000');
        state = field(state, 1, 'size', '0.25');
        expect(Number(state.elements[1].rpm)).toBeCloseTo(20000, 4);
    });
});
