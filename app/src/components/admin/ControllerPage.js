import React from 'react';
import {Container, Icon} from "semantic-ui-react";
import {Button, Header, Loader, Modal, Segment, Table} from "../Theme";
import {
    APIButton,
    HotspotToggle,
    ThrottleToggle,
    Toggle,
} from "../Common";
import {useDockerized} from "../../hooks/customHooks";
import {
    getServices,
    startService,
    stopService,
    restartService,
    enableService,
    disableService,
    getServiceLogs,
    getDisks,
    getMounts,
    getSmartStatus,
    getZfsPools,
    restartServices,
} from "../../api/controller";
import {toast} from "react-semantic-toasts-2";
import {getStatus, saveSettings} from "../../api";
import {RestartButton, ShutdownButton} from "./Settings";


// Service status color mapping
const statusColors = {
    running: 'green',
    stopped: 'red',
    failed: 'red',
    unknown: 'yellow',
};


function ServiceRow({service, onAction, dockerized}) {
    const [loading, setLoading] = React.useState(false);
    const [logsOpen, setLogsOpen] = React.useState(false);
    const [logs, setLogs] = React.useState('');
    const [logsLoading, setLogsLoading] = React.useState(false);

    const handleAction = async (action, actionFn) => {
        setLoading(true);
        try {
            await actionFn(service.name);
            toast({
                type: 'success',
                title: `${action} ${service.name}`,
                description: `Successfully ${action.toLowerCase()}ed ${service.name}`,
                time: 3000,
            });
            if (onAction) onAction();
        } catch (e) {
            toast({
                type: 'error',
                title: `${action} Failed`,
                description: e.message,
                time: 5000,
            });
        } finally {
            setLoading(false);
        }
    };

    const handleViewLogs = async () => {
        setLogsOpen(true);
        setLogsLoading(true);
        try {
            const result = await getServiceLogs(service.name, 100);
            setLogs(result.logs || 'No logs available');
        } catch (e) {
            setLogs(`Error fetching logs: ${e.message}`);
        } finally {
            setLogsLoading(false);
        }
    };

    const isRunning = service.status === 'running';
    const isStopped = service.status === 'stopped';
    const statusColor = statusColors[service.status] || 'grey';

    // Build view URL if service is viewable
    let viewUrl = null;
    if (service.viewable && service.port && isRunning) {
        const protocol = service.use_https ? 'https' : 'http';
        const host = window.location.hostname;
        const path = service.view_path || '';
        viewUrl = `${protocol}://${host}:${service.port}${path}`;
    }

    return (
        <Table.Row>
            <Table.Cell>
                <strong>{service.name}</strong>
                {service.description && <div style={{fontSize: '0.9em', color: '#888'}}>{service.description}</div>}
            </Table.Cell>
            <Table.Cell>{service.port || '-'}</Table.Cell>
            <Table.Cell>
                <Icon name='circle' color={statusColor}/>
                {service.status}
            </Table.Cell>
            <Table.Cell>
                {isRunning ? (
                    <Button
                        size='small'
                        icon='stop'
                        color='red'
                        disabled={loading}
                        loading={loading}
                        onClick={() => handleAction('Stop', stopService)}
                    />
                ) : (
                    <Button
                        size='small'
                        icon='play'
                        color='green'
                        disabled={loading}
                        loading={loading}
                        onClick={() => handleAction('Start', startService)}
                    />
                )}
                <Button
                    size='small'
                    icon='refresh'
                    color='blue'
                    disabled={loading}
                    loading={loading}
                    onClick={() => handleAction('Restart', restartService)}
                />
                <Modal
                    open={logsOpen}
                    onClose={() => setLogsOpen(false)}
                    onOpen={handleViewLogs}
                    trigger={<Button size='small' icon='file text' content='Logs'/>}
                    size='large'
                >
                    <Modal.Header>Logs: {service.name}</Modal.Header>
                    <Modal.Content scrolling>
                        {logsLoading ? (
                            <Loader active inline='centered'/>
                        ) : (
                            <pre style={{
                                whiteSpace: 'pre-wrap',
                                wordWrap: 'break-word',
                                maxHeight: '400px',
                                overflow: 'auto',
                                backgroundColor: '#1a1a1a',
                                color: '#00ff00',
                                padding: '1em',
                                fontFamily: 'monospace',
                                fontSize: '0.85em',
                            }}>
                                {logs}
                            </pre>
                        )}
                    </Modal.Content>
                    <Modal.Actions>
                        <Button onClick={() => setLogsOpen(false)}>Close</Button>
                    </Modal.Actions>
                </Modal>
                {viewUrl && (
                    <Button
                        size='small'
                        icon='external'
                        content='View'
                        as='a'
                        href={viewUrl}
                        target='_blank'
                        rel='noopener noreferrer'
                    />
                )}
            </Table.Cell>
            {!dockerized && (
                <Table.Cell>
                    <Toggle
                        checked={service.enabled === true}
                        disabled={service.enabled === null || loading}
                        onChange={async (checked) => {
                            if (checked) {
                                await handleAction('Enable', enableService);
                            } else {
                                await handleAction('Disable', disableService);
                            }
                        }}
                        label={service.enabled ? 'Enabled' : 'Disabled'}
                    />
                </Table.Cell>
            )}
        </Table.Row>
    );
}


