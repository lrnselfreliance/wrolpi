import React from "react";
import {getByTestId, queryByTestId, render, screen} from '@testing-library/react';
import {CPUTemperatureIcon, DisableDownloadsToggle} from "./Common";
import {StatusContext} from "../contexts/contexts";
import {startDownloads} from "../components/Common";
import {BrowserRouter} from "react-router-dom";

const mockedUseHref = jest.fn();

jest.mock("react-router-dom", () => ({
    ...(jest.requireActual("react-router-dom")),
    useHref: () => mockedUseHref
}));

test('DownloadsToggle is off when loading', async () => {
    const statusValue = {status: null, fetchStatus: null};
    const {container} = render(<StatusContext.Provider value={statusValue}>
        <DisableDownloadsToggle/>
    </StatusContext.Provider>);

    let toggle = screen.getByRole('checkbox');
    expect(toggle).not.toBeChecked();
    // Disabled while loading.
    expect(toggle).toHaveClass('disabled');
    // Text is "disabled" when downloading is On.
    const label = getByTestId(container, 'toggle-label');
    expect(label).toHaveTextContent('Downloading Disabled');
});

test('DownloadsToggle is off if downloading is Off', async () => {
    const statusValue = {
        status: {downloads: {disabled: true, stopped: true}},
        fetchStatus: null,
    }
    const {container} = render(<StatusContext.Provider value={statusValue}>
        <DisableDownloadsToggle/>
    </StatusContext.Provider>);

    const toggle = screen.getByRole('checkbox');
    expect(toggle).not.toBeChecked();
    // Not disabled when loaded.
    expect(toggle).not.toHaveClass('disabled');
    // Text is "disabled" when downloading is On.
    const label = getByTestId(container, 'toggle-label');
    expect(label).toHaveTextContent('Downloading Disabled');
});

test('DownloadsToggle is on if downloading is On', async () => {
    const statusValue = {
        status: {downloads: {disabled: false, stopped: false}},
        fetchStatus: null,
    }
    const {container} = render(<StatusContext.Provider value={statusValue}>
        <DisableDownloadsToggle/>
    </StatusContext.Provider>);

    const toggle = screen.getByRole('checkbox');
    expect(toggle).toBeChecked();
    // Not disabled when loaded.
    expect(toggle).not.toHaveClass('disabled');
    // Text is "enabled" when downloading is On.
    const label = getByTestId(container, 'toggle-label');
    expect(label).toHaveTextContent('Downloading Enabled');
});

test('CPUTemperatureIcon high', async () => {
    const statusValue = {status: {cpu_info: {temperature: 80, high_temperature: 75, critical_temperature: 90}}};
    const {container} = render(<StatusContext.Provider value={statusValue}>
        <BrowserRouter>
            <CPUTemperatureIcon/>
        </BrowserRouter>
    </StatusContext.Provider>);

    const icon = getByTestId(container, 'cpuTemperatureIcon');
    expect(icon).toHaveClass('thermometer');
    expect(icon).toHaveClass('half');
});

test('CPUTemperatureIcon critical', async () => {
    const statusValue = {status: {cpu_info: {temperature: 100, high_temperature: 75, critical_temperature: 90}}};
    const {container} = render(<StatusContext.Provider value={statusValue}>
        <BrowserRouter>
            <CPUTemperatureIcon/>
        </BrowserRouter>
    </StatusContext.Provider>);

    const icon = getByTestId(container, 'cpuTemperatureIcon');
    expect(icon).toHaveClass('thermometer');
    expect(icon).not.toHaveClass('half');
});

test('CPUTemperatureIcon hidden', async () => {
    const statusValue = {status: {cpu_info: {temperature: 35, high_temperature: 75, critical_temperature: 90}}};
    const {container} = render(<StatusContext.Provider value={statusValue}>
        <CPUTemperatureIcon/>
    </StatusContext.Provider>);

    const icon = queryByTestId(container, 'cpuTemperatureIcon');
    expect(icon).toBeNull();
});