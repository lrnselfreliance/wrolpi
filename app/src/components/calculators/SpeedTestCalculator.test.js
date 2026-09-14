import React from "react";
import {act, fireEvent, screen, waitFor} from "@testing-library/react";
import {renderWithProviders} from "../../test-utils";
import {ConnectionContext, SpeedTestCalculator, StreamCapacity} from "./SpeedTestCalculator";
import * as speedtest from "./speedtest";

jest.mock('./speedtest', () => {
    const actual = jest.requireActual('./speedtest');
    return {
        ...actual,
        fetchInfo: jest.fn(),
        runPing: jest.fn(),
        runDownload: jest.fn(),
        runUpload: jest.fn(),
    };
});

const deferred = () => {
    let resolve;
    const promise = new Promise(r => {
        resolve = r;
    });
    return {promise, resolve};
};

beforeEach(() => {
    jest.clearAllMocks();
    speedtest.fetchInfo.mockResolvedValue({client_ip: '10.0.0.50', active_tests: 0});
    speedtest.runPing.mockResolvedValue({min: 4, median: 6, jitter: 1.5, lost: 0});
    speedtest.runDownload.mockResolvedValue({mbps: 87.5, peak: 95, bytes: 1e8, samples: []});
    speedtest.runUpload.mockResolvedValue({mbps: 21.2, peak: 25, bytes: 3e7, samples: []});
});

describe('SpeedTestCalculator', () => {
    test('idle state shows Start and no results', () => {
        renderWithProviders(<SpeedTestCalculator/>);
        expect(screen.getByRole('button', {name: /start test/i})).toBeInTheDocument();
        expect(screen.getByTestId('speedtest-phase')).toHaveTextContent('Ready');
        expect(screen.queryByTestId('speedtest-results')).not.toBeInTheDocument();
    });

    test('runs ping, download, upload in order and shows results and stream capacity', async () => {
        renderWithProviders(<SpeedTestCalculator/>);
        fireEvent.click(screen.getByRole('button', {name: /start test/i}));

        await waitFor(() => expect(screen.getByTestId('speedtest-phase')).toHaveTextContent('Complete'));

        expect(speedtest.runPing).toHaveBeenCalledTimes(1);
        expect(speedtest.runDownload).toHaveBeenCalledTimes(1);
        expect(speedtest.runUpload).toHaveBeenCalledTimes(1);
        // Order: ping before download before upload.
        expect(speedtest.runPing.mock.invocationCallOrder[0])
            .toBeLessThan(speedtest.runDownload.mock.invocationCallOrder[0]);
        expect(speedtest.runDownload.mock.invocationCallOrder[0])
            .toBeLessThan(speedtest.runUpload.mock.invocationCallOrder[0]);

        const results = screen.getByTestId('speedtest-results');
        expect(results).toHaveTextContent('87.5 Mbps');
        expect(results).toHaveTextContent('21.2 Mbps');
        expect(results).toHaveTextContent('6.0 ms');

        // 87.5 Mbps: 35 SD, 17 HD, 10 Full HD, 5 2K, 3 4K streams.
        const capacity = screen.getByTestId('speedtest-capacity');
        const cells = Array.from(capacity.querySelectorAll('tbody td:last-child')).map(td => td.textContent);
        expect(cells).toEqual(['35', '17', '10', '5', '3']);

        expect(screen.getByTestId('speedtest-context')).toHaveTextContent('10.0.0.50');
        expect(screen.getByTestId('speedtest-context')).toHaveTextContent('via LAN');
        expect(screen.getByRole('button', {name: /run again/i})).toBeInTheDocument();
    });

    test('Start becomes Cancel before the first await resolves, so a second run cannot be started', async () => {
        // Hold the first await so Start is clicked again before the ping phase begins.
        const pending = deferred();
        speedtest.fetchInfo.mockImplementation(() => pending.promise);
        renderWithProviders(<SpeedTestCalculator/>);
        fireEvent.click(screen.getByRole('button', {name: /start test/i}));
        // The button has already become Cancel, and a stray click on it is the abort path,
        // so hunt for any Start/Run again button and click it if one exists.
        expect(screen.queryByRole('button', {name: /start test|run again/i})).toBeNull();
        expect(screen.getByTestId('speedtest-phase')).toHaveTextContent('Connecting');

        pending.resolve({client_ip: '10.0.0.50', active_tests: 0});
        await waitFor(() => expect(screen.getByTestId('speedtest-phase')).toHaveTextContent('Complete'));
        expect(speedtest.fetchInfo).toHaveBeenCalledTimes(1);
        expect(speedtest.runPing).toHaveBeenCalledTimes(1);
    });

    test('Cancel aborts the run and shows no results for unfinished phases', async () => {
        const pending = deferred();
        speedtest.runDownload.mockImplementation(({signal}) => new Promise((resolve, reject) => {
            signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
            pending.promise.then(resolve);
        }));
        renderWithProviders(<SpeedTestCalculator/>);
        fireEvent.click(screen.getByRole('button', {name: /start test/i}));

        await waitFor(() => expect(screen.getByTestId('speedtest-phase')).toHaveTextContent('Downloading'));
        const {signal} = speedtest.runDownload.mock.calls[0][0];
        fireEvent.click(screen.getByRole('button', {name: /cancel/i}));

        expect(signal.aborted).toBe(true);
        await waitFor(() => expect(screen.getByTestId('speedtest-phase')).toHaveTextContent('Cancelled'));
        expect(speedtest.runUpload).not.toHaveBeenCalled();
        // Ping finished before the cancel, so it is shown; download is not.
        expect(screen.getByTestId('speedtest-results')).toHaveTextContent('Ping');
        expect(screen.getByTestId('speedtest-results')).not.toHaveTextContent('Download');
    });

    test('an unreachable API is reported', async () => {
        speedtest.fetchInfo.mockRejectedValue(new Error('HTTP 502'));
        renderWithProviders(<SpeedTestCalculator/>);
        fireEvent.click(screen.getByRole('button', {name: /start test/i}));
        await waitFor(() => expect(screen.getByTestId('speedtest-phase')).toHaveTextContent('Failed'));
        expect(screen.getByText(/could not be reached/i)).toBeInTheDocument();
        expect(speedtest.runPing).not.toHaveBeenCalled();
    });

    test('a failing download phase is reported', async () => {
        speedtest.runDownload.mockRejectedValue(new Error('Download test failed: HTTP 500'));
        renderWithProviders(<SpeedTestCalculator/>);
        fireEvent.click(screen.getByRole('button', {name: /start test/i}));
        await waitFor(() => expect(screen.getByTestId('speedtest-phase')).toHaveTextContent('Failed'));
        expect(screen.getByText(/HTTP 500/)).toBeInTheDocument();
    });
});