function ServicesSection() {
    const [services, setServices] = React.useState([]);
    const [loading, setLoading] = React.useState(true);
    const [error, setError] = React.useState(null);
    const [restarting, setRestarting] = React.useState(false);
    const dockerized = useDockerized();

    const handleRestartServices = async () => {
        setRestarting(true);
        try {
            await restartServices();
            toast({
                type: 'success',
                title: 'Services Restarting',
                description: 'All WROLPi services are being restarted.',
                time: 5000,
            });
            // Refresh service list after restart initiated
            fetchServices();
        } catch (e) {
            toast({
                type: 'error',
                title: 'Restart Failed',
                description: e.message,
                time: 5000,
            });
        } finally {
            setRestarting(false);
        }
    };

    const fetchServices = async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await getServices();
            setServices(Array.isArray(result) ? result : []);
        } catch (e) {
            setError(e.message);
            setServices([]);
        } finally {
            setLoading(false);
        }
    };

    React.useEffect(() => {
        fetchServices();
        // Refresh every 10 seconds
        const interval = setInterval(fetchServices, 10000);
        return () => clearInterval(interval);
    }, []);

    if (loading && services.length === 0) {
        return <Segment>
            <Header as='h3'>Services</Header>
            <Loader active inline='centered'/>
        </Segment>;
    }

    if (error) {
        return <Segment>
            <Header as='h3'>Services</Header>
            <p style={{color: 'red'}}>Error loading services: {error}</p>
            <Button onClick={fetchServices}>Retry</Button>
        </Segment>;
    }

    return (
        <Segment>
            <Header as='h3'>
                <Icon name='server'/>
                Services
            </Header>
            <Table unstackable striped>
                <Table.Header>
                    <Table.Row>
                        <Table.HeaderCell>Service</Table.HeaderCell>
                        <Table.HeaderCell>Port</Table.HeaderCell>
                        <Table.HeaderCell>Status</Table.HeaderCell>
                        <Table.HeaderCell>Actions</Table.HeaderCell>
                        {!dockerized && <Table.HeaderCell>Boot</Table.HeaderCell>}
                    </Table.Row>
                </Table.Header>
                <Table.Body>
                    {services.map(service => (
                        <ServiceRow
                            dockerized={dockerized}
                            key={service.name}
                            service={service}
                            onAction={fetchServices}
                        />
                    ))}
                </Table.Body>
                <Table.Footer>
                    <Table.Row>
                        <Table.HeaderCell colSpan={dockerized ? 4 : 5}>
                            <APIButton
                                color='blue'
                                onClick={handleRestartServices}
                                confirmContent='Are you sure you want to restart all WROLPi services?'
                                confirmButton='Restart Services'
                                disabled={restarting}
                            >
                                <Icon name='refresh'/>
                                {restarting ? 'Restarting...' : 'Restart All Services'}
                            </APIButton>
                        </Table.HeaderCell>
                    </Table.Row>
                </Table.Footer>
            </Table>
            {services.length === 0 && (
                <p>No services found. Services may not be available in this environment.</p>
            )}
        </Segment>
    );
}


