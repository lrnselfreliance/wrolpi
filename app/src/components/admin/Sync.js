import React from "react";
import {SettingsContext, StatusContext} from "../../contexts/contexts";
import {
    cancelBackup,
    getSyncDirectories,
    PrimaryUnreachableError,
    runBackup,
    saveSyncSettings,
    testSync
} from "../../api";
import {cancelSync, getDisks, getSyncStatus, runSync} from "../../api/controller";
import {humanFileSize, isoDatetimeToAgoPopup, useTitle} from "../Common";
import {Link} from "react-router";
import {useDockerized, useSyncRole, useWROLMode} from "../../hooks/customHooks";
import {
    Button,
    Checkbox,
    Header,
    Icon,
    IconButton,
    Message,
    Modal,
    Panel,
    Progress,
    Select,
    TextInput,
    toast
} from "../ui";

const roleOptions = [
    {value: 'primary', label: 'Primary'},
    {value: 'secondary', label: 'Secondary'},
];

// What each step of a sync is called (see controller/lib/sync.py).
const SYNC_PHASES = {
    checks: 'Checking the primary',
    snapshot: 'The primary is copying its database',
    files: 'Copying files',
    database: 'Copying the database',
    starting: 'Starting WROLPi',
    purge: 'Emptying the trash',
};

export function syncProgressLabel(sync) {
    const phase = SYNC_PHASES[sync?.phase] || 'Syncing';
    if (sync?.phase === 'files' || sync?.phase === 'database') {
        return `${phase}: ${humanFileSize(sync.bytes_transferred || 0)}`;
    }
    return phase;
}

// How often the sync's status is asked for, while one runs, and otherwise.
const SYNC_POLL_RUNNING_MS = 2000;
const SYNC_POLL_IDLE_MS = 10000;

/**
 * The sync's status, from the Controller: a secondary's API is stopped while it syncs, so the Controller is the
 * only one that can say how the sync is going.  Not asked for at all on a primary.
 */
export function useSyncStatus() {
    const role = useSyncRole();
    const [sync, setSync] = React.useState(null);
    // The settings (and the role) cannot be read while the API is stopped; a role that is not known yet may be a
    // secondary in the middle of a sync.
    const enabled = role !== 'primary';
    const running = sync?.state === 'running';

    const fetchSync = React.useCallback(async () => {
        try {
            setSync(await getSyncStatus());
        } catch (e) {
            // The Controller is restarting; ask again later.
        }
    }, []);

    React.useEffect(() => {
        if (!enabled) {
            setSync(null);
            return;
        }
        fetchSync();
        const interval = setInterval(fetchSync, running ? SYNC_POLL_RUNNING_MS : SYNC_POLL_IDLE_MS);
        return () => clearInterval(interval);
    }, [enabled, running, fetchSync]);

    return {sync, running, fetchSync};
}

async function stopSync() {
    try {
        await cancelSync();
    } catch (e) {
        toast({type: 'error', title: 'Could not stop the sync', description: e.message, time: 5000});
    }
}

/**
 * Shown on every page of a secondary WROLPi, so nobody mistakes it for the primary.  WROL Mode stops syncing,
 * so the warning goes away with it.
 */
export function SecondaryRoleMessage({content}) {
    const role = useSyncRole();
    const wrolMode = useWROLMode();
    const {settings} = React.useContext(SettingsContext);

    if (role !== 'secondary' || wrolMode) {
        return null;
    }
    return <SecondaryRoleNotice primaryUrl={settings?.sync_primary_url} content={content}/>
}

export function SecondaryRoleNotice({primaryUrl, content}) {
    return <Message kind='warning' icon='copy' title='Secondary WROLPi'>
        {content || <>
            This WROLPi is a copy of <b>{primaryUrl || 'its primary'}</b>. Every sync replaces its library with the
            primary's, so changes made here are lost. Do not use it as a primary. Enable WROL Mode to stop syncing.
            {' '}<Link to='/admin/sync'>Sync settings</Link>
        </>}
    </Message>
}

// A sync that was stopped on purpose is not a problem.
const STOPPED = ['The sync was cancelled', 'WROL Mode was enabled'];

