import React from 'react';
import {act, fireEvent, screen} from '@testing-library/react';
import {renderUI} from '../test-utils';
import MapQuadPicker, {formatDistance, formatSheet} from './MapQuadPicker';
import {quadAt} from './mapQuads';

// As much of a MapLibre map as the picker uses.
class FakeMap {
    constructor({zoom = 12, bounds = {west: -112.05, south: 40.26, east: -111.8, north: 40.4}} = {}) {
        this.zoom = zoom;
        this.bounds = bounds;
        this.sources = {};
        this.layers = [];
        this.handlers = {};
    }

    on(event, handler) {
        (this.handlers[event] = this.handlers[event] || []).push(handler);
    }

    off(event, handler) {
        this.handlers[event] = (this.handlers[event] || []).filter(i => i !== handler);
    }

    fire(event, data) {
        for (const handler of [...(this.handlers[event] || [])]) handler(data);
    }

    addSource(id, source) {
        this.sources[id] = {data: source.data, setData(data) { this.data = data; }};
    }

    getSource(id) {
        return this.sources[id];
    }

    removeSource(id) {
        delete this.sources[id];
    }

    addLayer(layer) {
        this.layers.push(layer);
    }

    getLayer(id) {
        return this.layers.find(i => i.id === id);
    }

    removeLayer(id) {
        this.layers = this.layers.filter(i => i.id !== id);
    }

    getZoom() {
        return this.zoom;
    }

    getBounds() {
        const {west, south, east, north} = this.bounds;
        return {getWest: () => west, getSouth: () => south, getEast: () => east, getNorth: () => north};
    }

    // What a style change does: every layer and source is gone, then the new style has loaded.
    changeStyle() {
        this.sources = {};
        this.layers = [];
        this.fire('style.load');
    }
}

const click = (map, lng, lat) => act(() => map.fire('click', {lngLat: {lng, lat}}));
const gridLines = map => map.getSource('quad-grid').data.features[0]?.geometry.coordinates || [];
const selectedIds = map => map.getSource('quad-selected').data.features.map(f => f.properties.id);
const SPRINGS = quadAt(-111.9345, 40.2802);

function renderPicker(map, props = {}) {
    const onClose = jest.fn();
    const result = renderUI(<MapQuadPicker map={map} scaleUnit="metric" onClose={onClose} {...props}/>);
    return {...result, onClose};
}

