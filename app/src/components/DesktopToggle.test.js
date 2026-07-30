import React from 'react';
import {render, screen} from '../test-utils';
import userEvent from '@testing-library/user-event';
import {DesktopToggle} from './Common';

const mockSetDesktop = jest.fn();
let mockDesktopState = {on: true};

jest.mock('../hooks/customHooks', () => ({
    ...jest.requireActual('../hooks/customHooks'),
    useDesktop: () => ({...mockDesktopState, setDesktop: mockSetDesktop}),
}));

describe('DesktopToggle', () => {
    beforeEach(() => {
        mockSetDesktop.mockClear();
        mockDesktopState = {on: true};
    });

    it('renders checked when the desktop is running', () => {
        render(<DesktopToggle/>);
        expect(screen.getByTestId('toggle')).toBeChecked();
    });

    it('starts the desktop immediately when toggled on', async () => {
        mockDesktopState = {on: false};
        render(<DesktopToggle/>);
        await userEvent.click(screen.getByTestId('toggle'));
        expect(mockSetDesktop).toHaveBeenCalledWith(true);
    });

    it('asks for confirmation before stopping the desktop', async () => {
        render(<DesktopToggle/>);
        await userEvent.click(screen.getByTestId('toggle'));
        // Not stopped yet; the Confirm modal is shown instead.
        expect(mockSetDesktop).not.toHaveBeenCalled();
        // Mantine's Modal mounts its content on a subsequent render pass, so the
        // text isn't present synchronously after the click.
        expect(await screen.findByText('Stop the desktop')).toBeInTheDocument();

        await userEvent.click(screen.getByText('Stop'));
        expect(mockSetDesktop).toHaveBeenCalledWith(false);
    });

    it('cancelling the confirmation leaves the desktop running', async () => {
        render(<DesktopToggle/>);
        await userEvent.click(screen.getByTestId('toggle'));
        await userEvent.click(await screen.findByText('Cancel'));
        expect(mockSetDesktop).not.toHaveBeenCalled();
        expect(screen.getByTestId('toggle')).toBeChecked();
    });

    it('does nothing when the desktop is not supported', async () => {
        mockDesktopState = {on: null};
        render(<DesktopToggle/>);
        await userEvent.click(screen.getByTestId('toggle'));
        expect(mockSetDesktop).not.toHaveBeenCalled();
        expect(screen.queryByText('Stop the desktop')).not.toBeInTheDocument();
    });
});
