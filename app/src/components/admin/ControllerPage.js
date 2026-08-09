import React from 'react';
import {IconInfoCircle, IconPlayerEject} from '@tabler/icons-react';
import {
    Button,
    Checkbox,
    Confirm,
    Group,
    Header,
    Icon,
    IconButton,
    Loading,
    Message,
    Modal,
    Panel,
    Select,
    Status,
    Table,
    TextInput,
    toast,
} from "../ui";
import {APIButton, BluetoothToggle, DesktopToggle, DirectorySearch, HandPointMessage, HotspotToggle, InfoMessage, ThrottleToggle, Toggle, VncToggle,} from "../Common";
import {useDockerized, useMediaDirectory} from "../../hooks/customHooks";
import {Media} from "../../contexts/contexts";
import {
    addFstabEntry,
    addSambaShare,
    disableService,
    enableService,
    getDisks,
    getFstabEntries,
    getHotspotDevices,
    getHotspotProtocols,
    getHotspotSettings,
    getSambaStatus,
    getServiceLogs,
    getServices,
    getSmartStatus,
    mountDisk,
    removeFstabEntry,
    removeSambaShare,
    restartService,
    restartServices,
    startService,
    stopService,
    unmountDisk,
    updateHotspotSettings,
} from "../../api/controller";
import QRCode from "react-qr-code";
import {RestartButton, ShutdownButton} from "./Settings";
import {CONTROLLER_URI} from "../Vars";


// Service status kind mapping. Status only knows complete/active/pending/failed,
// so "stopped" and "unknown" both land on pending -- the Start/Stop button and
// service name still tell them apart, this dot only carries running vs. failed.
const statusKinds = {
    running: 'complete',
    stopped: 'pending',
    failed: 'failed',
    unknown: 'pending',
};

// Sort order within a group: problems first so they stay visible.
const statusSortOrder = {
    failed: 0,
    unknown: 1,
    stopped: 2,
    running: 3,
};

// Partition services into the two Controller groups. The backend computes each
// service's `group` ("core" | "optional"); a missing group (e.g. Docker
// containers) is treated as core so nothing is hidden. Within each group,
// failed/stopped services sort first, then alphabetically.
export const groupServices = (services) => {
    const byStatusThenName = (a, b) => {
        const sa = statusSortOrder[a.status] ?? 1;
        const sb = statusSortOrder[b.status] ?? 1;
        if (sa !== sb) return sa - sb;
        return a.name.localeCompare(b.name);
    };
    const core = services.filter(s => s.group !== 'optional').sort(byStatusThenName);
    const optional = services.filter(s => s.group === 'optional').sort(byStatusThenName);
    return {core, optional};
};


const linesOptions = [
    {value: '100', label: '100 lines'},
    {value: '250', label: '250 lines'},
    {value: '500', label: '500 lines'},
    {value: '1000', label: '1000 lines'},
    {value: '5000', label: '5000 lines'},
];

