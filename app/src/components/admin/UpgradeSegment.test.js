import React from 'react';
import {fireEvent, screen, waitFor} from '@testing-library/react';
import {render} from '../../test-utils';
import {UpgradeSegment} from './Settings';
import {triggerUpgrade} from '../../api';

jest.mock('../../api', () => ({
    ...jest.requireActual('../../api'),
    // Not ok, so the page does not navigate to the Controller.
    triggerUpgrade: jest.fn(() => Promise.resolve({ok: false})),
}));

const upToDate = {status: {update_available: false, version: '1.0', git_branch: 'feature'}, loaded: true};
const updateAvailable = {
    status: {update_available: true, version: '1.0', git_branch: 'release', commits_behind: 2},
    loaded: true,
};

const branchInput = () => screen.getByLabelText('Branch', {selector: 'input'});

const confirmUpgrade = async (buttonName) => {
    fireEvent.click(screen.getByRole('button', {name: buttonName}));
    fireEvent.click(await screen.findByRole('button', {name: 'Start Upgrade'}));
};

beforeEach(() => {
    triggerUpgrade.mockClear();
});

describe('UpgradeSegment branch picker', () => {
    test('starts on the current branch and lists it with master and release', async () => {
        render(<UpgradeSegment/>, {status: upToDate});
        expect(branchInput()).toHaveValue('feature');

        fireEvent.focus(branchInput());
        fireEvent.click(branchInput());
        const options = (await screen.findAllByRole('option')).map(i => i.textContent);
        expect(options).toEqual(['feature', 'master', 'release']);
    });

    test('an up to date branch offers no upgrade until another branch is chosen', async () => {
        render(<UpgradeSegment/>, {status: upToDate});
        expect(screen.queryByRole('button', {name: /^Upgrade/})).not.toBeInTheDocument();

        fireEvent.change(branchInput(), {target: {value: 'master'}});
        await confirmUpgrade('Upgrade to master');
        await waitFor(() => expect(triggerUpgrade).toHaveBeenCalledWith('master'));
    });

    test('a typed branch name is upgraded to', async () => {
        render(<UpgradeSegment/>, {status: updateAvailable});
        fireEvent.change(branchInput(), {target: {value: '  my-branch '}});
        await confirmUpgrade('Upgrade to my-branch');
        await waitFor(() => expect(triggerUpgrade).toHaveBeenCalledWith('my-branch'));
    });

    test('an available update upgrades the current branch by default', async () => {
        render(<UpgradeSegment/>, {status: updateAvailable});
        expect(branchInput()).toHaveValue('release');
        await confirmUpgrade('Upgrade Now');
        await waitFor(() => expect(triggerUpgrade).toHaveBeenCalledWith('release'));
    });
});