describe('choosing a quadrangle to export', () => {
    test('the grid is drawn over the view, above the layers of the map', () => {
        const map = new FakeMap();
        map.layers.push({id: 'roads'});
        renderPicker(map);

        expect(gridLines(map)).toHaveLength(7);
        expect(map.layers.map(l => l.id))
            .toEqual(['roads', 'quad-grid-lines', 'quad-selected-fill', 'quad-selected-outline']);
        expect(screen.getByText('Click a quadrangle on the map to choose it.')).toBeInTheDocument();
        expect(screen.getByRole('button', {name: 'Export PDF'})).toBeDisabled();
    });

    test('the grid follows the map', () => {
        const map = new FakeMap();
        renderPicker(map);
        map.bounds = {west: -112.05, south: 40.26, east: -111.8, north: 40.6};
        act(() => map.fire('moveend'));
        expect(gridLines(map)).toHaveLength(8);
    });

    test('there is no grid when zoomed out, and the user is told to zoom in', () => {
        const map = new FakeMap({zoom: 5});
        renderPicker(map);
        expect(gridLines(map)).toEqual([]);
        expect(screen.getByText('Zoom in to see the quadrangles.')).toBeInTheDocument();

        map.zoom = 9;
        act(() => map.fire('moveend'));
        expect(gridLines(map)).toHaveLength(7);
        expect(screen.getByText('Click a quadrangle on the map to choose it.')).toBeInTheDocument();
    });

    test('a click chooses the quadrangle under it, and says what it is', () => {
        const map = new FakeMap();
        renderPicker(map);
        click(map, -111.9345, 40.2802);

        expect(selectedIds(map)).toEqual([SPRINGS.id]);
        expect(screen.getByTestId('quad-label')).toHaveTextContent('40°15′N 112°00′W');
        expect(screen.getByTestId('quad-size'))
            .toHaveTextContent('10.6 km × 13.9 km on the ground, 44.3 cm × 57.8 cm printed');

        // Another click chooses another; there is one at a time.
        click(map, -111.8, 40.4);
        expect(selectedIds(map)).toEqual([quadAt(-111.8, 40.4).id]);
        expect(screen.getByTestId('quad-label')).toHaveTextContent('40°22′30″N 111°52′30″W');
    });

    test('a click on the chosen quadrangle lets go of it', () => {
        const map = new FakeMap();
        renderPicker(map);
        click(map, -111.9345, 40.2802);
        click(map, -111.95, 40.3);
        expect(selectedIds(map)).toEqual([]);
        expect(screen.queryByTestId('quad-label')).not.toBeInTheDocument();
    });

    test('can start with a quadrangle already chosen', () => {
        const map = new FakeMap();
        renderPicker(map, {initialQuad: SPRINGS});
        expect(selectedIds(map)).toEqual([SPRINGS.id]);
        expect(screen.getByTestId('quad-label')).toHaveTextContent('40°15′N 112°00′W');
    });

    test('the size is in the units of the map', () => {
        renderPicker(new FakeMap(), {initialQuad: SPRINGS, scaleUnit: 'imperial'});
        expect(screen.getByTestId('quad-size'))
            .toHaveTextContent('6.6 mi × 8.6 mi on the ground, 17.4 in × 22.8 in printed');
        expect(formatDistance(1609.344, 'imperial')).toBe('1.0 mi');
        expect(formatSheet(254, 'metric')).toBe('25.4 cm');
    });

    test('the grid and the choice are put back when the style of the map changes', () => {
        const map = new FakeMap();
        renderPicker(map);
        click(map, -111.9345, 40.2802);

        act(() => map.changeStyle());
        expect(map.layers.map(l => l.id)).toEqual(['quad-grid-lines', 'quad-selected-fill', 'quad-selected-outline']);
        expect(gridLines(map)).toHaveLength(7);
        expect(selectedIds(map)).toEqual([SPRINGS.id]);
    });

    test('exports the chosen quadrangle', () => {
        const onExport = jest.fn();
        renderPicker(new FakeMap(), {initialQuad: SPRINGS, onExport});
        fireEvent.click(screen.getByRole('button', {name: 'Export PDF'}));
        expect(onExport).toHaveBeenCalledWith(SPRINGS);
    });

    test('while the PDF is being made it says how far along it is, and the choice stays', () => {
        const map = new FakeMap();
        const onExport = jest.fn();
        renderPicker(map, {initialQuad: SPRINGS, onExport, status: 'Drawing Water (2 of 13)…'});

        expect(screen.getByRole('status')).toHaveTextContent('Drawing Water (2 of 13)…');
        expect(screen.getByRole('button', {name: 'Export PDF'})).toBeDisabled();
        expect(screen.getByRole('button', {name: 'Cancel'})).toBeDisabled();

        // A click on the map does not choose another quadrangle.
        click(map, -111.8, 40.4);
        expect(selectedIds(map)).toEqual([SPRINGS.id]);
        expect(screen.getByTestId('quad-label')).toHaveTextContent('40°15′N 112°00′W');
    });

    test('says why the PDF could not be made, and it can be tried again', () => {
        const onExport = jest.fn();
        renderPicker(new FakeMap(), {initialQuad: SPRINGS, onExport, error: 'Could not reach the server'});
        expect(screen.getByRole('alert')).toHaveTextContent('Could not reach the server');
        fireEvent.click(screen.getByRole('button', {name: 'Export PDF'}));
        expect(onExport).toHaveBeenCalledWith(SPRINGS);
        expect(screen.getByRole('button', {name: 'Close'})).toBeEnabled();
    });

    test('leaves nothing on the map when it is closed', () => {
        const map = new FakeMap();
        map.layers.push({id: 'roads'});
        const {onClose, unmount} = renderPicker(map);
        fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
        expect(onClose).toHaveBeenCalled();

        unmount();
        expect(map.layers.map(l => l.id)).toEqual(['roads']);
        expect(map.sources).toEqual({});
        expect(Object.values(map.handlers).flat()).toEqual([]);
    });
});
