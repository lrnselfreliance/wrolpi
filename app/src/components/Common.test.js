import React from "react";
import {getByTestId, render, screen} from '@testing-library/react';
import {DisableDownloadsToggle} from "./Common";
import {useDownloaders} from "../hooks/customHooks";
import user from '@testing-library/user-event';

jest.mock('../hooks/customHooks', () => ({useDownloaders: jest.fn()}));

test('DownloadsToggle is off when loading', async () => {
    useDownloaders.mockImplementation(() => ({on: null}));

    const {container} = render(<DisableDownloadsToggle/>);
    let toggle = screen.getByRole('checkbox');
    expect(toggle).not.toBeChecked();
    // Disabled while loading.
    expect(toggle).toHaveClass('disabled');
    // Text is "disabled" when downloading is On.
    const label = getByTestId(container, 'toggle-label');
    expect(label).toHaveTextContent('Downloading Disabled');
});

test('DownloadsToggle is off if downloading is Off', async () => {
    useDownloaders.mockImplementation(() => ({on: false}));

    const {container} = render(<DisableDownloadsToggle/>);
    const toggle = screen.getByRole('checkbox');
    expect(toggle).not.toBeChecked();
    // Not disabled when loaded.
    expect(toggle).not.toHaveClass('disabled');
    // Text is "disabled" when downloading is On.
    const label = getByTestId(container, 'toggle-label');
    expect(label).toHaveTextContent('Downloading Disabled');
});

test('DownloadsToggle is on if downloading is On', async () => {
    useDownloaders.mockImplementation(() => ({on: true}));

    const {container} = render(<DisableDownloadsToggle/>);
    const toggle = screen.getByRole('checkbox');
    expect(toggle).toBeChecked();
    // Not disabled when loaded.
    expect(toggle).not.toHaveClass('disabled');
    // Text is "enabled" when downloading is On.
    const label = getByTestId(container, 'toggle-label');
    expect(label).toHaveTextContent('Downloading Enabled');
});

test('DownloadsToggle click', async () => {
    const mock = jest.fn();
    useDownloaders.mockImplementation(() => ({on: true, setDownloads: mock}));
    render(<DisableDownloadsToggle/>);

    // Downloads is toggled when DownloadsToggle is clicked.
    const toggle = screen.getByRole('checkbox');
    user.click(toggle);
    expect(mock).toHaveBeenCalled();
    expect(mock).toHaveBeenLastCalledWith(false);
})
