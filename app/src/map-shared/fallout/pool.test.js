import {MOST_WORKERS, workerCount} from './pool.js';

describe('how many fallout workers run', () => {
    test('one for each core but one, left for the page', () => {
        expect(workerCount({hardwareConcurrency: 4})).toBe(3);
        expect(workerCount({hardwareConcurrency: 2})).toBe(1);
        expect(workerCount({hardwareConcurrency: 1})).toBe(1);
    });

    test('no more than a few, however many cores', () => {
        expect(workerCount({hardwareConcurrency: 8})).toBe(MOST_WORKERS);
        expect(workerCount({hardwareConcurrency: 64})).toBe(MOST_WORKERS);
    });

    test('few on a device with little memory, or which does not say', () => {
        expect(workerCount({hardwareConcurrency: 8, deviceMemory: 2})).toBe(2);
        expect(workerCount({hardwareConcurrency: 8, deviceMemory: 8})).toBe(MOST_WORKERS);
        expect(workerCount({})).toBe(1);
        expect(workerCount()).toBe(1);
    });
});