/** The progress and outcome of a secondary's sync. */
export function SyncStatus({sync, running}) {
    if (!sync) {
        return null;
    }
    const stopped = STOPPED.includes(sync.last_error);
    return <div>
        {running && <Progress percent={sync.percent || 0} label={syncProgressLabel(sync)}/>}
        <p>
            <b>Last successful sync:</b> {sync.last_success_at ? isoDatetimeToAgoPopup(sync.last_success_at) : 'Never'}
        </p>
        {!running && sync.finished_at && <p>
            <b>Last sync:</b> {sync.files_transferred} files copied ({humanFileSize(sync.bytes_transferred || 0)}),
            {' '}{sync.files_deleted} moved to the trash
        </p>}
        {sync.trash_bytes > 0 && <p style={{color: 'var(--muted)'}}>
            The trash holds {humanFileSize(sync.trash_bytes)} of files the primary deleted or replaced.
        </p>}
        {!running && (sync.warnings || []).map(warning => <Message key={warning} kind='warning' icon='warning'
                                                                  title='Sync warning'>{warning}</Message>)}
        {sync.last_error && !running && (stopped
            ? <p style={{color: 'var(--muted)'}}>{sync.last_error}.</p>
            : <Message kind='error' icon='warning' title='Sync problem'>{sync.last_error}</Message>)}
    </div>
}

/** Covers the app while a secondary syncs; its API is stopped until the sync finishes. */
export function SyncingOverlay() {
    const {sync, running} = useSyncStatus();

    if (!running) {
        return null;
    }
    return <div className='wrolpi-sync-overlay' role='alertdialog' aria-modal='true' aria-label='Syncing'
                style={{
                    position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center',
                    justifyContent: 'center', padding: 16, background: 'rgba(0, 0, 0, 0.6)',
                }}>
        <SyncingPanel sync={sync} onCancel={stopSync}/>
    </div>
}

/** What the SyncingOverlay shows. */
export function SyncingPanel({sync, onCancel}) {
    return <Panel style={{maxWidth: '32em', width: '100%'}}>
        <Header as='h2' icon='sync'>Syncing from the primary</Header>
        <p>
            This WROLPi is copying the library of {sync?.primary_url || 'its primary'}. It is unavailable
            until the sync finishes.
        </p>
        <Progress percent={sync?.percent || 0} label={syncProgressLabel(sync)}/>
        <Button color='red' onClick={onCancel} style={{marginTop: '1em'}}>Stop Sync</Button>
    </Panel>
}

/** The Settings panel: this WROLPi's role, and (for a secondary) its primary and sync window. */
/** Is `path` an excluded folder, or inside one? */
export function isExcludedPath(path, excluded) {
    return (excluded || []).some(i => path === i || path.startsWith(`${i}/`));
}

/** Excluded folders without the ones already inside another excluded folder, sorted. */
export function simplifyExcluded(excluded) {
    const unique = Array.from(new Set(excluded || []));
    return unique.filter(i => !unique.some(j => j !== i && i.startsWith(`${j}/`))).sort();
}

function ExcludeFolderRow({folder, depth, source, chosen, onToggle}) {
    const [open, setOpen] = React.useState(false);
    const [children, setChildren] = React.useState(null);
    const [error, setError] = React.useState(null);

    const checked = chosen.has(folder.path);
    // A folder inside a chosen folder is excluded with it, whether or not it was chosen itself.
    const inherited = isExcludedPath(folder.path, Array.from(chosen).filter(i => i !== folder.path));

    const toggleOpen = async () => {
        if (!open && children === null) {
            try {
                setChildren(await getSyncDirectories(folder.path, source));
            } catch (e) {
                setError(e.message);
            }
        }
        setOpen(!open);
    };

    return <>
        <div style={{display: 'flex', alignItems: 'center', gap: '0.5em', paddingLeft: `${depth * 1.5}em`}}
             data-testid='exclude-folder-row'>
            <IconButton icon={open ? 'chevron down' : 'chevron right'} size='xs' onClick={toggleOpen}
                        label={`${open ? 'Close' : 'Open'} ${folder.name}`}/>
            <Checkbox checked={checked || inherited} disabled={inherited} aria-label={folder.path}
                      onChange={() => onToggle(folder.path)}
                      label={<span><Icon name='folder'/> {folder.name}</span>}/>
            {inherited && <span style={{color: 'var(--muted)', fontSize: '0.85em'}}>excluded with its parent</span>}
        </div>
        {open && error && <p style={{paddingLeft: `${(depth + 1) * 1.5}em`, color: 'var(--muted)'}}>{error}</p>}
        {open && children && children.length === 0 && <p
            style={{paddingLeft: `${(depth + 1) * 1.5 + 2}em`, color: 'var(--muted)', margin: 0}}>No folders</p>}
        {open && children && children.map(child => <ExcludeFolderRow key={child.path} folder={child} depth={depth + 1}
                                                                     source={source} chosen={chosen}
                                                                     onToggle={onToggle}/>)}
    </>
}

