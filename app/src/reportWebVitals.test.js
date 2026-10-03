jest.mock('web-vitals', () => ({
    onCLS: jest.fn(),
    onINP: jest.fn(),
    onFCP: jest.fn(),
    onLCP: jest.fn(),
    onTTFB: jest.fn(),
}));

import reportWebVitals from './reportWebVitals';
import * as webVitals from 'web-vitals';

describe('reportWebVitals', () => {
    test('subscribes the callback to every current web-vitals metric', async () => {
        const callback = jest.fn();
        const pending = reportWebVitals(callback);
        expect(pending).toBeDefined();
        await pending;
        for (const name of ['onCLS', 'onINP', 'onFCP', 'onLCP', 'onTTFB']) {
            expect(webVitals[name]).toHaveBeenCalledWith(callback);
        }
    });

    test('does nothing without a function', async () => {
        jest.clearAllMocks();
        expect(reportWebVitals(undefined)).toBeUndefined();
        expect(webVitals.onCLS).not.toHaveBeenCalled();
    });
});
