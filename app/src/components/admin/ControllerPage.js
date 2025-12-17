import React from 'react';
import {Container, Dropdown, Icon, Confirm, Input, Checkbox, Form} from "semantic-ui-react";
import {Button, Header, Loader, Modal, Segment, Table} from "../Theme";
import {
    APIButton,
    HotspotToggle,
    ThrottleToggle,
    Toggle,
} from "../Common";
import {useDockerized} from "../../hooks/customHooks";
import {Media} from "../../contexts/contexts";
import {
    getServices,
    startService,
    stopService,
    restartService,
    enableService,
    disableService,
    getServiceLogs,
    getDisks,
    getSmartStatus,
    restartServices,
    getFstabEntries,
    addFstabEntry,
    removeFstabEntry,
    mountDisk,
    unmountDisk,
} from "../../api/controller";
import {toast} from "react-semantic-toasts-2";
import {RestartButton, ShutdownButton} from "./Settings";


// Service status color mapping
const statusColors = {
    running: 'green',
    stopped: 'red',
    failed: 'red',
    unknown: 'yellow',
};


const linesOptions = [
    {key: 100, text: '100 lines', value: 100},
    {key: 250, text: '250 lines', value: 250},
    {key: 500, text: '500 lines', value: 500},
    {key: 1000, text: '1000 lines', value: 1000},
    {key: 5000, text: '5000 lines', value: 5000},
];