/** Choose folders in a tree; `source` is 'local' (this WROLPi's media directory) or 'primary'. */
export function ExcludeFolderModal({open, onClose, value, onSubmit, source}) {
    const [chosen, setChosen] = React.useState(new Set());
    const [folders, setFolders] = React.useState(null);
    const [error, setError] = React.useState(null);

    React.useEffect(() => {
        if (!open) {
            return;
        }
        setChosen(new Set(value || []));
        setFolders(null);
        setError(null);
        getSyncDirectories('', source)
            .then(setFolders)
            .catch(e => setError(e instanceof PrimaryUnreachableError
                ? `The primary did not answer: ${e.message}` : e.message));
    }, [open, source, value]);

    const onToggle = path => {
        const next = new Set(chosen);
        next.has(path) ? next.delete(path) : next.add(path);
        setChosen(next);
    };

    return <Modal open={open} onClose={onClose}>
        <Modal.Header>{source === 'primary' ? "Exclude the primary's folders" : 'Exclude folders'}</Modal.Header>
        <Modal.Content>
            <p>Checked folders, and everything inside them, are not copied.</p>
            {error && <Message kind='error' icon='warning' title='Could not list the folders'>{error}</Message>}
            {!error && folders === null && <p>Loading folders...</p>}
            {folders && folders.length === 0 && <p>No folders</p>}
            {folders && folders.map(folder => <ExcludeFolderRow key={folder.path} folder={folder} depth={0}
                                                                source={source} chosen={chosen}
                                                                onToggle={onToggle}/>)}
        </Modal.Content>
        <Modal.Actions>
            <Button role='cancel' style={{marginRight: 'auto'}} onClick={onClose}>Cancel</Button>
            <Button color='violet' onClick={() => onSubmit(simplifyExcluded(Array.from(chosen)))}>Done</Button>
        </Modal.Actions>
    </Modal>
}

/** The folders a sync or a backup does not copy, and the button that chooses them. */
export function ExcludedDirectories({value, onChange, source, disabled, note}) {
    const [open, setOpen] = React.useState(false);
    const excluded = value || [];
    return <div style={{margin: '0.5em 0'}}>
        <label><b>Excluded folders</b></label>
        {excluded.length === 0
            ? <p style={{color: 'var(--muted)', margin: '0.25em 0'}}>Nothing excluded; every folder is copied.</p>
            : <ul style={{listStyle: 'none', padding: 0, margin: '0.25em 0'}}>
                {excluded.map(path => <li key={path} style={{display: 'flex', alignItems: 'center', gap: '0.5em'}}>
                    <Icon name='folder'/> <span>{path}</span>
                    <IconButton icon='close' size='xs' label={`Copy ${path} again`} disabled={disabled}
                                onClick={() => onChange(excluded.filter(i => i !== path))}/>
                </li>)}
            </ul>}
        <Button icon='folder open' onClick={() => setOpen(true)} disabled={disabled}>Choose Folders</Button>
        <p style={{color: 'var(--muted)', fontSize: '0.9em'}}>
            Files already copied into an excluded folder are kept; delete them yourself to free space.
            {note && <> {note}</>}
        </p>
        <ExcludeFolderModal open={open} onClose={() => setOpen(false)} value={excluded} source={source}
                            onSubmit={chosen => {
                                onChange(chosen);
                                setOpen(false);
                            }}/>
    </div>
}

/** True if `days` (a number, or the text of the days box) is a whole number of days. */
export function validDays(days) {
    return /^\d+$/.test(String(days ?? '').trim());
}

/**
 * How long deleted files wait in a trash folder before they are removed; `value` null is "never".  An empty box is
 * not "delete at once": callers refuse to save it (see `validDays`).
 */
