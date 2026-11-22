import {WEAPON_CHOICES} from './FalloutPanel';

describe('the fallout panel\'s weapons', () => {
    test('are grouped by country, then a yield of one\'s own', () => {
        const groups = WEAPON_CHOICES.map((g) => g.group);
        expect(groups[0]).toBe('United States');
        expect(groups).toContain('Russia');
        expect(groups).toContain('Improvised nuclear device');
        expect(groups[groups.length - 1]).toBe('Other');
        expect(WEAPON_CHOICES[groups.length - 1].items.map((i) => i.value)).toEqual(['custom']);
    });

    test('each read differently, by name and yield', () => {
        const labels = WEAPON_CHOICES.flatMap((g) => g.items.map((i) => i.label));
        expect(new Set(labels).size).toBe(labels.length);
        expect(labels).toContain('B61-12 bomb, 0.3 kt');
    });

    test('say their yield', () => {
        const w88 = WEAPON_CHOICES[0].items.find((i) => i.value === 'w88');
        expect(w88.label).toBe('W88 (Trident II D5), 455 kt');
    });
});

describe('the fallout panel\'s winds', () => {
    const {windProfile, hourLabel} = require('./FalloutPanel');
    const forecast = {
        elevation: 600,
        hours: [{time: '2026-11-22T00:00Z', winds: [[610, 2, 180], [1500, 10, 270]]}],
    };

    test('take a forecast hour\'s winds, at heights above ground zero', () => {
        const profile = windProfile({wind: 'forecast', forecast, hour: 0, groundElevation: 100});
        expect(profile.map((p) => p[0])).toEqual([510, 1400]);
    });

    test('fall back to one wind at every height until there is a forecast', () => {
        const profile = windProfile({wind: 'forecast', forecast: null, direction: 270, speed: 10});
        expect(profile).toHaveLength(1);
        expect(profile[0][1]).toBeGreaterThan(0);
    });

    test('mark the hour nearest now', () => {
        expect(hourLabel('2026-11-22T00:00Z', true)).toMatch(/\(now\)$/);
        expect(hourLabel('2026-11-22T00:00Z', false)).not.toMatch(/now/);
    });
});
