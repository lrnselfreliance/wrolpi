import React from 'react';
import {render, screen} from '../test-utils';
import userEvent from '@testing-library/user-event';
import {VncToggle} from './Common';

const mockSetVnc = jest.fn();
let mockVncState = {on: false, desktopRunning: true};

jest.mock('../hooks/customHooks', () => ({
    ...jest.requireActual('../hooks/customHooks'),
    useVnc: () => ({...mockVncState, setVnc: mockSetVnc}),
}));

describe('VncToggle', () => {
    beforeEach(() => {
        mockSetVnc.mockClear();
        mockVncState = {on: false, desktopRunning: true};
    });

    it('starts VNC when the Desktop is running', async () => {
        render(<VncToggle/>);
        const toggle = screen.getByTestId('toggle');
        expect(toggle).not.toBeDisabled();
        await userEvent.click(toggle);
        expect(mockSetVnc).toHaveBeenCalledWith(true);
    });

    it('is disabled while the Desktop is stopped', async () => {
        mockVncState = {on: false, desktopRunning: false};
        render(<VncToggle/>);
        await userEvent.click(screen.getByTestId('toggle'));
        expect(mockSetVnc).not.toHaveBeenCalled();
    });

    it('can always be stopped, even with the Desktop stopped', async () => {
        // Otherwise a running VNC server would be stranded on with no way to stop it.
        mockVncState = {on: true, desktopRunning: false};
        render(<VncToggle/>);
        const toggle = screen.getByTestId('toggle');
        expect(toggle).toBeChecked();
        await userEvent.click(toggle);
        expect(mockSetVnc).toHaveBeenCalledWith(false);
    });

    it('renders checked when VNC is running', () => {
        mockVncState = {on: true, desktopRunning: true};
        render(<VncToggle/>);
        expect(screen.getByTestId('toggle')).toBeChecked();
    });

    it('does nothing when VNC is unsupported', async () => {
        mockVncState = {on: null, desktopRunning: true};
        render(<VncToggle/>);
        await userEvent.click(screen.getByTestId('toggle'));
        expect(mockSetVnc).not.toHaveBeenCalled();
    });
});
