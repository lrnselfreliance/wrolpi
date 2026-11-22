import {formatYield, WEAPON_GROUPS, WEAPON_SOURCES, weaponByKey} from './weapons.js';

const weapons = WEAPON_GROUPS.flatMap((g) => g.weapons);

describe('the weapons offered', () => {
    test('each have a unique key and a yield', () => {
        expect(new Set(weapons.map((w) => w.key)).size).toBe(weapons.length);
        for (const w of weapons) {
            expect(w.yield_kt).toBeGreaterThan(0);
            if (w.yield_range_kt) {
                const [low, high] = w.yield_range_kt;
                expect(low).toBeLessThan(high);
                expect(w.yield_kt).toBeGreaterThanOrEqual(low);
                expect(w.yield_kt).toBeLessThanOrEqual(high);
            }
            expect(w.fission_fraction).toBeGreaterThan(0);
            expect(w.fission_fraction).toBeLessThanOrEqual(1);
        }
    });

    test('each quote their yield from a cited source', () => {
        for (const w of weapons) {
            expect(w.quote.length).toBeGreaterThan(3);
            for (const key of w.source.split(', ')) expect(WEAPON_SOURCES[key]).toBeTruthy();
        }
    });

    test('are in service today: none retired, none historical', () => {
        for (const w of weapons) expect(w.status).not.toMatch(/retired$|historical|dismantled/i);
        const historical = /little boy|fat man|tsar|ivy mike|castle|b53|b28|w56/i;
        for (const w of weapons) expect(w.name).not.toMatch(historical);
    });

    test('are found by key, with their group', () => {
        expect(weaponByKey('w88')).toMatchObject({yield_kt: 455, group: 'United States'});
        expect(weaponByKey('nope')).toBeUndefined();
    });
});

describe('a yield', () => {
    test('is written in kilotons, or megatons from 1000 kt up', () => {
        expect(formatYield(0.3)).toBe('0.3 kt');
        expect(formatYield(455)).toBe('455 kt');
        expect(formatYield(1200)).toBe('1.2 Mt');
        expect(formatYield(4500)).toBe('4.5 Mt');
    });
});