// Custom hook for service row state and handlers
function useServiceRow(service, onAction) {
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

    const handleLinesChange = (value) => {
        const lines = parseInt(value, 10);
        setLinesCount(lines);
        fetchLogs(lines);
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
    const statusKind = statusKinds[service.status] || 'pending';

    // Build view URL if service is viewable
    let viewUrl = null;
    if (service.viewable && service.port && isRunning) {
        const protocol = service.use_https ? 'https' : 'http';
        const host = window.location.hostname;
        const path = service.view_path || '';
        const isDefaultPort = (protocol === 'https' && service.port === 443) || (protocol === 'http' && service.port === 80);
        const portSuffix = isDefaultPort ? '' : `:${service.port}`;
        viewUrl = `${protocol}://${host}${portSuffix}${path}`;
    }

    return {
        loading, logsOpen, setLogsOpen, logs, logsLoading, linesCount, countdown, logsRef,
        handleAction, fetchLogs, handleViewLogs, handleLinesChange, handleDownloadLogs,
        isRunning, statusKind, viewUrl
    };
}

// Logs modal component (shared between mobile and desktop)
function ServiceLogsModal({
                              service,
                              logsOpen,
                              setLogsOpen,
                              logs,
                              logsLoading,
                              logsRef,
                              linesCount,
                              countdown,
                              handleLinesChange,
                              handleDownloadLogs,
                              fetchLogs
                          }) {
    return (
        <Modal
            open={logsOpen}
            onClose={() => setLogsOpen(false)}
            size='fullscreen'
        >
            <Modal.Header>Logs: {service.name}</Modal.Header>
            <Modal.Content scrolling>
                {logsLoading ? (
                    <Loading/>
                ) : (
                    <pre ref={logsRef} style={{
                        whiteSpace: 'pre-wrap',
                        wordWrap: 'break-word',
                        maxHeight: '400px',
                        overflow: 'auto',
                        background: 'var(--panel)',
                        color: 'var(--text)',
                        padding: '1em',
                        fontFamily: 'var(--font-mono)',
                        fontSize: '0.85em',
                    }}>
                        {logs}
                    </pre>
                )}
            </Modal.Content>
            <Modal.Actions>
                <span style={{marginRight: '0.5em', color: 'var(--muted)'}}>{countdown}s</span>
                <Select
                    data={linesOptions}
                    value={String(linesCount)}
                    onChange={handleLinesChange}
                    style={{marginRight: 'auto'}}
                />
                <Button onClick={() => fetchLogs(linesCount)} role='primary' icon='refresh'>Refresh</Button>
                <Button onClick={handleDownloadLogs} color='yellow' icon='download'>Download</Button>
                <Button role='cancel' onClick={() => setLogsOpen(false)}>Close</Button>
            </Modal.Actions>
        </Modal>
    );
}

// Mobile service row - simplified layout
function MobileServiceRow({service, onAction}) {
    const {
        loading, logsOpen, setLogsOpen, logs, logsLoading, linesCount, countdown, logsRef,
        handleAction, fetchLogs, handleViewLogs, handleLinesChange, handleDownloadLogs,
        isRunning, statusKind, viewUrl
    } = useServiceRow(service, onAction);

    return (
        <Table.Row failed={service.status === 'failed'}>
            <Table.Cell>
                <Status kind={statusKind} plain/>
                <strong>{service.name}</strong>
                {service.description &&
                    <div style={{fontSize: '0.9em', color: 'var(--muted)'}}>{service.description}</div>}
            </Table.Cell>
            <Table.Cell numeric>
                <div className='wrolpi-button-row' style={{justifyContent: 'flex-end'}}>
                {isRunning ? (
                    <IconButton
                        icon='stop'
                        label={`Stop ${service.name}`}
                        role='danger'
                        disabled={loading}
                        loading={loading}
                        onClick={() => handleAction('Stop', stopService)}
                    />
                ) : (
                    <IconButton
                        icon='play'
                        label={`Start ${service.name}`}
                        role='save'
                        disabled={loading}
                        loading={loading}
                        onClick={() => handleAction('Start', startService)}
                    />
                )}
                <IconButton
                    icon='refresh'
                    label={`Restart ${service.name}`}
                    role='retry'
                    disabled={loading}
                    loading={loading}
                    onClick={() => handleAction('Restart', restartService)}
                />
                <IconButton
                    icon='file text'
                    label={`View logs for ${service.name}`}
                    role='primary'
                    onClick={handleViewLogs}
                />
                </div>
                <ServiceLogsModal
                    service={service}
                    logsOpen={logsOpen}
                    setLogsOpen={setLogsOpen}
                    logs={logs}
                    logsLoading={logsLoading}
                    logsRef={logsRef}
                    linesCount={linesCount}
                    countdown={countdown}
                    handleLinesChange={handleLinesChange}
                    handleDownloadLogs={handleDownloadLogs}
                    fetchLogs={fetchLogs}
                />
                {viewUrl && (
                    <IconButton
                        icon='external'
                        label={`Open ${service.name}`}
                        color='violet'
                        component='a'
                        href={viewUrl}
                        target='_blank'
                        rel='noopener noreferrer'
                    />
                )}
            </Table.Cell>
        </Table.Row>
    );
}

// Desktop service row - full layout with all columns
function DesktopServiceRow({service, onAction, dockerized}) {
    const {
        loading, logsOpen, setLogsOpen, logs, logsLoading, linesCount, countdown, logsRef,
        handleAction, fetchLogs, handleViewLogs, handleLinesChange, handleDownloadLogs,
        isRunning, statusKind, viewUrl
    } = useServiceRow(service, onAction);

    return (
        <Table.Row failed={service.status === 'failed'}>
            <Table.Cell>
                <Status kind={statusKind} plain/>
                <strong>{service.name}</strong>
                {service.description &&
                    <div style={{fontSize: '0.9em', color: 'var(--muted)'}}>{service.description}</div>}
            </Table.Cell>
            <Table.Cell>{service.port || '-'}</Table.Cell>
            <Table.Cell>
                <div className='wrolpi-button-row'>
                {isRunning ? (
                    <IconButton
                        icon='stop'
                        label={`Stop ${service.name}`}
                        role='danger'
                        disabled={loading}
                        loading={loading}
                        onClick={() => handleAction('Stop', stopService)}
                    />
                ) : (
                    <IconButton
                        icon='play'
                        label={`Start ${service.name}`}
                        role='save'
                        disabled={loading}
                        loading={loading}
                        onClick={() => handleAction('Start', startService)}
                    />
                )}
                <IconButton
                    icon='refresh'
                    label={`Restart ${service.name}`}
                    role='retry'
                    disabled={loading}
                    loading={loading}
                    onClick={() => handleAction('Restart', restartService)}
                />
                <IconButton
                    icon='file text'
                    label={`View logs for ${service.name}`}
                    role='primary'
                    onClick={handleViewLogs}
                />
                </div>
                <ServiceLogsModal
                    service={service}
                    logsOpen={logsOpen}
                    setLogsOpen={setLogsOpen}
                    logs={logs}
                    logsLoading={logsLoading}
                    logsRef={logsRef}
                    linesCount={linesCount}
                    countdown={countdown}
                    handleLinesChange={handleLinesChange}
                    handleDownloadLogs={handleDownloadLogs}
                    fetchLogs={fetchLogs}
                />
                {viewUrl && (
                    <IconButton
                        icon='external'
                        label={`Open ${service.name}`}
                        color='violet'
                        component='a'
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
        return <Panel>
            <Header as='h3'>Services</Header>
            <Loading/>
        </Panel>;
    }

    if (error) {
        return <Panel>
            <Header as='h3'>Services</Header>
            <Message kind='error'>Error loading services: {error}</Message>
            <Button role='retry' icon='refresh' onClick={fetchServices}>Retry</Button>
        </Panel>;
    }

    const restartButton = (colSpan) => (
        <Table.Footer>
            <Table.Row>
                <Table.HeaderCell colSpan={colSpan}>
                    <APIButton
                        role='retry'
                        icon='refresh'
                        onClick={handleRestartServices}
                        confirmContent='Are you sure you want to restart all WROLPi services?'
                        confirmButton='Restart Services'
                        disabled={restarting}
                    >
                        {restarting ? 'Restarting...' : 'Restart All Services'}
                    </APIButton>
                </Table.HeaderCell>
            </Table.Row>
        </Table.Footer>
    );

    const {core, optional} = groupServices(services);

    // Full-width labeled separator between the two service groups.
    const groupLabelRow = (key, title, colSpan) => (
        <Table.Row key={key} className='service-group-label'>
            <Table.Cell colSpan={colSpan} style={{fontWeight: 'bold'}}>
                {title}
            </Table.Cell>
        </Table.Row>
    );

    const groupedRows = (RowComponent, colSpan, extraProps = {}) => {
        const rows = [];
        // Only label the Core group when there is also an Optional group to
        // distinguish it from; otherwise a lone header adds noise.
        if (core.length > 0 && optional.length > 0) {
            rows.push(groupLabelRow('label-core', 'Core Services', colSpan));
        }
        core.forEach(service => rows.push(
            <RowComponent key={service.name} service={service} onAction={fetchServices} {...extraProps}/>
        ));
        if (optional.length > 0) {
            rows.push(groupLabelRow('label-optional', 'Optional & Maintenance', colSpan));
            optional.forEach(service => rows.push(
                <RowComponent key={service.name} service={service} onAction={fetchServices} {...extraProps}/>
            ));
        }
        return rows;
    };

    return (
        <Panel>
            <Header as='h3' icon='server'>Services</Header>
            {/* Mobile table - 2 columns */}
            <Media at='mobile'>
                <Table>
                    <Table.Header>
                        <Table.Row>
                            <Table.HeaderCell>Service</Table.HeaderCell>
                            <Table.HeaderCell>Actions</Table.HeaderCell>
                        </Table.Row>
                    </Table.Header>
                    <Table.Body>
                        {groupedRows(MobileServiceRow, 2)}
                    </Table.Body>
                    {restartButton(2)}
                </Table>
            </Media>
            {/* Desktop table - full columns */}
            <Media greaterThanOrEqual='tablet'>
                <Table>
                    <Table.Header>
                        <Table.Row>
                            <Table.HeaderCell>Service</Table.HeaderCell>
                            <Table.HeaderCell>Port</Table.HeaderCell>
                            <Table.HeaderCell>Actions</Table.HeaderCell>
                            {!dockerized && <Table.HeaderCell>Boot</Table.HeaderCell>}
                        </Table.Row>
                    </Table.Header>
                    <Table.Body>
                        {groupedRows(DesktopServiceRow, dockerized ? 3 : 4, {dockerized})}
                    </Table.Body>
                    {restartButton(dockerized ? 4 : 5)}
                </Table>
            </Media>
            {services.length === 0 && (
                <p>No services found. Services may not be available in this environment.</p>
            )}
        </Panel>
    );
}


// Helper to get health status color from SMART assessment
/**
 * The severity of a SMART assessment.
 *
 * Roles, not hues: a drive's health is a severity and has to rank as one.  All four
 * branches together -- a helper where PASS and FAIL rank but WARN is an unranked hue is
 * worse than either choice, and in night `--amber` is byte-identical to `--yellow`, so WARN
 * would stop sitting between them.
 *
 * Exported and pure so the mapping can be tested as a mapping rather than scraped out of
 * the source, which is what this needed before it was separated from the CSS wrapper.
 */
export const healthRole = (assessment) => {
    if (!assessment) return 'neutral';
    switch (assessment.toUpperCase()) {
        case 'PASS':
            return 'success';
        case 'WARN':
            return 'warning';
        case 'FAIL':
            return 'danger';
        default:
            return 'neutral';
    }
};

const getHealthColor = (assessment) => `var(--${healthRole(assessment)})`;

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

    const healthColor = getHealthColor(drive.health || drive.assessment);

    return (
        <Modal open={open} onClose={onClose} size='small'>
            <Modal.Header>
                <Icon name='heartbeat'/> SMART Details: {drive.device}
            </Modal.Header>
            <Modal.Content>
                <Table>
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
                                <span style={{color: healthColor}}>&#9679;</span>{' '}
                                {drive.assessment || drive.health || 'Unknown'}
                                {drive.smart_limited
                                    ? ' (limited — USB enclosure reports health only, no attributes)'
                                    : ''}
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
                            <Table.Cell style={{color: drive.reallocated_sectors > 0 ? 'var(--amber)' : 'inherit'}}>
                                {drive.reallocated_sectors !== null && drive.reallocated_sectors !== undefined
                                    ? drive.reallocated_sectors
                                    : '-'}
                            </Table.Cell>
                        </Table.Row>
                        <Table.Row>
                            <Table.Cell>Pending Sectors</Table.Cell>
                            <Table.Cell style={{color: drive.pending_sectors > 0 ? 'var(--amber)' : 'inherit'}}>
                                {drive.pending_sectors !== null && drive.pending_sectors !== undefined
                                    ? drive.pending_sectors
                                    : '-'}
                            </Table.Cell>
                        </Table.Row>
                        <Table.Row>
                            <Table.Cell>Uncorrectable Sectors</Table.Cell>
                            <Table.Cell style={{color: drive.offline_uncorrectable > 0 ? 'var(--amber)' : 'inherit'}}>
                                {drive.offline_uncorrectable !== null && drive.offline_uncorrectable !== undefined
                                    ? drive.offline_uncorrectable
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
                <Button role='cancel' onClick={onClose}>Close</Button>
            </Modal.Actions>
        </Modal>
    );
}


// The primary mount can be unmounted (to swap in a backup drive), but doing
// so stops the WROLPi API service — the unmount modal warns about this.  Any
// mount outside /media belongs to the system (/, /boot/efi, /boot/firmware, …)
// and is entirely untouchable.
const PRIMARY_MOUNT = '/media/wrolpi';

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


function formatBytes(bytes) {
    if (!bytes || bytes < 1) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    let n = bytes;
    while (n >= 1024 && i < units.length - 1) {
        n /= 1024;
        i++;
    }
    return `${n.toFixed(n >= 10 ? 0 : 1)} ${units[i]}`;
}

function MountModal({disk, open, onClose, onMount}) {
    const [mountPoint, setMountPoint] = React.useState('');
    const [persist, setPersist] = React.useState(false);
    const [loading, setLoading] = React.useState(false);
    const [shadowed, setShadowed] = React.useState(null);

    // Set default mount point when disk changes
    React.useEffect(() => {
        if (disk) {
            const defaultMount = disk.label ? `/media/${disk.label}` : `/media/${disk.name}`;
            setMountPoint(defaultMount);
            setPersist(false);
            setShadowed(null);
        }
    }, [disk]);

    const performMount = async (forceShadowed) => {
        setLoading(true);
        try {
            const result = await mountDisk(disk.path, mountPoint.trim(), disk.fstype, 'defaults', persist, forceShadowed);

            // Soft-block: target contains data that would be hidden by the mount.
            if (result && result.success === false && result.needs_force === 'shadowed') {
                setShadowed(result.shadowed_data || {entries: [], size_bytes: 0});
                return;
            }

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
        await performMount(false);
    };

    const handleForceMount = () => performMount(true);

    const handleCancel = () => {
        setShadowed(null);
        onClose();
    };

    if (!disk) return null;

    if (shadowed) {
        const entries = (shadowed.entries || []).join(', ') || '(unknown)';
        return (
            <Modal open={open} onClose={handleCancel} size='small'>
                <Modal.Header>
                    <Icon name='warning sign'/> Existing Files Detected
                </Modal.Header>
                <Modal.Content>
                    <p>
                        Mounting <strong>{disk.name}</strong> at <code>{mountPoint}</code> would
                        hide existing files that are already there.
                    </p>
                    <p>
                        Found <strong>{entries}</strong> ({formatBytes(shadowed.size_bytes)}) at the mount target.
                    </p>
                    {/* A caution about a consequence, not a failure -- the destructive
                        weight is already carried by the confirm button below. */}
                    <p style={{color: 'var(--warning)'}}>
                        Those files will continue to consume space on the underlying filesystem
                        (typically the SD card on a Raspberry Pi) and can fill it up.
                    </p>
                    <p>
                        Recommended: cancel, move or delete the existing files, then mount.
                    </p>
                </Modal.Content>
                <Modal.Actions>
                    <Button role='cancel' onClick={handleCancel} disabled={loading}>Cancel</Button>
                    <Button role='retry' icon='exclamation triangle' onClick={handleForceMount} loading={loading}
                            disabled={loading}>
                        Mount Anyway
                    </Button>
                </Modal.Actions>
            </Modal>
        );
    }

    return (
        <Modal open={open} onClose={onClose} size='small'>
            <Modal.Header>
                <Icon name='disk'/> Mount Disk: {disk.name}
            </Modal.Header>
            <Modal.Content>
                <TextInput
                    autoFocus
                    label='Mount Point'
                    value={mountPoint}
                    onChange={(e) => setMountPoint(e.target.value)}
                    placeholder="/media/..."
                />
                <div style={{marginTop: '0.8em'}}>
                    <Checkbox
                        label="Persistent (survive reboots)"
                        checked={persist}
                        onChange={(e) => setPersist(e.currentTarget.checked)}
                    />
                </div>
                {disk.fstype && (
                    <p style={{color: 'var(--muted)', fontSize: '0.9em'}}>
                        Filesystem: {disk.fstype}
                        {disk.label && ` | Label: ${disk.label}`}
                        {disk.size && ` | Size: ${formatSize(disk.size)}`}
                    </p>
                )}
            </Modal.Content>
            <Modal.Actions>
                <Button role='cancel' onClick={onClose} disabled={loading}>Cancel</Button>
                <Button role='save' icon='check' onClick={handleMount} loading={loading} disabled={loading}>
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
            const result = await unmountDisk(unmountTarget);
            const stoppedServices = (result && result.stopped_services) || [];
            toast({
                type: 'success',
                title: 'Disk Unmounted',
                description: stoppedServices.length > 0 ?
                    `Unmounted ${unmountTarget}; stopped ${stoppedServices.join(', ')}` :
                    `Unmounted ${unmountTarget}`,
                time: 5000,
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
            <Panel>
                <Header as='h3' icon='disk'>Disk Management</Header>
                <p>Disk management is not available in Docker environments.</p>
            </Panel>
        );
    }

    if (loading) {
        return <Panel>
            <Header as='h3'>Disk Management</Header>
            <Loading/>
        </Panel>;
    }

    return (
        <Panel>
            <Header as='h3' icon='disk'>Disk Management</Header>

            {error && <Message kind='warning'>Some disk information unavailable: {error}</Message>}

            <Header as='h4'>Disks</Header>
            {disks.length > 0 ? (
                <Table>
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
                            const isPrimary = disk.mountpoint === PRIMARY_MOUNT;
                            // Mounts outside /media (/, /boot/efi, …) are system mounts.
                            const isSystemMount = isMounted && !isPrimary && !disk.mountpoint.startsWith('/media/');
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
                                            <span style={{color: 'var(--muted)'}}>-</span>
                                        )}
                                    </Table.Cell>
                                    <Table.Cell>
                                        {isMounted && !isSystemMount ? (
                                            <Toggle
                                                checked={persistent}
                                                onChange={(checked) => handleTogglePersist(disk, checked)}
                                                label={persistent ? 'Enabled' : 'Disabled'}
                                            />
                                        ) : (
                                            <span style={{color: 'var(--muted)'}}>-</span>
                                        )}
                                    </Table.Cell>
                                    <Table.Cell>
                                        {isMounted && isSystemMount ? (
                                            <span style={{color: 'var(--muted)'}}>System</span>
                                        ) : isMounted ? (
                                            <Button
                                                size='sm'
                                                role='danger'
                                                icon={IconPlayerEject}
                                                onClick={() => handleUnmountClick(disk.mountpoint)}
                                            >
                                                Unmount
                                            </Button>
                                        ) : (
                                            <Button
                                                size='sm'
                                                role='save'
                                                icon='plug'
                                                onClick={() => handleOpenMountModal(disk)}
                                            >
                                                Mount
                                            </Button>
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
                <p style={{color: 'var(--muted)'}}>SMART monitoring not available (pySMART not installed or not
                    supported)</p>
            ) : smartDrives.length > 0 ? (
                <Table>
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
                                    <span style={{color: getHealthColor(drive.health || drive.assessment)}}>
                                        &#9679;
                                    </span>{' '}
                                    {drive.health || drive.assessment || 'Unknown'}
                                    {drive.smart_limited ? ' (limited)' : ''}
                                </Table.Cell>
                                <Table.Cell>
                                    {drive.temperature !== null && drive.temperature !== undefined
                                        ? `${drive.temperature}°C`
                                        : '-'}
                                </Table.Cell>
                                <Table.Cell>
                                    <Button
                                        size='sm'
                                        role='cancel'
                                        icon={IconInfoCircle}
                                        onClick={() => handleShowDetails(drive)}
                                    >
                                        Details
                                    </Button>
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
                title='Unmount Disk'
                destructive
                confirmLabel='Unmount'
                onCancel={() => {
                    setUnmountConfirmOpen(false);
                    setUnmountTarget(null);
                }}
                onConfirm={handleUnmountConfirm}
            >
                {unmountTarget === PRIMARY_MOUNT ? (
                    <div>
                        <p>Are you sure you want to unmount <code>{unmountTarget}</code>?</p>
                        <p>
                            This is the primary WROLPi drive. The WROLPi API service will
                            be <strong>stopped</strong> before unmounting, and your media will be
                            unavailable until a drive is mounted at <code>{PRIMARY_MOUNT}</code> and
                            the API service is started again.
                        </p>
                    </div>
                ) : `Are you sure you want to unmount ${unmountTarget}?`}
            </Confirm>

            <Button role='cancel' icon='refresh' onClick={fetchDiskInfo} style={{marginTop: '1em'}}>
                Refresh
            </Button>
        </Panel>
    );
}


function SambaSection() {
    const [status, setStatus] = React.useState(null);
    const [loading, setLoading] = React.useState(true);
    const [actionLoading, setActionLoading] = React.useState(false);
    const [addOpen, setAddOpen] = React.useState(false);
    const [shareAll, setShareAll] = React.useState(true);
    const [newName, setNewName] = React.useState('');
    const [newPath, setNewPath] = React.useState('');
    const [newReadOnly, setNewReadOnly] = React.useState(true);
    const [newComment, setNewComment] = React.useState('');
    const [removeConfirmName, setRemoveConfirmName] = React.useState(null);
    const dockerized = useDockerized();
    const mediaDirectory = useMediaDirectory();

    const fetchStatus = async () => {
        try {
            const result = await getSambaStatus();
            setStatus(result);
        } catch (e) {
            console.error('Failed to fetch Samba status:', e);
        } finally {
            setLoading(false);
        }
    };

    React.useEffect(() => {
        fetchStatus();
        const interval = setInterval(fetchStatus, 10000);
        return () => clearInterval(interval);
    }, []);

    const handleAddShare = async () => {
        if (!newName.trim()) return;
        setActionLoading(true);
        const absolutePath = shareAll
            ? mediaDirectory
            : `${mediaDirectory}/${newPath.trim()}`;
        try {
            await addSambaShare(newName.trim(), absolutePath, newReadOnly, newComment.trim());
            toast({type: 'success', title: 'Share Added', description: `Added share "${newName}"`, time: 3000});
            setAddOpen(false);
            setShareAll(true);
            setNewName('');
            setNewPath('');
            setNewReadOnly(true);
            setNewComment('');
            await fetchStatus();
        } catch (e) {
            toast({type: 'error', title: 'Add Share Failed', description: e.message, time: 5000});
        } finally {
            setActionLoading(false);
        }
    };

    const handleRemoveShare = async (name) => {
        setActionLoading(true);
        try {
            await removeSambaShare(name);
            toast({type: 'success', title: 'Share Removed', description: `Removed share "${name}"`, time: 3000});
            await fetchStatus();
        } catch (e) {
            toast({type: 'error', title: 'Remove Share Failed', description: e.message, time: 5000});
        } finally {
            setActionLoading(false);
            setRemoveConfirmName(null);
        }
    };

    if (loading) {
        return <Panel><Loading/></Panel>;
    }

    if (!status || !status.available) {
        if (dockerized) return null;
        return (
            <Panel>
                <Header as='h3' icon='folder open'>Network Shares (Samba)</Header>
                <Message kind='info'>Samba is not available on this system.</Message>
            </Panel>
        );
    }

    const shares = status.shares || [];

    return (
        <Panel>
            <Header as='h3' icon='folder open'>Network Shares (Samba)</Header>

            <p>Configure directories to share over the local network. Start the smbd service to activate sharing.</p>

            {shares.length > 0 && (
                <Table style={{marginTop: '1em'}}>
                    <Table.Header>
                        <Table.Row>
                            <Table.HeaderCell>Name</Table.HeaderCell>
                            <Table.HeaderCell>Path</Table.HeaderCell>
                            <Table.HeaderCell>Read Only</Table.HeaderCell>
                            <Table.HeaderCell>Comment</Table.HeaderCell>
                            <Table.HeaderCell>Actions</Table.HeaderCell>
                        </Table.Row>
                    </Table.Header>
                    <Table.Body>
                        {shares.map(share => (
                            <Table.Row key={share.name}>
                                <Table.Cell>{share.name}</Table.Cell>
                                <Table.Cell><code>{share.path}</code></Table.Cell>
                                <Table.Cell>{share.read_only ? 'Yes' : 'No'}</Table.Cell>
                                <Table.Cell>{share.comment}</Table.Cell>
                                <Table.Cell>
                                    <IconButton
                                        icon='trash'
                                        label={`Remove share "${share.name}"`}
                                        role='danger'
                                        size='xs'
                                        disabled={actionLoading}
                                        onClick={() => setRemoveConfirmName(share.name)}
                                    />
                                </Table.Cell>
                            </Table.Row>
                        ))}
                    </Table.Body>
                </Table>
            )}

            <Confirm
                open={removeConfirmName !== null}
                title='Remove Share'
                confirmLabel='Remove'
                destructive
                onCancel={() => setRemoveConfirmName(null)}
                onConfirm={() => handleRemoveShare(removeConfirmName)}
            >
                {`Remove the share "${removeConfirmName}"?`}
            </Confirm>

            <div style={{marginTop: '1em'}}>
                <Button
                    role='primary'
                    icon='plus'
                    onClick={() => setAddOpen(true)}
                    disabled={actionLoading}
                >
                    Add Share
                </Button>
            </div>

            <Modal open={addOpen} onClose={() => {
                setAddOpen(false);
                setShareAll(true);
            }} size='large'>
                <Modal.Header>Add Samba Share</Modal.Header>
                <Modal.Content>
                    <TextInput
                        label='Share Name'
                        placeholder='e.g. Documents'
                        value={newName}
                        onChange={(e) => setNewName(e.target.value)}
                    />
                    <div style={{marginTop: '0.8em'}}>
                        <Checkbox
                            label='Share all files'
                            checked={shareAll}
                            onChange={(e) => setShareAll(e.currentTarget.checked)}
                        />
                    </div>
                    {!shareAll && (
                        <div style={{marginTop: '0.8em'}}>
                            <label>Path</label>
                            <DirectorySearch
                                onSelect={setNewPath}
                                value={newPath}
                            />
                        </div>
                    )}
                    <div style={{marginTop: '0.8em'}}>
                        <Checkbox
                            label='Read Only'
                            checked={newReadOnly}
                            onChange={(e) => setNewReadOnly(e.currentTarget.checked)}
                        />
                    </div>
                    <TextInput
                        style={{marginTop: '0.8em'}}
                        label='Comment (optional)'
                        placeholder='Description of this share'
                        value={newComment}
                        onChange={(e) => setNewComment(e.target.value)}
                    />
                </Modal.Content>
                <Modal.Actions>
                    <Button role='cancel' onClick={() => setAddOpen(false)}>Cancel</Button>
                    <Button
                        role='save'
                        icon='plus'
                        disabled={!newName.trim() || actionLoading}
                        loading={actionLoading}
                        onClick={handleAddShare}
                    >
                        Add Share
                    </Button>
                </Modal.Actions>
            </Modal>
        </Panel>
    );
}


// Human labels for the hotspot protocols reported by the Controller.
const hotspotProtocolLabels = {
    wpa2: 'WPA2 (most compatible)',
    wpa3: 'WPA3',
};

function HotspotSettingsForm() {
    const dockerized = useDockerized();
    const [devices, setDevices] = React.useState([]);
    const [protocols, setProtocols] = React.useState([]);
    const [form, setForm] = React.useState({device: '', ssid: '', password: '', protocol: ''});
    const [loading, setLoading] = React.useState(true);
    const [saving, setSaving] = React.useState(false);
    const [qrOpen, setQrOpen] = React.useState(false);

    React.useEffect(() => {
        const fetchSettings = async () => {
            try {
                const [settings, devicesResponse] = await Promise.all([getHotspotSettings(), getHotspotDevices()]);
                setForm({
                    device: settings.device,
                    ssid: settings.ssid,
                    password: settings.password,
                    protocol: settings.protocol,
                });
                setDevices(devicesResponse.devices || []);
            } catch (e) {
                console.error('Failed to fetch hotspot settings', e);
            } finally {
                setLoading(false);
            }
        };
        fetchSettings();
    }, []);

    // The supported protocols depend on the selected device's hardware.
    React.useEffect(() => {
        if (!form.device) {
            return;
        }
        // Ignore out-of-order responses when the user switches devices quickly.
        let cancelled = false;
        const fetchProtocols = async () => {
            try {
                const response = await getHotspotProtocols(form.device);
                if (cancelled) {
                    return;
                }
                const supported = response.protocols || [];
                setProtocols(supported);
                // Reset a selection the probed device does not support (e.g. WPA3 kept
                // after switching to a WPA2-only adapter).
                if (supported.length) {
                    setForm(f => supported.includes(f.protocol) ? f : {...f, protocol: supported[0]});
                }
            } catch (e) {
                if (!cancelled) {
                    console.error('Failed to fetch hotspot protocols', e);
                    setProtocols([]);
                }
            }
        };
        fetchProtocols();
        return () => {
            cancelled = true;
        };
    }, [form.device]);

    const handleSave = async () => {
        setSaving(true);
        try {
            const settings = await updateHotspotSettings(form);
            setForm(settings);
            toast({type: 'success', title: 'Hotspot settings saved', time: 3000});
        } catch (e) {
            toast({type: 'error', title: 'Failed to save hotspot settings', description: e.message, time: 5000});
        } finally {
            setSaving(false);
        }
    };

    if (loading) {
        return <Panel>
            <Header as='h4' icon='wifi'>Hotspot Settings</Header>
            <Loading size='xs'/>
        </Panel>;
    }

    // Keep the saved device selectable even if it is not currently present
    // (e.g. a USB WiFi dongle is unplugged).
    const deviceOptions = [...new Set([...devices, form.device].filter(Boolean))]
        .map(device => ({value: device, label: device}));

    // Keep the saved protocol selectable even if the device does not report it.
    const protocolOptions = [...new Set([...protocols, form.protocol].filter(Boolean))]
        .map(protocol => ({value: protocol, label: hotspotProtocolLabels[protocol] || protocol}));

    // Special string which allows a mobile device to connect to a specific Wi-Fi.
    // The WPA QR format requires backslash-escaping of \ ; , " in the SSID and password.
    const escapeWifi = (s) => s.replace(/([\\;,"])/g, '\\$1');
    const qrCodeValue = `WIFI:S:${escapeWifi(form.ssid)};T:WPA;P:${escapeWifi(form.password)};;`;

    return <Panel>
        <Header as='h4' icon='wifi'>Hotspot Settings</Header>
        <Group grow align='flex-start'>
            <TextInput
                label='Hotspot SSID'
                value={form.ssid}
                disabled={dockerized || saving}
                onChange={(e) => setForm({...form, ssid: e.target.value})}
            />
            <TextInput
                label='Hotspot Password'
                value={form.password}
                disabled={dockerized || saving}
                onChange={(e) => setForm({...form, password: e.target.value})}
            />
            <Select
                label='Hotspot Device'
                placeholder='No WiFi devices found'
                data={deviceOptions}
                value={form.device}
                disabled={dockerized || saving}
                onChange={(value) => setForm({...form, device: value})}
            />
            <Select
                label='Hotspot Protocol'
                placeholder='No protocols supported'
                data={protocolOptions}
                value={form.protocol}
                disabled={dockerized || saving}
                onChange={(value) => setForm({...form, protocol: value})}
            />
        </Group>
        <div className='wrolpi-button-row' style={{marginTop: '0.8em'}}>
            <Button
                color='violet'
                disabled={dockerized}
                loading={saving}
                onClick={handleSave}
            >Save</Button>
            <IconButton
                icon='qrcode'
                label='Scan this code to join the hotspot'
                color='violet'
                onClick={() => setQrOpen(true)}
            />
            <Modal size='small' open={qrOpen} onClose={() => setQrOpen(false)} closeIcon>
                <Modal.Header>Scan this code to join the hotspot</Modal.Header>
                <Modal.Content>
                    {/* `media`: filtered as a unit by night mode; a QR code needs real black-on-white
                        contrast to scan, so it is exempted the same way DonatePage's and Share's are. */}
                    <div className='media'
                         style={{display: 'inline-block', backgroundColor: '#ffffff', padding: '1em'}}>
                        <QRCode value={qrCodeValue} size={300}/>
                    </div>
                </Modal.Content>
            </Modal>
        </div>
    </Panel>;
}

function AdminControlsSection() {
    const dockerized = useDockerized();

    return (
        <Panel>
            <Header as='h3' icon='settings'>Hardware Controls</Header>

            <HotspotToggle/>
            <BluetoothToggle/>
            <DesktopToggle/>
            <VncToggle/>
            <ThrottleToggle/>

            <HotspotSettingsForm/>

            {!dockerized && (
                <div className='wrolpi-button-row' style={{marginTop: '1em'}}>
                    <RestartButton/>
                    <ShutdownButton/>
                </div>
            )}
        </Panel>
    );
}

export function ControllerPage() {
    return (
        // `wrolpi-stack`: these four sections are panels held in a wrapper of this page's own,
        // so the stack on PageContainer does not reach them -- the same hole Settings had.
        <div className='wrolpi-stack'>
            <AdminControlsSection/>
            <ServicesSection/>
            <SambaSection/>
            <DiskSection/>
        </div>
    );
}

export default ControllerPage;
