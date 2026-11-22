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
