import React from "react";
import {fireEvent, screen, within} from "@testing-library/react";
import {renderWithProviders} from "../../test-utils";
import {missingInputs, SolarCalculator, sunlightFor, systemFromParams} from "./SolarCalculator";
import {CalculatorsPage} from "../Calculators";
import {DEFAULT_LOSSES, estimateProduction, MODULE_TYPES} from "./solar";
import {decodeClimatology, forgetClimatology, lookupClimatology} from "./solarData";
import {mockClimatologyFetch, SUNNY_GHI, uniformClimatology} from "./solarData.fixtures";
import {roundDigits} from "../Common";

const BASE = '/more/calculators?calc=solar';
const DENVER = `${BASE}&lat=40&lon=-105`;

const params = query => {
    const searchParams = new URLSearchParams(query);
    return key => searchParams.get(key);
};

const currentParams = () => new URLSearchParams(window.location.search);

// The estimate appears once the data file has loaded and decoded, which can be slow on a busy machine.
const findEstimate = (unit = 'DC') => screen.findByText(`kWh ${unit} per year`, {}, {timeout: 5000});

// The annual estimate the page should show for a location, from the same uniform test data.
const expectedAnnual = (overrides = {}) => {
    const grid = decodeClimatology(uniformClimatology());
    const sunlight = lookupClimatology(grid, 40, -105);
    return estimateProduction({latitude: 40, kwp: 0.4, tilt: 40, azimuth: 180, ...sunlight, ...overrides}).annual;
};

beforeEach(() => {
    forgetClimatology();
    mockClimatologyFetch();
});

describe('systemFromParams', () => {
    test('defaults when the URL is empty', () => {
        const s = systemFromParams(params(''));
        expect(s.latitude).toBeNull();
        expect(s.kwp).toBeCloseTo(0.4, 6);
        expect(s.tracking).toBe('fixed');
        expect(s.mounting).toBe('open');
        expect(s.gamma).toBe(MODULE_TYPES.standard.gamma);
        expect(s.losses).toEqual(DEFAULT_LOSSES);
        expect(s.inverterOn).toBe(false);
        expect(s.ownData).toBe(false);
        expect(s.albedo).toBeNull();
    });

    test('tilt and azimuth default from the latitude', () => {
        expect(systemFromParams(params('lat=40.4')).tilt).toBe(40);
        expect(systemFromParams(params('lat=40.4')).azimuth).toBe(180);
        expect(systemFromParams(params('lat=-33.9')).tilt).toBe(34);
        expect(systemFromParams(params('lat=-33.9')).azimuth).toBe(0);
    });

    test('invalid values fall back instead of crashing', () => {
        const s = systemFromParams(params('lat=999&track=bogus&mount=x&tilt=abc&losses=1,2,abc&alb=7&pn=-3'));
        expect(s.latitude).toBeNull();
        expect(s.tracking).toBe('fixed');
        expect(s.mounting).toBe('open');
        expect(s.tilt).toBe(0);
        expect(s.losses.slice(0, 3)).toEqual([1, 2, DEFAULT_LOSSES[2]]);
        expect(s.albedo).toBe(1);
        expect(s.kwp).toBe(0);
    });

    test('own Fahrenheit temperatures are converted to Celsius', () => {
        const s = systemFromParams(params('ghi=5&tu=f&temp=32,212'));
        expect(s.ownData).toBe(true);
        expect(s.temperature[0]).toBeCloseTo(0, 6);
        expect(s.temperature[1]).toBeCloseTo(100, 6);
        expect(s.temperatureInput[0]).toBe(32);
    });
});