function DiskSection() {
    const [disks, setDisks] = React.useState([]);
    const [mounts, setMounts] = React.useState([]);
    const [smart, setSmart] = React.useState({});
    const [zfsPools, setZfsPools] = React.useState([]);
    const [loading, setLoading] = React.useState(true);
    const [error, setError] = React.useState(null);
    const dockerized = useDockerized();

    const fetchDiskInfo = async () => {
        setLoading(true);
        setError(null);
        try {
            const [disksResult, mountsResult, smartResult, zfsResult] = await Promise.allSettled([
                getDisks(),
                getMounts(),
                getSmartStatus(),
                getZfsPools(),
            ]);

            if (disksResult.status === 'fulfilled') {
                setDisks(Array.isArray(disksResult.value) ? disksResult.value : []);
            }
            if (mountsResult.status === 'fulfilled') {
                setMounts(Array.isArray(mountsResult.value) ? mountsResult.value : []);
            }
            if (smartResult.status === 'fulfilled') {
                setSmart(smartResult.value || {});
            }
            if (zfsResult.status === 'fulfilled') {
                setZfsPools(Array.isArray(zfsResult.value) ? zfsResult.value : []);
            }
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    React.useEffect(() => {
        fetchDiskInfo();
    }, []);

    if (dockerized) {
        return (
            <Segment>
                <Header as='h3'>
                    <Icon name='disk'/>
                    Disk Management
                </Header>
                <p>Disk management is not available in Docker environments.</p>
            </Segment>
        );
    }

    if (loading) {
        return <Segment>
            <Header as='h3'>Disk Management</Header>
            <Loader active inline='centered'/>
        </Segment>;
    }

    return (
        <Segment>
            <Header as='h3'>
                <Icon name='disk'/>
                Disk Management
            </Header>

            {error && <p style={{color: 'orange'}}>Some disk information unavailable: {error}</p>}

            <Header as='h4'>Current Mounts</Header>
            {mounts.length > 0 ? (
                <Table unstackable striped compact>
                    <Table.Header>
                        <Table.Row>
                            <Table.HeaderCell>Device</Table.HeaderCell>
                            <Table.HeaderCell>Mount Point</Table.HeaderCell>
                            <Table.HeaderCell>Filesystem</Table.HeaderCell>
                        </Table.Row>
                    </Table.Header>
                    <Table.Body>
                        {mounts.map((mount, idx) => (
                            <Table.Row key={idx}>
                                <Table.Cell>{mount.device}</Table.Cell>
                                <Table.Cell>{mount.mount_point}</Table.Cell>
                                <Table.Cell>{mount.fstype}</Table.Cell>
                            </Table.Row>
                        ))}
                    </Table.Body>
                </Table>
            ) : (
                <p>No mounts found.</p>
            )}

            {Object.keys(smart).length > 0 && (
                <>
                    <Header as='h4'>SMART Health</Header>
                    <Table unstackable striped compact>
                        <Table.Header>
                            <Table.Row>
                                <Table.HeaderCell>Device</Table.HeaderCell>
                                <Table.HeaderCell>Health</Table.HeaderCell>
                                <Table.HeaderCell>Temperature</Table.HeaderCell>
                            </Table.Row>
                        </Table.Header>
                        <Table.Body>
                            {Object.entries(smart).map(([device, info]) => (
                                <Table.Row key={device}>
                                    <Table.Cell>{device}</Table.Cell>
                                    <Table.Cell>
                                        <Icon
                                            name='circle'
                                            color={info.healthy ? 'green' : 'red'}
                                        />
                                        {info.healthy ? 'Healthy' : 'Warning'}
                                    </Table.Cell>
                                    <Table.Cell>
                                        {info.temperature ? `${info.temperature}°C` : '-'}
                                    </Table.Cell>
                                </Table.Row>
                            ))}
                        </Table.Body>
                    </Table>
                </>
            )}

            {zfsPools.length > 0 && (
                <>
                    <Header as='h4'>ZFS Pools</Header>
                    <Table unstackable striped compact>
                        <Table.Header>
                            <Table.Row>
                                <Table.HeaderCell>Pool</Table.HeaderCell>
                                <Table.HeaderCell>Health</Table.HeaderCell>
                                <Table.HeaderCell>Size</Table.HeaderCell>
                            </Table.Row>
                        </Table.Header>
                        <Table.Body>
                            {zfsPools.map((pool, idx) => (
                                <Table.Row key={idx}>
                                    <Table.Cell>{pool.name}</Table.Cell>
                                    <Table.Cell>
                                        <Icon
                                            name='circle'
                                            color={pool.health === 'ONLINE' ? 'green' : 'yellow'}
                                        />
                                        {pool.health}
                                    </Table.Cell>
                                    <Table.Cell>{pool.size || '-'}</Table.Cell>
                                </Table.Row>
                            ))}
                        </Table.Body>
                    </Table>
                </>
            )}

            <Button onClick={fetchDiskInfo} style={{marginTop: '1em'}}>
                <Icon name='refresh'/>
                Refresh
            </Button>
        </Segment>
    );
}


function AdminControlsSection() {
    const dockerized = useDockerized();

    return (
        <Segment>
            <Header as='h3'>
                <Icon name='settings'/>
                Hardware Controls
            </Header>

            <HotspotToggle/>
            <ThrottleToggle/>

            {!dockerized && (
                <div style={{marginTop: '1em'}}>
                    <RestartButton/>
                    <ShutdownButton/>
                </div>
            )}
        </Segment>
    );
}


function WROLModeSection() {
    const [wrolMode, setWrolMode] = React.useState(false);
    const [ready, setReady] = React.useState(false);

    React.useEffect(() => {
        const fetchWrolMode = async () => {
            try {
                const {wrol_mode} = await getStatus();
                setWrolMode(wrol_mode);
                setReady(true);
            } catch (e) {
                console.error('Failed to fetch WROL mode status:', e);
            }
        };
        fetchWrolMode();
    }, []);

    const toggleWROLMode = async (checked) => {
        try {
            await saveSettings({wrol_mode: checked});
            setWrolMode(checked);
        } catch (e) {
            toast({
                type: 'error',
                title: 'Failed to toggle WROL Mode',
                description: e.message,
                time: 5000,
            });
        }
    };

    if (!ready) {
        return <Segment>
            <Header as='h3'>WROL Mode</Header>
            <Loader active inline='centered'/>
        </Segment>;
    }

    return (
        <Segment>
            <Header as='h3'>
                <Icon name='shield'/>
                WROL Mode
            </Header>
            <p>
                Enable read-only mode. No content can be deleted or modified.
                Enable this when the SHTF and you want to prevent any potential loss of data.
            </p>
            <p style={{fontSize: '0.9em', color: '#888'}}>
                Note: User settings and tags can still be modified.
            </p>
            <Toggle
                checked={wrolMode}
                onChange={toggleWROLMode}
                label={wrolMode ? 'WROL Mode Enabled' : 'WROL Mode Disabled'}
            />
        </Segment>
    );
}


export function ControllerPage() {
    return (
        <Container fluid>
            <AdminControlsSection/>
            <ServicesSection/>
            <DiskSection/>
            <WROLModeSection/>
        </Container>
    );
}

export default ControllerPage;
