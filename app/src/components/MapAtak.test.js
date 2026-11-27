import React from 'react';
import {screen, waitFor} from '@testing-library/react';
import {mockFetch, renderWithProviders} from '../test-utils';
import {humanFileSize} from './Common';
import {httpMapSourceUrl, httpsMapSourceUrl, MapAtak} from './MapAtak';

const STATUS = {
    renderer: true,
    processes: 2,
    max_zoom: 17,
    maps: ['/opt/wrolpi-blobs/map-overview.pmtiles', '/media/wrolpi/map/mexico.pmtiles'],
    style_id: 'abc',
    queued_blocks: 3,
    drawing_blocks: 2,
    tiles_per_second: 31.5,
    block_ms: 310,
    cache: {enabled: true, bytes: 25 * 1024 * 1024, max_bytes: 1024 * 1024 * 1024},
    stats: {},
    clients: [{client: '192.0.2.34', tiles: 578, first_seen: 0, last_seen: Date.now() / 1000 - 30, queued_blocks: 0}],
};

describe('MapAtak', () => {
    const realFetch = global.fetch;
    afterEach(() => {
        global.fetch = realFetch;
    });

    it('builds the map source addresses from how the browser reached this WROLPi', () => {
        expect(httpMapSourceUrl('192.0.2.8')).toBe('http://192.0.2.8:8088/tiles/wrolpi.xml');
        expect(httpsMapSourceUrl('https://wrolpi.local')).toBe('https://wrolpi.local/tiles/wrolpi.xml');
    });

    it('shows the map sources and what the tile service is doing', async () => {
        global.fetch = mockFetch(STATUS);
        renderWithProviders(<MapAtak/>);

        expect(screen.getByText(httpMapSourceUrl())).toHaveAttribute('href', httpMapSourceUrl());
        expect(screen.getByText(httpsMapSourceUrl())).toHaveAttribute('href', httpsMapSourceUrl());
        expect(screen.getByText("this WROLPi's certificate")).toHaveAttribute('href', '/ca.crt');

        expect(await screen.findByText('31.5 per second (last minute)')).toBeInTheDocument();
        expect(global.fetch).toHaveBeenCalledWith('/tiles/status');
        expect(screen.getByText('5 blocks of 16 tiles')).toBeInTheDocument();
        expect(screen.getByText(`${humanFileSize(25 * 1024 * 1024)} of ${humanFileSize(1024 * 1024 * 1024)}`))
            .toBeInTheDocument();
        expect(screen.getByText('192.0.2.34')).toBeInTheDocument();
        expect(screen.getByText('578')).toBeInTheDocument();
        expect(screen.getByText('30s ago')).toBeInTheDocument();
    });

    it('says when the tile service is not running', async () => {
        global.fetch = jest.fn(() => Promise.reject(new Error('connection refused')));
        renderWithProviders(<MapAtak/>);
        expect(await screen.findByText(/The tile service is not running/)).toBeInTheDocument();
    });

    it('says when there are no map files', async () => {
        global.fetch = mockFetch({...STATUS, maps: [], clients: []});
        renderWithProviders(<MapAtak/>);
        expect(await screen.findByText(/There are no map files/)).toBeInTheDocument();
        expect(screen.getByText('No phone has asked for tiles.')).toBeInTheDocument();
    });

    it('polls the status while open', async () => {
        jest.useFakeTimers();
        try {
            global.fetch = mockFetch(STATUS);
            const {unmount} = renderWithProviders(<MapAtak/>);
            await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(1));
            jest.advanceTimersByTime(5000);
            await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2));
            unmount();
            jest.advanceTimersByTime(20000);
            expect(global.fetch).toHaveBeenCalledTimes(2);
        } finally {
            jest.useRealTimers();
        }
    });
});