export function DeleteDelay({label, value, onChange, disabled, description}) {
    const never = value === null;
    return <div style={{margin: '0.5em 0'}}>
        <label><b>{label}</b></label>
        <div style={{display: 'flex', gap: '1em', alignItems: 'center', flexWrap: 'wrap'}}>
            <span style={{display: 'flex', gap: '0.5em', alignItems: 'center'}}>
                Delete after
                <TextInput type='number' min={0} max={3650} style={{width: '6em'}} aria-label={`${label}: days`}
                           value={never ? '' : value} disabled={disabled || never}
                           onChange={e => onChange(e.currentTarget.value)}/>
                days
            </span>
            <Checkbox checked={never} disabled={disabled} label='Never delete them'
                      aria-label={`${label}: never delete them`} onChange={() => onChange(never ? 30 : null)}/>
        </div>
        <p style={{color: 'var(--muted)', fontSize: '0.9em'}}>{description}</p>
    </div>
}

export function SyncSection() {
    const {settings, fetchSettings} = React.useContext(SettingsContext);
    const {sync, running, fetchSync} = useSyncStatus();
    const wrolMode = useWROLMode();
    const [state, setState] = React.useState({});
    const [testResult, setTestResult] = React.useState(null);
    const [saving, setSaving] = React.useState(false);

    // Only these values reset the form; the settings are re-fetched while the user types.
    const loaded = Boolean(settings);
    const role = settings?.role;
    const primaryUrl = settings?.sync_primary_url;
    const windowStart = settings?.sync_window_start;
    const windowEnd = settings?.sync_window_end;
    const excludedKey = JSON.stringify(settings?.sync_excluded_directories || []);
    const deleteAfterDays = settings?.sync_delete_after_days;
    React.useEffect(() => {
        if (loaded) {
            setState({
                role: role || 'primary',
                sync_primary_url: primaryUrl || '',
                sync_window_start: windowStart || '',
                sync_window_end: windowEnd || '',
                sync_excluded_directories: JSON.parse(excludedKey),
                // null: never delete.
                sync_delete_after_days: deleteAfterDays === undefined ? 30 : deleteAfterDays,
            });
        }
    }, [loaded, role, primaryUrl, windowStart, windowEnd, excludedKey, deleteAfterDays]);

    if (!settings) {
        return null;
    }

    const secondary = state.role === 'secondary';
    const saved = secondary && settings.role === 'secondary' && settings.sync_primary_url;
    const neverDelete = state.sync_delete_after_days === null;

    const save = async () => {
        // An empty box is not "delete at once": that would empty the trash at the next sync.
        const days = String(state.sync_delete_after_days ?? '').trim();
        if (secondary && !neverDelete && !validDays(days)) {
            toast({
                type: 'error', title: 'Sync settings were not saved', time: 5000,
                description: 'Enter how many days to keep deleted files, or choose to never delete them.',
            });
            return;
        }
        setSaving(true);
        try {
            // The API takes -1 for "never".
            const response = await saveSyncSettings({
                ...state, sync_delete_after_days: neverDelete ? -1 : Number(days),
            });
            if (response?.ok) {
                toast({type: 'success', title: 'Sync settings saved', time: 3000});
                setTestResult(null);
            }
            await fetchSettings();
        } finally {
            setSaving(false);
        }
    };

    const test = async () => {
        setTestResult(await testSync());
    };

    const syncNow = async () => {
        try {
            await runSync();
            toast({type: 'info', title: 'Sync started', time: 3000});
            await fetchSync();
        } catch (e) {
            toast({type: 'error', title: 'The sync did not start', description: e.message, time: 5000});
        }
    };

    return <Panel>
        <Header as='h3' icon='copy'>Sync</Header>
        <p>
            A <b>secondary</b> WROLPi keeps a copy of a <b>primary</b> WROLPi's library: all of its files (maps
            and repositories too), its database, tags, channels, playlists, and other library settings.
        </p>
        <div style={{margin: '0.5em 0', maxWidth: '20em'}}>
            <label><b>This WROLPi is</b></label>
            <Select data={roleOptions} value={state.role} allowDeselect={false} disabled={wrolMode}
                    onChange={value => setState({...state, role: value})}/>
        </div>

        {secondary && <>
            <Message kind='warning' icon='warning' title='A secondary is overwritten'>
                Every sync replaces this WROLPi's library and database with the primary's; changes made here are
                lost. It does not download, and it is unavailable while it syncs. Both WROLPis must run the same
                version.
            </Message>
            <div style={{margin: '0.5em 0', maxWidth: '30em'}}>
                <label><b>Primary address</b></label>
                <TextInput placeholder='https://192.168.0.10' value={state.sync_primary_url} disabled={wrolMode}
                           onChange={e => setState({...state, sync_primary_url: e.currentTarget.value})}/>
            </div>
        </>}

        {secondary && <>
            <div style={{display: 'flex', gap: '1em', flexWrap: 'wrap', margin: '0.5em 0'}}>
                <div>
                    <label><b>Sync Window Start</b></label>
                    <TextInput type='time' value={state.sync_window_start} disabled={wrolMode}
                               onChange={e => setState({...state, sync_window_start: e.currentTarget.value})}/>
                </div>
                <div>
                    <label><b>Sync Window End</b></label>
                    <TextInput type='time' value={state.sync_window_end} disabled={wrolMode}
                               onChange={e => setState({...state, sync_window_end: e.currentTarget.value})}/>
                </div>
            </div>
            <p style={{color: 'var(--muted)', fontSize: '0.9em'}}>
                Within the window, this secondary syncs every 15 minutes. Leave both empty to sync only with
                "Sync Now".
            </p>
            <DeleteDelay label='Files the primary deletes' value={state.sync_delete_after_days} disabled={wrolMode}
                         onChange={value => setState({...state, sync_delete_after_days: value})}
                         description={<>A file the primary deletes, or the old version of one it changes, waits in a
                             trash folder (<code>.sync-trash</code>) for this long. It is removed sooner if the drive
                             is nearly full.</>}/>
        </>}

        {/* The primary's folders can only be listed once this WROLPi knows its primary. */}
        {secondary && saved && <ExcludedDirectories value={state.sync_excluded_directories} source='primary'
                                                    disabled={wrolMode}
                                                    note="This WROLPi's database is the primary's, so the files of an
                                                    excluded folder are still listed here; they do not open."
                                                    onChange={value => setState({
                                                        ...state,
                                                        sync_excluded_directories: value
                                                    })}/>}

        <div style={{display: 'flex', gap: '0.5em', flexWrap: 'wrap'}}>
            <Button color='violet' onClick={save} disabled={wrolMode || saving}>Save</Button>
            {saved && <Button onClick={test} disabled={wrolMode}>Test Connection</Button>}
            {saved && <Button onClick={syncNow} disabled={wrolMode || running}>Sync Now</Button>}
        </div>

        {testResult && (testResult.ok
            ? <Message kind='success' icon='check' title='The primary answered'>
                WROLPi {testResult.info?.version} at {settings.sync_primary_url}
            </Message>
            : <Message kind='error' icon='warning' title='The primary did not answer'>{testResult.error}</Message>)}

        {wrolMode && settings.role === 'secondary' && <Message kind='info' icon='lock' title='Syncing is stopped'>
            WROL Mode is enabled; this WROLPi does not sync.
        </Message>}

        {settings.role === 'secondary' && <SyncStatus sync={sync} running={running}/>}
    </Panel>
}


