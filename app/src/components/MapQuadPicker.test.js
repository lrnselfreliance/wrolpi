import React from 'react';
import {act, fireEvent, screen, waitFor} from '@testing-library/react';
import {renderUI} from '../test-utils';
import MapQuadPicker, {formatDistance, formatSheet} from './MapQuadPicker';
import {quadAt} from './mapQuads';

// As much of a MapLibre map as the picker uses.
class FakeMap {
    constructor({zoom = 12, bounds = {west: -105.175, south: 40.26, east: -104.925, north: 40.4}} = {}) {
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
const BERTHOUD = quadAt(-105.0595, 40.31);

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
        map.bounds = {west: -105.175, south: 40.26, east: -104.925, north: 40.6};
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
        click(map, -105.0595, 40.31);

        expect(selectedIds(map)).toEqual([BERTHOUD.id]);
        expect(screen.getByTestId('quad-label')).toHaveTextContent('40°15′N 105°07′30″W');
        expect(screen.getByTestId('quad-size'))
            .toHaveTextContent('10.6 km × 13.9 km on the ground, 44.3 cm × 57.8 cm printed');

        // Another click chooses another; there is one at a time.
        click(map, -104.925, 40.4);
        expect(selectedIds(map)).toEqual([quadAt(-104.925, 40.4).id]);
        expect(screen.getByTestId('quad-label')).toHaveTextContent('40°22′30″N 105°00′W');
    });

    test('a click on the chosen quadrangle lets go of it', () => {
        const map = new FakeMap();
        renderPicker(map);
        click(map, -105.0595, 40.31);
        click(map, -105.075, 40.3);
        expect(selectedIds(map)).toEqual([]);
        expect(screen.queryByTestId('quad-label')).not.toBeInTheDocument();
    });

    test('can start with a quadrangle already chosen', () => {
        const map = new FakeMap();
        renderPicker(map, {initialQuad: BERTHOUD});
        expect(selectedIds(map)).toEqual([BERTHOUD.id]);
        expect(screen.getByTestId('quad-label')).toHaveTextContent('40°15′N 105°07′30″W');
    });

    test('the size is in the units of the map', () => {
        renderPicker(new FakeMap(), {initialQuad: BERTHOUD, scaleUnit: 'imperial'});
        expect(screen.getByTestId('quad-size'))
            .toHaveTextContent('6.6 mi × 8.6 mi on the ground, 17.4 in × 22.8 in printed');
        expect(formatDistance(1609.344, 'imperial')).toBe('1.0 mi');
        expect(formatSheet(254, 'metric')).toBe('25.4 cm');
    });

    test('the grid and the choice are put back when the style of the map changes', () => {
        const map = new FakeMap();
        renderPicker(map);
        click(map, -105.0595, 40.31);

        act(() => map.changeStyle());
        expect(map.layers.map(l => l.id)).toEqual(['quad-grid-lines', 'quad-selected-fill', 'quad-selected-outline']);
        expect(gridLines(map)).toHaveLength(7);
        expect(selectedIds(map)).toEqual([BERTHOUD.id]);
    });

    test('exports the chosen quadrangle', () => {
        const onExport = jest.fn();
        renderPicker(new FakeMap(), {initialQuad: BERTHOUD, onExport});
        fireEvent.click(screen.getByRole('button', {name: 'Export PDF'}));
        expect(onExport).toHaveBeenCalledWith(BERTHOUD, {sheet: true, dpi: 300, name: null});
    });

    test('while the PDF is being made, Cancel stops it and the picker stays', () => {
        const onCancel = jest.fn();
        const {onClose} = renderPicker(new FakeMap(), {
            initialQuad: BERTHOUD, onExport: jest.fn(), onCancel, status: 'Making the PDF (40%)…',
        });
        const cancel = screen.getByRole('button', {name: 'Cancel'});
        expect(cancel).toBeEnabled();
        fireEvent.click(cancel);
        expect(onCancel).toHaveBeenCalledTimes(1);
        expect(onClose).not.toHaveBeenCalled();
    });

    test('when nothing is being made, Cancel closes the picker', () => {
        const onCancel = jest.fn();
        const {onClose} = renderPicker(new FakeMap(), {initialQuad: BERTHOUD, onExport: jest.fn(), onCancel});
        fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
        expect(onClose).toHaveBeenCalledTimes(1);
        expect(onCancel).not.toHaveBeenCalled();
    });

    test('exports the map alone when the sheet is turned off', () => {
        const onExport = jest.fn();
        renderPicker(new FakeMap(), {initialQuad: BERTHOUD, onExport});
        const sheet = screen.getByRole('checkbox', {name: 'Margins, grid and scale bars'});
        expect(sheet).toBeChecked();
        fireEvent.click(sheet);
        fireEvent.click(screen.getByRole('button', {name: 'Export PDF'}));
        expect(onExport).toHaveBeenCalledWith(BERTHOUD, {sheet: false, dpi: 300, name: null});
    });

    test('exports a sharper map when one is asked for', () => {
        const onExport = jest.fn();
        renderPicker(new FakeMap(), {initialQuad: BERTHOUD, onExport});
        expect(screen.getByRole('radio', {name: '300 DPI'})).toBeChecked();
        fireEvent.click(screen.getByRole('radio', {name: '400 DPI'}));
        fireEvent.click(screen.getByRole('button', {name: 'Export PDF'}));
        expect(onExport).toHaveBeenCalledWith(BERTHOUD, {sheet: true, dpi: 400, name: null});
    });

    test('the look the map is exported in is chosen, and not while a map is exported', () => {
        const onLook = jest.fn();
        const {unmount} = renderPicker(new FakeMap(), {initialQuad: BERTHOUD, look: 'print', onLook});
        expect(screen.getByRole('radio', {name: 'Print'})).toBeChecked();
        fireEvent.click(screen.getByRole('radio', {name: 'Dark'}));
        expect(onLook).toHaveBeenCalledWith('dark');
        unmount();

        renderPicker(new FakeMap(), {
            initialQuad: BERTHOUD, look: 'dark', onLook, status: 'Drawing Water (1 of 12)…',
        });
        expect(screen.getByRole('radio', {name: 'Dark'})).toBeChecked();
        expect(screen.getByRole('radio', {name: 'Light'})).toBeDisabled();
    });

    test('there is no look to choose where none is given', () => {
        renderPicker(new FakeMap(), {initialQuad: BERTHOUD});
        expect(screen.queryByRole('radio', {name: 'Print'})).toBeNull();
    });

    test('says what the USGS calls the quadrangle, and exports it by that name', async () => {
        const named = {name: 'Berthoud', state: 'Colorado', exact: true};
        const fetchName = jest.fn().mockResolvedValue(named);
        const onExport = jest.fn();
        renderPicker(new FakeMap(), {initialQuad: BERTHOUD, onExport, fetchName});
        expect(await screen.findByTestId('quad-name')).toHaveTextContent('Berthoud, Colorado');
        expect(fetchName).toHaveBeenCalledWith(BERTHOUD);
        // Where it is, is still said.
        expect(screen.getByTestId('quad-label')).toHaveTextContent('40°15′N 105°07′30″W');
        fireEvent.click(screen.getByRole('button', {name: 'Export PDF'}));
        expect(onExport).toHaveBeenCalledWith(BERTHOUD, {sheet: true, dpi: 300, name: named});
    });

    test('a quadrangle the USGS has no name for goes by where it is', async () => {
        const fetchName = jest.fn().mockResolvedValue(null);
        const onExport = jest.fn();
        renderPicker(new FakeMap(), {initialQuad: BERTHOUD, onExport, fetchName});
        await waitFor(() => expect(fetchName).toHaveBeenCalled());
        expect(screen.queryByTestId('quad-name')).toBeNull();
        fireEvent.click(screen.getByRole('button', {name: 'Export PDF'}));
        expect(onExport).toHaveBeenCalledWith(BERTHOUD, {sheet: true, dpi: 300, name: null});
    });

    test('a name which can not be asked for is no name', async () => {
        const fetchName = jest.fn().mockRejectedValue(new Error('offline'));
        renderPicker(new FakeMap(), {initialQuad: BERTHOUD, fetchName});
        await waitFor(() => expect(fetchName).toHaveBeenCalled());
        expect(screen.queryByTestId('quad-name')).toBeNull();
        expect(screen.getByTestId('quad-label')).toBeInTheDocument();
    });

    test('the name of one quadrangle is not shown for another', async () => {
        let answer;
        const fetchName = jest.fn()
            .mockImplementationOnce(() => new Promise(resolve => {
                answer = resolve;
            }))
            .mockResolvedValue({name: 'Windsor', state: 'Colorado', exact: true});
        const map = new FakeMap();
        renderPicker(map, {initialQuad: BERTHOUD, fetchName});
        // Another quadrangle is chosen before the first is named.
        act(() => map.fire('click', {lngLat: {lng: -104.925, lat: 40.4}}));
        expect(await screen.findByTestId('quad-name')).toHaveTextContent('Windsor, Colorado');
        await act(async () => answer({name: 'Berthoud', state: 'Colorado', exact: true}));
        expect(screen.getByTestId('quad-name')).toHaveTextContent('Windsor, Colorado');
    });

    test('while the PDF is being made it says how far along it is, and the choice stays', () => {
        const map = new FakeMap();
        const onExport = jest.fn();
        renderPicker(map, {initialQuad: BERTHOUD, onExport, status: 'Drawing Water (2 of 13)…'});

        expect(screen.getByRole('status')).toHaveTextContent('Drawing Water (2 of 13)…');
        expect(screen.getByRole('button', {name: 'Export PDF'})).toBeDisabled();
        // An export which can not be stopped has no way to stop it.
        expect(screen.getByRole('button', {name: 'Cancel'})).toBeDisabled();

        // A click on the map does not choose another quadrangle.
        click(map, -104.925, 40.4);
        expect(selectedIds(map)).toEqual([BERTHOUD.id]);
        expect(screen.getByTestId('quad-label')).toHaveTextContent('40°15′N 105°07′30″W');
    });

    test('says why the PDF could not be made, and it can be tried again', () => {
        const onExport = jest.fn();
        renderPicker(new FakeMap(), {initialQuad: BERTHOUD, onExport, error: 'Could not reach the server'});
        expect(screen.getByRole('alert')).toHaveTextContent('Could not reach the server');
        fireEvent.click(screen.getByRole('button', {name: 'Export PDF'}));
        expect(onExport).toHaveBeenCalledWith(BERTHOUD, {sheet: true, dpi: 300, name: null});
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
