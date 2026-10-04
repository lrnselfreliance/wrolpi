import React from 'react';
import {renderWithProviders as render} from '../test-utils';
import MapViewer from './MapViewer';

// MapLibre needs WebGL, which jsdom lacks; these tests only cover what the viewer does to the URL.
jest.mock('maplibre-gl', () => ({
    __esModule: true,
    default: {Map: class {
        }, addProtocol: jest.fn(), Marker: class {
        }, Popup: class {
        }},
}));
jest.mock('maplibre-gl/dist/maplibre-gl.css', () => ({}));
jest.mock('pmtiles', () => ({
    __esModule: true, Protocol: class {
        tile = jest.fn();
    },
}));
jest.mock('protomaps-themes-base', () => ({__esModule: true, default: () => []}));
jest.mock('@acalcutt/maplibre-contour-pmtiles', () => ({__esModule: true, default: {}}));
jest.mock('../api', () => ({
    ...jest.requireActual('../api'),
    // Never resolves: the map never initializes, which these tests do not need.
    getMapFiles: jest.fn(() => new Promise(() => {
    })),
    getMapPins: jest.fn(() => new Promise(() => {
    })),
}));

describe('the map position in the URL', () => {
    test('is removed when the map closes', () => {
        const {unmount} = render(<MapViewer/>, {route: '/map?lat=40&lon=-105&z=8&layer=a'});
        unmount();
        expect(window.location.pathname).toBe('/map');
        expect(window.location.search).toBe('?layer=a');
    });

    test('is not removed from the page the map navigated to', () => {
        // "Calculate Solar Performance" navigates to a page whose own lat/lon must survive the map closing.
        const {unmount} = render(<MapViewer/>, {route: '/map?lat=40&lon=-105&z=8'});
        window.history.pushState({}, '', '/more/calculators?calc=solar&lat=40.0154&lon=-105.2705');
        unmount();
        expect(window.location.search).toBe('?calc=solar&lat=40.0154&lon=-105.2705');
    });
});