/** The drives a backup can be written to: mounted under /media, and not the media drive. */
export function backupDriveOptions(disks, mediaDirectory) {
    const media = mediaDirectory || '/media/wrolpi';
    return (disks || [])
        .filter(d => d.mountpoint && d.uuid && d.mountpoint.startsWith('/media/')
            && d.mountpoint !== media && d.mountpoint !== '/media/wrolpi_temp_onboarding')
        .map(d => ({value: d.mountpoint, uuid: d.uuid, label: `${d.label || d.name} (${d.size}) at ${d.mountpoint}`}));
}

/** Split a saved backup directory into the drive it is on (its option) and the folder on that drive. */
export function splitBackupDirectory(directory, uuid, options) {
    if (!directory) {
        return {drive: '', folder: ''};
    }
    const onDrive = options.filter(i => directory === i.value || directory.startsWith(`${i.value}/`));
    // The drive with the saved UUID, else the deepest mount point that holds the directory.
    const drive = onDrive.find(i => i.uuid === uuid)
        || onDrive.sort((a, b) => b.value.length - a.value.length)[0];
    if (!drive) {
        return {drive: directory, folder: ''};
    }
    return {drive: drive.value, folder: directory.slice(drive.value.length).replace(/^\/+/, '')};
}

/** The progress and outcome of copying the media directory to the backup drive. */
export function BackupStatus({backup, running}) {
    if (!backup) {
        return null;
    }
    return <div>
        {running && <Progress percent={backup.percent}
                              label={`${backup.phase === 'database' ? 'Copying the database (this finishes first)'
                                  : `${backup.files_transferred} files`} (${humanFileSize(backup.bytes_transferred)})`}/>}
        <p>
            <b>Last successful backup:</b> {backup.last_success_at
            ? isoDatetimeToAgoPopup(backup.last_success_at) : 'Never'}
        </p>
        {backup.last_error && !running && <Message kind='error' icon='warning' title='Backup problem'>
            {backup.last_error}
        </Message>}
        {backup.last_skip_reason && !running && <p style={{color: 'var(--muted)'}}>
            Not backed up: {backup.last_skip_reason}
        </p>}
    </div>
}

