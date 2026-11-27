import React from 'react';
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {MantineProvider} from '@mantine/core';
import {cssVariablesResolver, mantineTheme} from '../../themes/mantine';
import {VpnSection} from './VpnSection';
import {
    deleteVpnConfig,
    getVpnSettings,
    getVpnStatus,
    saveVpnAuth,
    updateVpnSettings,
    uploadVpnConfig,
} from '../../api/controller';
import {toast} from '../ui';

jest.mock('../../api/controller', () => ({
    getVpnSettings: jest.fn(),
    getVpnStatus: jest.fn(),
    updateVpnSettings: jest.fn(),
    uploadVpnConfig: jest.fn(),
    deleteVpnConfig: jest.fn(),
    saveVpnAuth: jest.fn(),
}));

// Toasts render through Mantine notifications, which the test providers do not include.
jest.mock('../ui', () => ({
    ...jest.requireActual('../ui'),
    toast: jest.fn(),
}));

const noConfig = {
    enabled: false, kind: null, servers: [], needs_auth: false, has_auth: false,
    port_forwarding: 'none', forwarded_port: null, public_ip_url: 'https://api.ipify.org',
};
const wireguard = {...noConfig, kind: 'wireguard', servers: ['vpn.example.com']};
const openvpn = {...noConfig, kind: 'openvpn', servers: ['198.51.100.7'], needs_auth: true};
const stopped = {enabled: false, state: 'stopped', port_forwarding: 'none', warnings: []};

const renderSection = () => render(
    <MantineProvider theme={mantineTheme} cssVariablesResolver={cssVariablesResolver}>
        <VpnSection/>
    </MantineProvider>
);

