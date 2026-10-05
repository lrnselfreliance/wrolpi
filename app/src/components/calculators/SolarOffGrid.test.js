import React from "react";
import {fireEvent, screen} from "@testing-library/react";
import {renderWithProviders} from "../../test-utils";
import {offGridFromParams, offGridResults} from "./SolarOffGrid";
import {SolarCalculator} from "./SolarCalculator";
import {forgetClimatology} from "./solarData";
import {mockClimatologyFetch} from "./solarData.fixtures";

const params = query => {
    const searchParams = new URLSearchParams(query);
    return key => searchParams.get(key);
};
const currentParams = () => new URLSearchParams(window.location.search);
const TEMPS = [-1, 0, 5, 10, 15, 20, 24, 22, 18, 10, 4, -1];
const DEC = {month: 'Dec', energyDaily: 3};

describe('offGridFromParams', () => {
    test('defaults', () => {
        const o = offGridFromParams(params(''), TEMPS);
        expect(o.loads).toEqual([]);
        expect(o.acLoads).toBe(true);
        expect(o.battery).toBe('lfp');
        expect(o.dod).toBe(80);
        expect(o.systemVoltage).toBe(12);
        expect(o.days).toBe(2);
        expect(o.controller).toBe('mppt');
        expect(o.series).toBe(1);
        expect(o.coldestMonthly).toBe(-1);
        expect(o.coldest).toBe(-26);
    });

    test('the depth of discharge follows the battery type unless set', () => {
        expect(offGridFromParams(params('bat=lead'), TEMPS).dod).toBe(50);
        expect(offGridFromParams(params('bat=lead&dod=60'), TEMPS).dod).toBe(60);
    });

    test('a Voc coefficient without its minus sign is read as negative, even from a shared link', () => {
        expect(offGridFromParams(params('bvoc=0.27'), TEMPS).betaVoc).toBe(-0.27);
        expect(offGridFromParams(params('bvoc=-0.3'), TEMPS).betaVoc).toBe(-0.3);
    });

    test('invalid values fall back', () => {
        const o = offGridFromParams(params('bat=x&sv=13&ctl=y&ns=0&aut=-1'), null);
        expect(o.battery).toBe('lfp');
        expect(o.systemVoltage).toBe(12);
        expect(o.controller).toBe('mppt');
        expect(o.series).toBe(1);
        expect(o.days).toBe(0);
        expect(o.coldest).toBe(-20);
    });
});

describe('offGridResults', () => {
    // 1000 Wh/day of AC devices through a 90% inverter, LiFePO4 at 80%, 2 days, 12 V.
    const o = offGridFromParams(params('load=Stuff~100~10'), TEMPS);

    test('battery and panels for the worst month', () => {
        const r = offGridResults(o, DEC, 400, 1);
        expect(r.devicesWh).toBe(1000);
        expect(r.batteryLoadWh).toBeCloseTo(1111.1, 1);
        expect(r.bank.nominalWh).toBeCloseTo(2777.8, 1);
        expect(r.bank.ah).toBeCloseTo(231.5, 1);
        // 1.111 kWh / (3 kWh/kWp x 95%) = 0.390 kW: one 400 W panel.
        expect(r.kwp).toBeCloseTo(0.3899, 4);
        expect(r.panelsNeeded).toBe(1);
        // One 400 W panel: 3 x 0.4 x 95% = 1.14 kWh for 1.111 kWh of use.
        expect(r.coverage).toBeCloseTo(1.026, 3);
    });

    test('DC devices skip the inverter loss', () => {
        const dc = offGridResults(offGridFromParams(params('load=Stuff~100~10&ac=0'), TEMPS), DEC, 400, 1);
        expect(dc.batteryLoadWh).toBe(1000);
    });

    test('a PWM controller needs more panels', () => {
        const pwm = offGridResults(offGridFromParams(params('load=Stuff~100~10&ctl=pwm'), TEMPS), DEC, 400, 1);
        // Only 14.4 / 31 of each panel is used: 0.390 / 0.4645 = 0.839 kW, three panels.
        expect(pwm.panelsNeeded).toBe(3);
    });

    test('an outdoor lead-acid bank is enlarged for the cold', () => {
        const indoor = offGridResults(offGridFromParams(params('load=Stuff~100~10&bat=lead'), TEMPS), DEC, 400, 1);
        const outdoor = offGridResults(offGridFromParams(params('load=Stuff~100~10&bat=lead&bout=1'), TEMPS),
            DEC, 400, 1);
        // Coldest month -1 °C: 79% of rated capacity.
        expect(outdoor.bank.nominalWh).toBeCloseTo(indoor.bank.nominalWh / 0.79, 1);
        expect(outdoor.warnings).toHaveLength(1);
    });

    test('nothing to size without devices or an estimate', () => {
        const none = offGridResults(offGridFromParams(params(''), TEMPS), DEC, 400, 1);
        expect(none.bank).toBeNull();
        expect(none.panelsNeeded).toBeNull();
        expect(offGridResults(o, null, 400, 1).panelsNeeded).toBeNull();
    });
});