describe('sunlight and missing inputs', () => {
    const grid = decodeClimatology(uniformClimatology());

    test('the NASA data is used unless the user gave their own', () => {
        const nasa = sunlightFor(systemFromParams(params('lat=40&lon=-105')), grid);
        expect(nasa.ghi[5]).toBeCloseTo(SUNNY_GHI[5], 1);
        expect(nasa.diffuse[5]).toBeCloseTo(SUNNY_GHI[5] * 0.3, 1);

        const own = sunlightFor(systemFromParams(params(`lat=40&lon=-105&ghi=${Array(12).fill(1).join(',')}`)), grid);
        expect(own.ghi).toEqual(Array(12).fill(1));
        expect(own.diffuse).toBeNull();
    });

    test('a location is enough with the NASA data', () => {
        const s = systemFromParams(params('lat=40&lon=-105'));
        expect(missingInputs(s, sunlightFor(s, grid))).toEqual([]);
        const noLon = systemFromParams(params('lat=40'));
        expect(missingInputs(noLon, sunlightFor(noLon, grid))).toEqual(['a longitude']);
    });

    test('own data needs all 12 months but no longitude', () => {
        const s = systemFromParams(params('lat=40&ghi=1,2,3'));
        expect(missingInputs(s, sunlightFor(s, grid))).toEqual(['sunlight for all 12 months']);
    });
});