function ServiceRow({service, onAction, dockerized}) {
    const [loading, setLoading] = React.useState(false);
    const [logsOpen, setLogsOpen] = React.useState(false);
    const [logs, setLogs] = React.useState('');
    const [logsLoading, setLogsLoading] = React.useState(false);
    const [linesCount, setLinesCount] = React.useState(250);
    const [countdown, setCountdown] = React.useState(10);
    const logsRef = React.useRef(null);

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

    const fetchLogs = async (lines, showLoading = false) => {
        if (showLoading) setLogsLoading(true);
        try {
            const result = await getServiceLogs(service.name, lines);
            setLogs(result.logs || 'No logs available');
        } catch (e) {
            setLogs(`Error fetching logs: ${e.message}`);
        } finally {
            if (showLoading) setLogsLoading(false);
        }
    };

    // Scroll to bottom when logs finish loading
    React.useEffect(() => {
        if (!logsLoading && logsRef.current) {
            logsRef.current.scrollTop = logsRef.current.scrollHeight;
        }
    }, [logsLoading]);

    // Auto-refresh countdown timer (only when scrolled to bottom)
    React.useEffect(() => {
        if (!logsOpen) return;

        const interval = setInterval(() => {
            setCountdown(prev => {
                if (prev <= 1) {
                    // Check if scrolled to bottom (within 50px threshold)
                    if (logsRef.current) {
                        const {scrollTop, scrollHeight, clientHeight} = logsRef.current;
                        const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
                        if (isAtBottom) {
                            fetchLogs(linesCount);
                        }
                    }
                    return 10; // Reset countdown
                }
                return prev - 1;
            });
        }, 1000);

        return () => clearInterval(interval);
    }, [logsOpen, linesCount]);

    const handleViewLogs = async () => {
        setLogsOpen(true);
        fetchLogs(linesCount, true); // Show loading on initial open
    };

    const handleLinesChange = (e, {value}) => {
        setLinesCount(value);
        fetchLogs(value);
    };

    const handleDownloadLogs = () => {
        const datetime = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        const filename = `${service.name}_${datetime}.txt`;
        const blob = new Blob([logs], {type: 'text/plain'});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
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
            <Media greaterThanOrEqual='tablet'>
                <Table.Cell>{service.port || '-'}</Table.Cell>
            </Media>
            <Media greaterThanOrEqual='tablet'>
                <Table.Cell>
                    <Icon name='circle' color={statusColor}/>
                    {service.status}
                </Table.Cell>
            </Media>
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
                    color='yellow'
                    disabled={loading}
                    loading={loading}
                    onClick={() => handleAction('Restart', restartService)}
                />
                <Modal
                    open={logsOpen}
                    onClose={() => setLogsOpen(false)}
                    onOpen={handleViewLogs}
                    trigger={<Button size='small' icon='file text' content='Logs' color='blue'/>}
                    size='fullscreen'
                >
                    <Modal.Header>Logs: {service.name}</Modal.Header>
                    <Modal.Content scrolling>
                        {logsLoading ? (
                            <Loader active inline='centered'/>
                        ) : (
                            <pre ref={logsRef} style={{
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
                        <span style={{marginRight: '0.5em', color: '#888'}}>{countdown}s</span>
                        <Dropdown
                            selection
                            options={linesOptions}
                            value={linesCount}
                            onChange={handleLinesChange}
                            style={{marginRight: 'auto'}}
                        />
                        <Button onClick={() => fetchLogs(linesCount)} color='blue' icon='refresh' content='Refresh'/>
                        <Button onClick={handleDownloadLogs} color='yellow' icon='download' content='Download'/>
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
                        color='violet'
                    />
                )}
            </Table.Cell>
            {!dockerized && (
                <Media greaterThanOrEqual='tablet'>
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
                </Media>
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
                        <Media greaterThanOrEqual='tablet'>
                            <Table.HeaderCell>Port</Table.HeaderCell>
                        </Media>
                        <Media greaterThanOrEqual='tablet'>
                            <Table.HeaderCell>Status</Table.HeaderCell>
                        </Media>
                        <Table.HeaderCell>Actions</Table.HeaderCell>
                        {!dockerized && (
                            <Media greaterThanOrEqual='tablet'>
                                <Table.HeaderCell>Boot</Table.HeaderCell>
                            </Media>
                        )}
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
                        {/* Mobile: 2 columns (Service, Actions) */}
                        <Media at='mobile'>
                            <Table.HeaderCell colSpan={2}>
                                <APIButton
                                    color='yellow'
                                    onClick={handleRestartServices}
                                    confirmContent='Are you sure you want to restart all WROLPi services?'
                                    confirmButton='Restart Services'
                                    disabled={restarting}
                                >
                                    <Icon name='refresh'/>
                                    {restarting ? 'Restarting...' : 'Restart All Services'}
                                </APIButton>
                            </Table.HeaderCell>
                        </Media>
                        {/* Tablet+: 4 columns (dockerized) or 5 columns (non-dockerized) */}
                        <Media greaterThanOrEqual='tablet'>
                            <Table.HeaderCell colSpan={dockerized ? 4 : 5}>
                                <APIButton
                                    color='yellow'
                                    onClick={handleRestartServices}
                                    confirmContent='Are you sure you want to restart all WROLPi services?'
                                    confirmButton='Restart Services'
                                    disabled={restarting}
                                >
                                    <Icon name='refresh'/>
                                    {restarting ? 'Restarting...' : 'Restart All Services'}
                                </APIButton>
                            </Table.HeaderCell>
                        </Media>
                    </Table.Row>
                </Table.Footer>
            </Table>
            {services.length === 0 && (
                <p>No services found. Services may not be available in this environment.</p>
            )}
        </Segment>
    );
}


// Helper to get health status color from SMART assessment
const getHealthColor = (assessment) => {
    if (!assessment) return 'grey';
    const upper = assessment.toUpperCase();
    if (upper === 'PASS') return 'green';
    if (upper === 'WARN') return 'yellow';
    if (upper === 'FAIL') return 'red';
    return 'grey';
};

// Helper to format power-on hours
const formatPowerOnHours = (hours) => {
    if (hours === null || hours === undefined) return '-';
    const days = Math.floor(hours / 24);
    const years = Math.floor(days / 365);
    if (years > 0) return `${hours.toLocaleString()} hrs (${years}y ${days % 365}d)`;
    if (days > 0) return `${hours.toLocaleString()} hrs (${days}d)`;
    return `${hours} hrs`;
};


function SmartDetailsModal({drive, open, onClose}) {
    if (!drive) return null;

    const healthColor = getHealthColor(drive.assessment);

    return (
        <Modal open={open} onClose={onClose} size='small'>
            <Modal.Header>
                <Icon name='heartbeat'/>
                SMART Details: {drive.device}
            </Modal.Header>
            <Modal.Content>
                <Table definition unstackable>
                    <Table.Body>
                        <Table.Row>
                            <Table.Cell width={6}>Model</Table.Cell>
                            <Table.Cell>{drive.model || '-'}</Table.Cell>
                        </Table.Row>
                        <Table.Row>
                            <Table.Cell>Serial</Table.Cell>
                            <Table.Cell>{drive.serial || '-'}</Table.Cell>
                        </Table.Row>
                        <Table.Row>
                            <Table.Cell>Capacity</Table.Cell>
                            <Table.Cell>{drive.capacity || '-'}</Table.Cell>
                        </Table.Row>
                        <Table.Row>
                            <Table.Cell>Assessment</Table.Cell>
                            <Table.Cell>
                                <Icon name='circle' color={healthColor}/>
                                {drive.assessment || 'Unknown'}
                            </Table.Cell>
                        </Table.Row>
                        <Table.Row>
                            <Table.Cell>Temperature</Table.Cell>
                            <Table.Cell>
                                {drive.temperature !== null && drive.temperature !== undefined
                                    ? `${drive.temperature}°C`
                                    : '-'}
                            </Table.Cell>
                        </Table.Row>
                        <Table.Row>
                            <Table.Cell>Power-On Hours</Table.Cell>
                            <Table.Cell>{formatPowerOnHours(drive.power_on_hours)}</Table.Cell>
                        </Table.Row>
                        <Table.Row>
                            <Table.Cell>Reallocated Sectors</Table.Cell>
                            <Table.Cell style={{color: drive.reallocated_sectors > 0 ? 'orange' : 'inherit'}}>
                                {drive.reallocated_sectors !== null && drive.reallocated_sectors !== undefined
                                    ? drive.reallocated_sectors
                                    : '-'}
                            </Table.Cell>
                        </Table.Row>
                        <Table.Row>
                            <Table.Cell>Pending Sectors</Table.Cell>
                            <Table.Cell style={{color: drive.pending_sectors > 0 ? 'orange' : 'inherit'}}>
                                {drive.pending_sectors !== null && drive.pending_sectors !== undefined
                                    ? drive.pending_sectors
                                    : '-'}
                            </Table.Cell>
                        </Table.Row>
                        <Table.Row>
                            <Table.Cell>SMART Enabled</Table.Cell>
                            <Table.Cell>{drive.smart_enabled ? 'Yes' : 'No'}</Table.Cell>
                        </Table.Row>
                    </Table.Body>
                </Table>
            </Modal.Content>
            <Modal.Actions>
                <Button onClick={onClose}>Close</Button>
            </Modal.Actions>
        </Modal>
    );
}


// Protected mount points that should not be unmounted
const PROTECTED_MOUNTS = ['/', '/boot', '/boot/firmware'];

// Helper to format disk size
const formatSize = (size) => {
    if (!size) return '-';
    // If already a string (e.g., "59.5G" from lsblk), return as-is
    if (typeof size === 'string') return size;
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    let bytes = size;
    while (bytes >= 1024 && i < units.length - 1) {
        bytes /= 1024;
        i++;
    }
    return `${bytes.toFixed(1)} ${units[i]}`;
};


function MountModal({disk, open, onClose, onMount}) {
    const [mountPoint, setMountPoint] = React.useState('');
    const [persist, setPersist] = React.useState(false);
    const [loading, setLoading] = React.useState(false);

    // Set default mount point when disk changes
    React.useEffect(() => {
        if (disk) {
            const defaultMount = disk.label ? `/media/${disk.label}` : `/media/${disk.name}`;
            setMountPoint(defaultMount);
            setPersist(false);
        }
    }, [disk]);

    const handleMount = async () => {
        if (!mountPoint.trim()) {
            toast({
                type: 'error',
                title: 'Mount point required',
                description: 'Please enter a mount point.',
                time: 3000,
            });
            return;
        }

        setLoading(true);
        try {
            await mountDisk(disk.path, mountPoint.trim(), disk.fstype, 'defaults', persist);
            toast({
                type: 'success',
                title: 'Disk Mounted',
                description: `${disk.name} mounted at ${mountPoint}`,
                time: 3000,
            });
            onClose();
            if (onMount) onMount();
        } catch (e) {
            toast({
                type: 'error',
                title: 'Mount Failed',
                description: e.message,
                time: 5000,
            });
        } finally {
            setLoading(false);
        }
    };

    if (!disk) return null;

    return (
        <Modal open={open} onClose={onClose} size='small'>
            <Modal.Header>
                <Icon name='disk'/>
                Mount Disk: {disk.name}
            </Modal.Header>
            <Modal.Content>
                <Form>
                    <Form.Field>
                        <label>Mount Point</label>
                        <Input
                            value={mountPoint}
                            onChange={(e) => setMountPoint(e.target.value)}
                            placeholder="/media/..."
                            fluid
                        />
                    </Form.Field>
                    <Form.Field>
                        <Checkbox
                            label="Persistent (survive reboots)"
                            checked={persist}
                            onChange={(e, {checked}) => setPersist(checked)}
                        />
                    </Form.Field>
                    {disk.fstype && (
                        <p style={{color: '#888', fontSize: '0.9em'}}>
                            Filesystem: {disk.fstype}
                            {disk.label && ` | Label: ${disk.label}`}
                            {disk.size && ` | Size: ${formatSize(disk.size)}`}
                        </p>
                    )}
                </Form>
            </Modal.Content>
            <Modal.Actions>
                <Button onClick={onClose} disabled={loading}>Cancel</Button>
                <Button color='green' onClick={handleMount} loading={loading} disabled={loading}>
                    <Icon name='check'/>
                    Mount
                </Button>
            </Modal.Actions>
        </Modal>
    );
}


function DiskSection() {
    const [disks, setDisks] = React.useState([]);
    const [fstabEntries, setFstabEntries] = React.useState([]);
    const [smartDrives, setSmartDrives] = React.useState([]);
    const [smartAvailable, setSmartAvailable] = React.useState(true);
    const [loading, setLoading] = React.useState(true);
    const [error, setError] = React.useState(null);
    const [selectedDrive, setSelectedDrive] = React.useState(null);
    const [detailsOpen, setDetailsOpen] = React.useState(false);
    const [mountModalOpen, setMountModalOpen] = React.useState(false);
    const [selectedDisk, setSelectedDisk] = React.useState(null);
    const [unmountConfirmOpen, setUnmountConfirmOpen] = React.useState(false);
    const [unmountTarget, setUnmountTarget] = React.useState(null);
    const dockerized = useDockerized();

    const fetchDiskInfo = async () => {
        setLoading(true);
        setError(null);
        try {
            const [disksResult, fstabResult, smartResult] = await Promise.allSettled([
                getDisks(),
                getFstabEntries(),
                getSmartStatus(),
            ]);

            if (disksResult.status === 'fulfilled') {
                setDisks(Array.isArray(disksResult.value) ? disksResult.value : []);
            }
            if (fstabResult.status === 'fulfilled') {
                setFstabEntries(Array.isArray(fstabResult.value) ? fstabResult.value : []);
            }
            if (smartResult.status === 'fulfilled' && smartResult.value) {
                // Handle new API format: {available: bool, drives: [...]}
                const smartData = smartResult.value;
                setSmartAvailable(smartData.available !== false);
                setSmartDrives(Array.isArray(smartData.drives) ? smartData.drives : []);
            } else {
                setSmartAvailable(false);
                setSmartDrives([]);
            }
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    const handleShowDetails = (drive) => {
        setSelectedDrive(drive);
        setDetailsOpen(true);
    };

    const handleOpenMountModal = (disk) => {
        setSelectedDisk(disk);
        setMountModalOpen(true);
    };

    const handleCloseMountModal = () => {
        setMountModalOpen(false);
        setSelectedDisk(null);
    };

    const handleUnmountClick = (mountPoint) => {
        setUnmountTarget(mountPoint);
        setUnmountConfirmOpen(true);
    };

    const handleUnmountConfirm = async () => {
        if (!unmountTarget) return;

        try {
            await unmountDisk(unmountTarget);
            toast({
                type: 'success',
                title: 'Disk Unmounted',
                description: `Unmounted ${unmountTarget}`,
                time: 3000,
            });
            fetchDiskInfo();
        } catch (e) {
            toast({
                type: 'error',
                title: 'Unmount Failed',
                description: e.message,
                time: 5000,
            });
        } finally {
            setUnmountConfirmOpen(false);
            setUnmountTarget(null);
        }
    };

    const handleTogglePersist = async (disk, enable) => {
        try {
            if (enable) {
                await addFstabEntry(disk.path, disk.mountpoint, disk.fstype || 'auto');
                toast({
                    type: 'success',
                    title: 'Persistence Enabled',
                    description: `${disk.mountpoint} will persist across reboots`,
                    time: 3000,
                });
            } else {
                await removeFstabEntry(disk.mountpoint);
                toast({
                    type: 'success',
                    title: 'Persistence Disabled',
                    description: `${disk.mountpoint} will not persist across reboots`,
                    time: 3000,
                });
            }
            fetchDiskInfo();
        } catch (e) {
            toast({
                type: 'error',
                title: 'Failed to update persistence',
                description: e.message,
                time: 5000,
            });
        }
    };

    // Check if a mount point is in fstab (persistent)
    const isPersistent = (mountpoint) => {
        return fstabEntries.some(entry => entry.mount_point === mountpoint);
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

            <Header as='h4'>Disks</Header>
            {disks.length > 0 ? (
                <Table unstackable striped compact>
                    <Table.Header>
                        <Table.Row>
                            <Table.HeaderCell>Name</Table.HeaderCell>
                            <Table.HeaderCell>Size</Table.HeaderCell>
                            <Table.HeaderCell>Type</Table.HeaderCell>
                            <Table.HeaderCell>Label</Table.HeaderCell>
                            <Table.HeaderCell>Mount Point</Table.HeaderCell>
                            <Table.HeaderCell>Persist</Table.HeaderCell>
                            <Table.HeaderCell>Actions</Table.HeaderCell>
                        </Table.Row>
                    </Table.Header>
                    <Table.Body>
                        {disks.map((disk) => {
                            const isMounted = disk.mountpoint && disk.mountpoint !== '';
                            const isProtected = PROTECTED_MOUNTS.includes(disk.mountpoint);
                            const persistent = isMounted && isPersistent(disk.mountpoint);

                            return (
                                <Table.Row key={disk.path || disk.name}>
                                    <Table.Cell>{disk.name}</Table.Cell>
                                    <Table.Cell>{formatSize(disk.size)}</Table.Cell>
                                    <Table.Cell>{disk.fstype || '-'}</Table.Cell>
                                    <Table.Cell>{disk.label || '-'}</Table.Cell>
                                    <Table.Cell>
                                        {isMounted ? (
                                            <span>{disk.mountpoint}</span>
                                        ) : (
                                            <span style={{color: '#888'}}>-</span>
                                        )}
                                    </Table.Cell>
                                    <Table.Cell>
                                        {isMounted && !isProtected ? (
                                            <Toggle
                                                checked={persistent}
                                                onChange={(checked) => handleTogglePersist(disk, checked)}
                                                label={persistent ? 'Enabled' : 'Disabled'}
                                            />
                                        ) : (
                                            <span style={{color: '#888'}}>-</span>
                                        )}
                                    </Table.Cell>
                                    <Table.Cell>
                                        {isMounted && isProtected ? (
                                            <span style={{color: '#888'}}>System</span>
                                        ) : isMounted ? (
                                            <Button
                                                size='small'
                                                color='red'
                                                icon='eject'
                                                content='Unmount'
                                                onClick={() => handleUnmountClick(disk.mountpoint)}
                                            />
                                        ) : (
                                            <Button
                                                size='small'
                                                color='green'
                                                icon='plug'
                                                content='Mount'
                                                onClick={() => handleOpenMountModal(disk)}
                                            />
                                        )}
                                    </Table.Cell>
                                </Table.Row>
                            );
                        })}
                    </Table.Body>
                </Table>
            ) : (
                <p>No disks detected.</p>
            )}

            <Header as='h4'>SMART Health</Header>
            {!smartAvailable ? (
                <p style={{color: '#888'}}>SMART monitoring not available (pySMART not installed or not supported)</p>
            ) : smartDrives.length > 0 ? (
                <Table unstackable striped compact>
                    <Table.Header>
                        <Table.Row>
                            <Table.HeaderCell>Device</Table.HeaderCell>
                            <Table.HeaderCell>Health</Table.HeaderCell>
                            <Table.HeaderCell>Temperature</Table.HeaderCell>
                            <Table.HeaderCell>Actions</Table.HeaderCell>
                        </Table.Row>
                    </Table.Header>
                    <Table.Body>
                        {smartDrives.map((drive) => (
                            <Table.Row key={drive.device}>
                                <Table.Cell>{drive.device}</Table.Cell>
                                <Table.Cell>
                                    <Icon
                                        name='circle'
                                        color={getHealthColor(drive.assessment)}
                                    />
                                    {drive.assessment || 'Unknown'}
                                </Table.Cell>
                                <Table.Cell>
                                    {drive.temperature !== null && drive.temperature !== undefined
                                        ? `${drive.temperature}°C`
                                        : '-'}
                                </Table.Cell>
                                <Table.Cell>
                                    <Button
                                        size='small'
                                        icon='info'
                                        content='Details'
                                        onClick={() => handleShowDetails(drive)}
                                    />
                                </Table.Cell>
                            </Table.Row>
                        ))}
                    </Table.Body>
                </Table>
            ) : (
                <p>No SMART-capable drives detected.</p>
            )}

            <SmartDetailsModal
                drive={selectedDrive}
                open={detailsOpen}
                onClose={() => setDetailsOpen(false)}
            />

            <MountModal
                disk={selectedDisk}
                open={mountModalOpen}
                onClose={handleCloseMountModal}
                onMount={fetchDiskInfo}
            />

            <Confirm
                open={unmountConfirmOpen}
                header='Unmount Disk'
                content={`Are you sure you want to unmount ${unmountTarget}?`}
                onCancel={() => {
                    setUnmountConfirmOpen(false);
                    setUnmountTarget(null);
                }}
                onConfirm={handleUnmountConfirm}
                confirmButton='Unmount'
            />

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


export function ControllerPage() {
    return (
        <Container fluid>
            <AdminControlsSection/>
            <ServicesSection/>
            <DiskSection/>
        </Container>
    );
}

export default ControllerPage;