describe('the off-grid tab', () => {
    const OFFGRID = '/more/calculators?calc=solar&lat=40&lon=-105&tab=offgrid';

    beforeEach(() => {
        forgetClimatology();
        mockClimatologyFetch();
    });

    const findNeeds = () => screen.findByText('What you need', {}, {timeout: 5000});

    test('devices are added to the URL and the system is sized', async () => {
        renderWithProviders(<SolarCalculator/>, {route: OFFGRID});
        expect(await screen.findByText('Add your devices', {}, {timeout: 5000})).toBeInTheDocument();
        fireEvent.change(screen.getByLabelText('Device 1 name'), {target: {value: 'Fridge'}});
        fireEvent.change(screen.getByLabelText('Device 1 watts'), {target: {value: '50'}});
        fireEvent.change(screen.getByLabelText('Device 1 hours'), {target: {value: '24'}});
        expect(currentParams().get('load')).toBe('Fridge~50~24');
        expect(await findNeeds()).toBeInTheDocument();
        expect(screen.getByText('1200 Wh')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', {name: 'Add device'}));
        expect(screen.getByLabelText('Device 2 name')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', {name: 'Remove device 2'}));
        expect(screen.queryByLabelText('Device 2 name')).not.toBeInTheDocument();
    });

    test('the suggested panel count can be applied', async () => {
        renderWithProviders(<SolarCalculator/>, {route: `${OFFGRID}&load=Heater~500~10`});
        await findNeeds();
        const button = screen.getByRole('button', {name: /^Use \d+ panels$/});
        const suggested = button.textContent.match(/\d+/)[0];
        fireEvent.click(button);
        expect(currentParams().get('pn')).toBe(suggested);
    });

    test('too many panels in series warns before it destroys the controller', async () => {
        renderWithProviders(<SolarCalculator/>, {route: `${OFFGRID}&load=Fridge~50~24&ns=3&pn=3`});
        await findNeeds();
        expect(screen.getByText('Too much voltage for the controller')).toBeInTheDocument();
    });

    test('PWM panels that cannot reach a 48 V battery say so instead of sizing a system', async () => {
        renderWithProviders(<SolarCalculator/>, {route: `${OFFGRID}&load=Fridge~50~24&ctl=pwm&sv=48`});
        await findNeeds();
        expect(screen.getByText('Too little voltage to charge')).toBeInTheDocument();
        expect(screen.getByText(/a PWM controller cannot charge it at all/)).toBeInTheDocument();
        expect(screen.queryByRole('button', {name: /^Use \d+ panels$/})).not.toBeInTheDocument();
    });

    test('while the data downloads, it shows a loader and no cold-morning verdict', async () => {
        forgetClimatology();
        global.fetch = jest.fn(() => new Promise(() => {
        }));
        renderWithProviders(<SolarCalculator/>, {route: `${OFFGRID}&load=Fridge~50~24`});
        // One beside the location, one in place of the sizing.
        expect(screen.getAllByLabelText('Loading sunlight data')).toHaveLength(2);
        expect(screen.queryByText('Almost there')).not.toBeInTheDocument();
        expect(screen.queryByText('String voltage on the coldest morning')).not.toBeInTheDocument();
    });

    test('a coldest morning the user typed is checked even while the data downloads', async () => {
        forgetClimatology();
        global.fetch = jest.fn(() => new Promise(() => {
        }));
        renderWithProviders(<SolarCalculator/>, {route: `${OFFGRID}&load=Fridge~50~24&tmin=-30`});
        expect(screen.getByText('String voltage on the coldest morning')).toBeInTheDocument();
    });

    test('the tab is remembered in the URL', async () => {
        renderWithProviders(<SolarCalculator/>, {route: '/more/calculators?calc=solar&lat=40&lon=-105'});
        fireEvent.click(screen.getByRole('tab', {name: 'Off-grid sizing'}));
        expect(currentParams().get('tab')).toBe('offgrid');
        fireEvent.click(screen.getByRole('tab', {name: 'Estimate'}));
        expect(currentParams().has('tab')).toBe(false);
    });
});
