import React from "react";
import {getByTestId, render, screen} from '@testing-library/react';
import {DisableDownloadsToggle} from "./Common";
import {StatusContext} from "../contexts/contexts";
import {startDownloads} from "../components/Common";

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
