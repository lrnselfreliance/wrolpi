import React from 'react';
import {Button, Checkbox, Confirm, Group, Header, Message, Panel, Select, Status, TextInput, toast} from "../ui";
import {
    deleteVpnConfig,
    getVpnSettings,
    getVpnStatus,
    saveVpnAuth,
    updateVpnSettings,
    uploadVpnConfig,
} from "../../api/controller";

// The tunnel reports one of these states; torrents only reach the Internet while connected.
export const vpnStates = {
    connected: {label: 'Connected', kind: 'complete'},
    connecting: {label: 'Connecting', kind: 'active'},
    waiting: {label: 'Waiting', kind: 'pending'},
    disabled: {label: 'Off', kind: 'pending'},
    stopped: {label: 'Not running', kind: 'pending'},
    error: {label: 'Error', kind: 'failed'},
};

const kindLabels = {wireguard: 'WireGuard', openvpn: 'OpenVPN'};

const portForwardingOptions = [
    {value: 'none', label: 'None (download only; seed to peers who accept connections)'},
    {value: 'fixed', label: 'A port my VPN provider forwards to me'},
];

const STATUS_INTERVAL_MS = 10000;

export function VpnSection() {
    const [settings, setSettings] = React.useState(null);
    const [status, setStatus] = React.useState(null);
    const [form, setForm] = React.useState({port_forwarding: 'none', forwarded_port: ''});
    const [login, setLogin] = React.useState({username: '', password: ''});
    const [saving, setSaving] = React.useState(false);
    const [deleteOpen, setDeleteOpen] = React.useState(false);
    const fileInput = React.useRef(null);

    const applySettings = (newSettings) => {
        setSettings(newSettings);
        setForm({
            port_forwarding: newSettings.port_forwarding || 'none',
            forwarded_port: newSettings.forwarded_port ? String(newSettings.forwarded_port) : '',
        });
    };

    React.useEffect(() => {
        getVpnSettings()
            .then(applySettings)
            .catch(e => console.error('Failed to fetch VPN settings', e));
    }, []);

    React.useEffect(() => {
        let cancelled = false;
        const fetchStatus = async () => {
            try {
                const newStatus = await getVpnStatus();
                if (!cancelled) {
                    setStatus(newStatus);
                }
            } catch (e) {
                console.error('Failed to fetch VPN status', e);
            }
        };
        fetchStatus();
        const interval = setInterval(fetchStatus, STATUS_INTERVAL_MS);
        return () => {
            cancelled = true;
            clearInterval(interval);
        };
    }, []);

    // Returns whether the change was saved.
    const run = async (action, successTitle) => {
        setSaving(true);
        try {
            applySettings(await action());
            if (successTitle) {
                toast({type: 'success', title: successTitle, time: 3000});
            }
        } catch (e) {
            toast({type: 'error', title: 'VPN', description: e.message, time: 6000});
            return false;
        } finally {
            setSaving(false);
        }
        try {
            setStatus(await getVpnStatus());
        } catch (e) {
            console.error('Failed to fetch VPN status', e);
        }
        return true;
    };

    const handleFile = async (event) => {
        const file = event.target.files && event.target.files[0];
        event.target.value = '';
        if (!file) {
            return;
        }
        const content = await file.text();
        await run(() => uploadVpnConfig(file.name, content), 'VPN config saved');
    };

    const handleSave = () => run(() => updateVpnSettings({
        port_forwarding: form.port_forwarding,
        forwarded_port: form.port_forwarding === 'fixed' && form.forwarded_port
            ? parseInt(form.forwarded_port, 10) : null,
    }), 'VPN settings saved');

    const handleEnabled = (enabled) => run(() => updateVpnSettings({enabled}));

    const handleLogin = async () => {
        if (await run(() => saveVpnAuth(login.username, login.password), 'VPN login saved')) {
            setLogin({username: '', password: ''});
        }
    };

    const handleDelete = () => {
        setDeleteOpen(false);
        return run(deleteVpnConfig, 'VPN config removed');
    };

    const state = vpnStates[status && status.state] || vpnStates.stopped;
    const hasConfig = settings && settings.kind;

    return <Panel>
        <Header as='h3' icon='lock'>VPN</Header>
        <p style={{marginTop: 0}}>
            Torrents only use this VPN, so peers never see this WROLPi's own address. When the VPN is down,
            torrents stop; they never fall back to this WROLPi's own Internet connection.
        </p>

        {status && <p data-testid='vpn-status'>
            <Status kind={state.kind}>{state.label}</Status>
            {status.public_ip && <> · Peers see <b>{status.public_ip}</b></>}
            {status.forwarded_port && <> · Port <b>{status.forwarded_port}</b></>}
        </p>}
        {status && status.error && <Message kind='warning'>{status.error}</Message>}
        {status && (status.warnings || []).map(warning => <Message key={warning} kind='warning'>{warning}</Message>)}

        <p>
            {hasConfig
                ? <>Config: <b>{kindLabels[settings.kind]}</b> to {settings.servers.join(', ')}</>
                : 'Upload the WireGuard (.conf) or OpenVPN (.ovpn) file from your VPN provider.'}
        </p>
        <input ref={fileInput} type='file' accept='.conf,.ovpn' style={{display: 'none'}}
               data-testid='vpn-config-file' onChange={handleFile}/>
        <div className='wrolpi-button-row'>
            <Button role='primary' loading={saving} onClick={() => fileInput.current && fileInput.current.click()}>
                {hasConfig ? 'Replace VPN Config' : 'Upload VPN Config'}
            </Button>
            {hasConfig && <Button role='danger' disabled={saving} onClick={() => setDeleteOpen(true)}>Remove</Button>}
        </div>

        {settings && settings.needs_auth && <>
            <p>This OpenVPN config needs your VPN login{settings.has_auth ? ' (saved)' : ''}.</p>
            <Group grow align='flex-start'>
                <TextInput label='VPN Username' value={login.username} disabled={saving}
                           onChange={e => setLogin({...login, username: e.target.value})}/>
                <TextInput label='VPN Password' type='password' value={login.password} disabled={saving}
                           onChange={e => setLogin({...login, password: e.target.value})}/>
            </Group>
            <Button mt='sm' role='save' disabled={saving || !login.username || !login.password}
                    onClick={handleLogin}>Save Login</Button>
        </>}

        <Group grow align='flex-start' mt='md'>
            <Select
                label='Port forwarding'
                data={portForwardingOptions}
                value={form.port_forwarding}
                disabled={saving}
                onChange={value => setForm({...form, port_forwarding: value})}
            />
            {form.port_forwarding === 'fixed' && <TextInput
                label='Forwarded port'
                inputMode='numeric'
                value={form.forwarded_port}
                disabled={saving}
                onChange={e => setForm({...form, forwarded_port: e.target.value.replace(/\D/g, '')})}
            />}
        </Group>
        <Button mt='sm' role='save' loading={saving} onClick={handleSave}>Save</Button>

        <Checkbox
            mt='md'
            label='Turn on the VPN'
            description='Torrents can only reach the Internet while the VPN is connected'
            checked={!!(settings && settings.enabled)}
            disabled={saving || !hasConfig}
            onChange={e => handleEnabled(e.currentTarget.checked)}
        />

        <Confirm
            open={deleteOpen}
            title='Remove VPN Config'
            confirmLabel='Remove'
            destructive
            onCancel={() => setDeleteOpen(false)}
            onConfirm={handleDelete}
        >
            Remove the VPN config and login, and turn the VPN off? Torrents will stop until a new config is uploaded.
        </Confirm>
    </Panel>;
}

export default VpnSection;