/** The Sync tab's backup drive: a second drive this WROLPi copies its media directory to. */
export function BackupDriveSection() {
    const {settings, fetchSettings} = React.useContext(SettingsContext);
    const {status} = React.useContext(StatusContext);
    const wrolMode = useWROLMode();
    const dockerized = useDockerized();
    const [disks, setDisks] = React.useState(null);
    const [disksError, setDisksError] = React.useState(null);
    const [drive, setDrive] = React.useState('');
    const [folder, setFolder] = React.useState('');
    const [windowStart, setWindowStart] = React.useState('');
    const [windowEnd, setWindowEnd] = React.useState('');
    const [excluded, setExcluded] = React.useState([]);
    const [deleteAfterDays, setDeleteAfterDays] = React.useState(30);
    const [saving, setSaving] = React.useState(false);

    const savedDirectory = settings?.backup_directory || '';
    const savedUuid = settings?.backup_device_uuid || '';
    const options = backupDriveOptions(disks, settings?.media_directory);
    const saved = splitBackupDirectory(savedDirectory, savedUuid, options);
    React.useEffect(() => {
        setDrive(saved.drive);
        setFolder(saved.folder);
    }, [saved.drive, saved.folder]);

    const savedWindowStart = settings?.backup_window_start || '';
    const savedWindowEnd = settings?.backup_window_end || '';
    React.useEffect(() => {
        setWindowStart(savedWindowStart);
        setWindowEnd(savedWindowEnd);
    }, [savedWindowStart, savedWindowEnd]);

    const savedExcluded = JSON.stringify(settings?.backup_excluded_directories || []);
    React.useEffect(() => {
        setExcluded(JSON.parse(savedExcluded));
    }, [savedExcluded]);

    // null: never delete.
    const savedDeleteAfterDays = settings?.backup_delete_after_days;
    React.useEffect(() => {
        setDeleteAfterDays(savedDeleteAfterDays === undefined ? 30 : savedDeleteAfterDays);
    }, [savedDeleteAfterDays]);

    React.useEffect(() => {
        if (dockerized === false) {
            getDisks().then(setDisks).catch(e => setDisksError(e.message));
        }
    }, [dockerized]);

    if (!settings || dockerized !== false) {
        // Docker cannot reach other drives.
        return null;
    }

    if (saved.drive && !options.find(i => i.value === saved.drive)) {
        // The chosen drive is unplugged; keep showing it.
        options.push({value: saved.drive, uuid: savedUuid, label: `${saved.drive} (not mounted)`});
    }
    const data = [{value: 'none', label: 'None'}, ...options.map(({value, label}) => ({value, label}))];
    const running = status?.flags?.backup_running === true;

    const save = async () => {
        if (drive && deleteAfterDays !== null && !validDays(deleteAfterDays)) {
            toast({
                type: 'error', title: 'Backup drive was not saved', time: 5000,
                description: 'Enter how many days to keep deleted files, or choose to never delete them.',
            });
            return;
        }
        setSaving(true);
        try {
            const chosen = options.find(i => i.value === drive);
            const cleanFolder = folder.trim().replace(/^\/+|\/+$/g, '');
            const response = await saveSyncSettings({
                backup_directory: chosen ? (cleanFolder ? `${chosen.value}/${cleanFolder}` : chosen.value) : '',
                backup_device_uuid: chosen ? chosen.uuid : '',
                backup_window_start: chosen ? windowStart : '',
                backup_window_end: chosen ? windowEnd : '',
                backup_excluded_directories: excluded,
                // The API takes -1 for "never".
                backup_delete_after_days: deleteAfterDays === null ? -1 : Number(String(deleteAfterDays).trim()),
            });
            if (response?.ok) {
                toast({type: 'success', title: 'Backup drive saved', time: 3000});
            }
            await fetchSettings();
        } finally {
            setSaving(false);
        }
    };

    const backUpNow = async () => {
        const response = await runBackup();
        if (response?.ok) {
            toast({type: 'info', title: 'Backup requested', description: 'The backup starts in a few seconds.',
                time: 3000});
        }
    };

    return <Panel>
        <Header as='h3' icon='hdd'>Backup Drive</Header>
        <p>
            Copy this WROLPi's media directory to a second drive, so the drive can replace the media drive if it
            fails. A file deleted here, or the old version of one that changes, is kept on the backup drive for as
            long as you choose below.
        </p>
        {disksError && <Message kind='error' icon='warning' title='Could not list drives'>{disksError}</Message>}
        <div style={{margin: '0.5em 0', maxWidth: '30em'}}>
            <label><b>Backup drive</b></label>
            <Select data={data} value={drive || 'none'} allowDeselect={false} disabled={wrolMode}
                    onChange={value => setDrive(value === 'none' ? '' : value)}/>
        </div>
        {drive && <div style={{margin: '0.5em 0', maxWidth: '30em'}}>
            <label><b>Folder on the drive</b></label>
            <TextInput placeholder='The whole drive' value={folder} disabled={wrolMode}
                       onChange={e => setFolder(e.currentTarget.value)}/>
            <p style={{color: 'var(--muted)', fontSize: '0.9em'}}>
                The media directory is copied into this folder; leave it empty to use the whole drive.
            </p>
        </div>}
        {drive && <>
            <div style={{display: 'flex', gap: '1em', flexWrap: 'wrap', margin: '0.5em 0'}}>
                <div>
                    <label><b>Backup Window Start</b></label>
                    <TextInput type='time' value={windowStart} disabled={wrolMode} aria-label='Backup Window Start'
                               onChange={e => setWindowStart(e.currentTarget.value)}/>
                </div>
                <div>
                    <label><b>Backup Window End</b></label>
                    <TextInput type='time' value={windowEnd} disabled={wrolMode} aria-label='Backup Window End'
                               onChange={e => setWindowEnd(e.currentTarget.value)}/>
                </div>
            </div>
            <p style={{color: 'var(--muted)', fontSize: '0.9em'}}>
                Within the window, the backup drive is updated every hour. Leave both empty to back up only with
                "Back Up Now".
            </p>
            <DeleteDelay label='Files deleted here' value={deleteAfterDays} onChange={setDeleteAfterDays}
                         disabled={wrolMode}
                         description={<>A file deleted from this WROLPi, or the old version of one that changes,
                             waits on the backup drive in a trash folder (<code>.backup-trash</code>) for this long.
                             It is removed sooner if the backup drive is nearly full.</>}/>
            <ExcludedDirectories value={excluded} onChange={setExcluded} source='local' disabled={wrolMode}/>
        </>}
        <div style={{display: 'flex', gap: '0.5em', flexWrap: 'wrap'}}>
            <Button color='violet' onClick={save} disabled={wrolMode || saving}>Save</Button>
            {savedDirectory && !running && <Button onClick={backUpNow} disabled={wrolMode}>Back Up Now</Button>}
            {/* The database snapshot runs to the end; a half-written database is worse than waiting for it. */}
            {running && <Button color='red' onClick={cancelBackup} disabled={status?.backup?.phase === 'database'}>
                Stop Backup
            </Button>}
        </div>
        {savedDirectory && <BackupStatus backup={status?.backup} running={running}/>}
    </Panel>
}

/** The Sync tab of /admin. */
export function SyncPage() {
    useTitle('Sync');
    return <div className='wrolpi-stack'>
        <SecondaryRoleMessage/>
        <SyncSection/>
        <BackupDriveSection/>
    </div>
}