describe('ConnectionContext', () => {
    test('hotspot badge needs both a hotspot address and the hotspot to be up', () => {
        const {rerender} = renderWithProviders(
            <ConnectionContext info={{client_ip: '10.42.0.7', active_tests: 0}} hotspotConnected={true} others={0}/>);
        expect(screen.getByTestId('speedtest-context')).toHaveTextContent('via WROLPi hotspot');

        rerender(<ConnectionContext info={{client_ip: '10.42.0.7', active_tests: 0}} hotspotConnected={false} others={0}/>);
        expect(screen.getByTestId('speedtest-context')).toHaveTextContent('via LAN');

        rerender(<ConnectionContext info={{client_ip: '192.168.1.9', active_tests: 0}} hotspotConnected={true} others={0}/>);
        expect(screen.getByTestId('speedtest-context')).toHaveTextContent('via LAN');
    });

    test('mentions concurrent tests', () => {
        renderWithProviders(<ConnectionContext info={{client_ip: '10.0.0.5'}} hotspotConnected={false} others={2}/>);
        expect(screen.getByTestId('speedtest-context')).toHaveTextContent('2 other speed tests were running');
    });

    test('renders nothing without info', () => {
        const {container} = renderWithProviders(<ConnectionContext info={null} hotspotConnected={false} others={0}/>);
        expect(container.querySelector('[data-testid="speedtest-context"]')).toBeNull();
    });
});

describe('StreamCapacity', () => {
    test('shows every tier with the disk caveat', () => {
        renderWithProviders(<StreamCapacity mbps={8}/>);
        expect(screen.getByText('1080p (Full HD)')).toBeInTheDocument();
        expect(screen.getByText(/served from the drive/i)).toBeInTheDocument();
    });
});