describe('VpnSection', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        getVpnSettings.mockResolvedValue(noConfig);
        getVpnStatus.mockResolvedValue(stopped);
    });

    test('says torrents stop when the VPN is down', async () => {
        renderSection();
        expect(await screen.findByText(/never fall back/)).toBeInTheDocument();
        expect(await screen.findByText('Upload VPN Config')).toBeInTheDocument();
        // Nothing to turn on until a config is uploaded.
        expect(screen.getByLabelText('Turn on the VPN')).toBeDisabled();
    });

    test('shows the address peers see while connected', async () => {
        getVpnSettings.mockResolvedValue({...wireguard, enabled: true, port_forwarding: 'fixed', forwarded_port: 51413});
        getVpnStatus.mockResolvedValue({
            enabled: true, state: 'connected', public_ip: '203.0.113.99', forwarded_port: 51413, warnings: []});
        renderSection();
        const status = await screen.findByTestId('vpn-status');
        await waitFor(() => expect(status).toHaveTextContent('Connected'));
        expect(status).toHaveTextContent('Peers see 203.0.113.99');
        expect(status).toHaveTextContent('Port 51413');
        expect(screen.getByText(/WireGuard/)).toBeInTheDocument();
        expect(screen.getByLabelText('Turn on the VPN')).toBeChecked();
    });

    test('shows why the tunnel is down', async () => {
        getVpnStatus.mockResolvedValue({...stopped, state: 'error', error: 'wg setconf failed: Invalid key'});
        renderSection();
        expect(await screen.findByText('wg setconf failed: Invalid key')).toBeInTheDocument();
    });

    test('uploads the chosen config file', async () => {
        uploadVpnConfig.mockResolvedValue(wireguard);
        renderSection();
        await screen.findByText('Upload VPN Config');
        const file = new File(['[Interface]\n'], 'proton.conf', {type: 'text/plain'});
        file.text = () => Promise.resolve('[Interface]\n');
        fireEvent.change(screen.getByTestId('vpn-config-file'), {target: {files: [file]}});
        await waitFor(() => expect(uploadVpnConfig).toHaveBeenCalledWith('proton.conf', '[Interface]\n'));
        expect(await screen.findByText('Replace VPN Config')).toBeInTheDocument();
    });

    test('a refused upload is shown to the user', async () => {
        uploadVpnConfig.mockRejectedValue(new Error('The WireGuard config has no PrivateKey'));
        renderSection();
        await screen.findByText('Upload VPN Config');
        const file = new File(['x'], 'bad.conf');
        file.text = () => Promise.resolve('x');
        fireEvent.change(screen.getByTestId('vpn-config-file'), {target: {files: [file]}});
        await waitFor(() => expect(toast).toHaveBeenCalledWith(
            expect.objectContaining({type: 'error', description: 'The WireGuard config has no PrivateKey'})));
    });

    test('an OpenVPN config asks for the login, which is cleared once saved', async () => {
        getVpnSettings.mockResolvedValue(openvpn);
        saveVpnAuth.mockResolvedValue({...openvpn, has_auth: true});
        renderSection();
        const username = await screen.findByLabelText('VPN Username');
        fireEvent.change(username, {target: {value: 'user'}});
        fireEvent.change(screen.getByLabelText('VPN Password'), {target: {value: 'secret'}});
        fireEvent.click(screen.getByText('Save Login'));
        await waitFor(() => expect(saveVpnAuth).toHaveBeenCalledWith('user', 'secret'));
        await waitFor(() => expect(username).toHaveValue(''));
        expect(await screen.findByText(/\(saved\)/)).toBeInTheDocument();
    });

    test('a fixed forwarded port is sent with the settings', async () => {
        getVpnSettings.mockResolvedValue({...wireguard, port_forwarding: 'fixed', forwarded_port: 51413});
        updateVpnSettings.mockResolvedValue({...wireguard, port_forwarding: 'fixed', forwarded_port: 51414});
        renderSection();
        const port = await screen.findByLabelText('Forwarded port');
        expect(port).toHaveValue('51413');
        fireEvent.change(port, {target: {value: '51414'}});
        fireEvent.click(screen.getByText('Save'));
        await waitFor(() => expect(updateVpnSettings).toHaveBeenCalledWith(
            {port_forwarding: 'fixed', forwarded_port: 51414}));
    });

    test('NAT-PMP asks for no port, and shows the one the VPN forwards', async () => {
        getVpnSettings.mockResolvedValue({...wireguard, enabled: true, port_forwarding: 'natpmp'});
        getVpnStatus.mockResolvedValue({
            enabled: true, state: 'connected', public_ip: '203.0.113.99', forwarded_port: 51413, warnings: []});
        updateVpnSettings.mockResolvedValue({...wireguard, enabled: true, port_forwarding: 'natpmp'});
        renderSection();
        const status = await screen.findByTestId('vpn-status');
        await waitFor(() => expect(status).toHaveTextContent('Port 51413'));
        expect(screen.queryByLabelText('Forwarded port')).not.toBeInTheDocument();
        fireEvent.click(screen.getByText('Save'));
        await waitFor(() => expect(updateVpnSettings).toHaveBeenCalledWith(
            {port_forwarding: 'natpmp', forwarded_port: null}));
    });

    test('a VPN which will not forward a port says why', async () => {
        getVpnSettings.mockResolvedValue({...wireguard, enabled: true, port_forwarding: 'natpmp'});
        getVpnStatus.mockResolvedValue({enabled: true, state: 'connected', public_ip: '203.0.113.99',
            forwarded_port: null, warnings: ['The VPN (10.2.0.1) did not answer a port forwarding request.']});
        renderSection();
        expect(await screen.findByText(/did not answer a port forwarding request/)).toBeInTheDocument();
    });

    test('turning the VPN on', async () => {
        getVpnSettings.mockResolvedValue(wireguard);
        updateVpnSettings.mockResolvedValue({...wireguard, enabled: true});
        renderSection();
        const toggle = await screen.findByLabelText('Turn on the VPN');
        await waitFor(() => expect(toggle).toBeEnabled());
        fireEvent.click(toggle);
        await waitFor(() => expect(updateVpnSettings).toHaveBeenCalledWith({enabled: true}));
        await waitFor(() => expect(toggle).toBeChecked());
    });

    test('removing the config asks first', async () => {
        getVpnSettings.mockResolvedValue(wireguard);
        deleteVpnConfig.mockResolvedValue(noConfig);
        renderSection();
        fireEvent.click(await screen.findByText('Remove'));
        expect(deleteVpnConfig).not.toHaveBeenCalled();
        // The Confirm modal is portaled; scope the query to the dialog.
        const dialog = await screen.findByRole('dialog');
        expect(dialog).toHaveTextContent('Torrents will stop');
        fireEvent.click(within(dialog).getByText('Remove'));
        await waitFor(() => expect(deleteVpnConfig).toHaveBeenCalled());
    });
});
