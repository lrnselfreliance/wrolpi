import {calcPowerLossPercent} from "./ElectricalCalculators";

describe('calcPowerLossPercent Function Tests', () => {
    test('should correctly calculate power loss percentage', () => {
        // Parameters: isSAE, volts, amps, resistancePerKm, length
        const percent = calcPowerLossPercent(true, 120, 8.33, 2.58, 200);
        expect(percent).toBeCloseTo(7.16, 2); // Use expected correct value and precision
    });
});