describe('SolarCalculator', () => {
    test('is linked from the Engineering group of the calculators page', () => {
        renderWithProviders(<CalculatorsPage/>, {route: '/more/calculators'});
        const engineering = screen.getByRole('heading', {name: 'Engineering'}).closest('.wrolpi-header').parentElement;
        const link = within(engineering).getByRole('link', {name: /Solar/});
        expect(link).toHaveAttribute('href', '/more/calculators?calc=solar');
    });

    test('asks for a location', async () => {
        renderWithProviders(<SolarCalculator/>, {route: BASE});
        expect(await screen.findByText('Enter a latitude, a longitude to see an estimate.', {}, {timeout: 5000}))
            .toBeInTheDocument();
    });

    test('a location alone gives an estimate from the built-in data', async () => {
        renderWithProviders(<SolarCalculator/>, {route: DENVER});
        expect(await findEstimate()).toBeInTheDocument();
        expect(screen.getByText(`${roundDigits(expectedAnnual(), 0)}`)).toBeInTheDocument();
        expect(screen.getByText(/Sunlight and temperature: NASA POWER/)).toBeInTheDocument();
        expect(global.fetch).toHaveBeenCalledWith(expect.stringMatching(/\/data\/solar-climatology\.bin$/));
    });

    test('the data attribution expands', async () => {
        renderWithProviders(<SolarCalculator/>, {route: DENVER});
        await findEstimate();
        expect(screen.queryByText(/Prediction Of Worldwide Energy Resources/)).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', {name: 'Data attribution'}));
        expect(screen.getByText(/Prediction Of Worldwide Energy Resources/)).toBeInTheDocument();
        expect(screen.getByText(/WROLPi modified the data/)).toBeInTheDocument();
        expect(screen.getByText(/CC BY 4\.0/, {selector: 'p'})).toBeInTheDocument();
    });

    test('typing writes the URL and leaves defaults out', async () => {
        renderWithProviders(<SolarCalculator/>, {route: BASE});
        fireEvent.change(screen.getByLabelText('Latitude'), {target: {value: '40°0\'54"N'}});
        expect(currentParams().get('lat')).toBe('40°0\'54"N');
        expect(currentParams().get('calc')).toBe('solar');

        fireEvent.change(screen.getByLabelText('Panels'), {target: {value: '4'}});
        expect(currentParams().get('pn')).toBe('4');
        fireEvent.change(screen.getByLabelText('Panels'), {target: {value: '1'}});
        expect(currentParams().has('pn')).toBe(false);
    });

    describe('use my current location', () => {
        const withGeolocation = getCurrentPosition => {
            Object.defineProperty(window, 'isSecureContext', {value: true, configurable: true});
            Object.defineProperty(navigator, 'geolocation', {value: {getCurrentPosition}, configurable: true});
        };

        afterEach(() => {
            delete window.isSecureContext;
            delete navigator.geolocation;
        });

        test('fills in the location, rounded to 4 decimals', async () => {
            withGeolocation(success => success({coords: {latitude: 39.7392358, longitude: -104.990251}}));
            renderWithProviders(<SolarCalculator/>, {route: BASE});
            fireEvent.click(screen.getByRole('button', {name: 'Use my current location'}));
            expect(currentParams().get('lat')).toBe('39.7392');
            expect(currentParams().get('lon')).toBe('-104.9903');
            expect(screen.getByLabelText('Latitude')).toHaveValue('39.7392');
            expect(await findEstimate()).toBeInTheDocument();
        });

        test('explains a denied permission', () => {
            withGeolocation((success, failure) => failure({code: 1, message: 'User denied Geolocation'}));
            renderWithProviders(<SolarCalculator/>, {route: BASE});
            fireEvent.click(screen.getByRole('button', {name: 'Use my current location'}));
            expect(screen.getByText('Could not get your location')).toBeInTheDocument();
            expect(screen.getByText(/Location permission was denied/)).toBeInTheDocument();
            expect(currentParams().has('lat')).toBe(false);
        });

        test('is disabled without HTTPS', () => {
            Object.defineProperty(window, 'isSecureContext', {value: false, configurable: true});
            renderWithProviders(<SolarCalculator/>, {route: BASE});
            expect(screen.getByRole('button', {name: 'Use my current location'})).toBeDisabled();
        });
    });

    test('an invalid latitude is flagged', () => {
        renderWithProviders(<SolarCalculator/>, {route: `${BASE}&lat=95`});
        expect(screen.getByText('Latitude must be between -90 and 90')).toBeInTheDocument();
    });

    test('the inverter switches the results to AC', async () => {
        renderWithProviders(<SolarCalculator/>, {route: DENVER});
        await findEstimate();
        fireEvent.click(screen.getByText('Inverter: off (DC output)'));
        fireEvent.click(screen.getByLabelText('Include an inverter (AC output)'));
        expect(currentParams().get('inv')).toBe('1');
        expect(screen.getByText('kWh AC per year')).toBeInTheDocument();
    });

    test('best-for-the-year replaces a poor tilt', async () => {
        renderWithProviders(<SolarCalculator/>, {route: `${DENVER}&tilt=10`});
        await findEstimate();
        expect(screen.getByText('Panel angle: 10° tilt, facing S')).toBeInTheDocument();
        fireEvent.click(screen.getByText('Panel angle: 10° tilt, facing S'));
        fireEvent.click(await screen.findByRole('button', {name: 'Best for the year'}));
        // A result of 40 equals the default (the latitude), so it is left out of the URL.
        const tilt = Number(currentParams().get('tilt') ?? 40);
        expect(tilt).toBeGreaterThanOrEqual(30);
        expect(tilt).toBeLessThanOrEqual(44);
    });

    test('own sunlight data starts from the built-in values and replaces them', async () => {
        renderWithProviders(<SolarCalculator/>, {route: DENVER});
        await findEstimate();
        fireEvent.click(screen.getByText('Use my own sunlight data: off'));
        fireEvent.click(screen.getByLabelText('Use my own sunlight data'));

        const ghi = currentParams().get('ghi').split(',').map(Number);
        ghi.forEach((v, i) => expect(v).toBeCloseTo(SUNNY_GHI[i], 1));
        expect(screen.getByText('Using your own sunlight data.')).toBeInTheDocument();
        expect(screen.getByLabelText('Jun sunlight')).toHaveValue(`${ghi[5]}`);

        // Halving June's sunlight lowers the estimate.
        fireEvent.change(screen.getByLabelText('Jun sunlight'), {target: {value: `${ghi[5] / 2}`}});
        expect(currentParams().get('ghi').split(',')[5]).toBe(`${ghi[5] / 2}`);

        fireEvent.click(screen.getByLabelText('Use my own sunlight data'));
        expect(currentParams().has('ghi')).toBe(false);
        expect(currentParams().has('temp')).toBe(false);
    });

    test('a failed download explains how to continue', async () => {
        forgetClimatology();
        global.fetch = jest.fn(() => Promise.resolve({ok: false, status: 404}));
        renderWithProviders(<SolarCalculator/>, {route: DENVER});
        expect(await screen.findByText('Sunlight data could not be loaded', {}, {timeout: 5000})).toBeInTheDocument();
        expect(screen.getByText('Enter a location with sunlight data to see an estimate.')).toBeInTheDocument();
    });
});
