import React from "react";
import {SettingsContext, StatusContext} from "../../contexts/contexts";
import {cancelBackup, cancelSync, runBackup, runSync, saveSyncSettings, testSync} from "../../api";
import {getDisks} from "../../api/controller";
import {humanFileSize, isoDatetimeToAgoPopup, useTitle} from "../Common";
import {Link} from "react-router";
import {useDockerized, useSyncRole, useWROLMode} from "../../hooks/customHooks";
import {Button, Header, Message, Panel, Progress, Select, TextInput, toast} from "../ui";

const roleOptions = [
    {value: 'primary', label: 'Primary'},
    {value: 'secondary', label: 'Secondary'},
];

/** The sync's progress: how many of the primary's FileGroups have been compared. */
function syncPercent(sync) {
    if (!sync || !sync.max_id) {
        return 0;
    }
    // FileGroup ids are not contiguous; `groups_seen / max_id` underestimates, it never overshoots.
    return Math.min(100, Math.round(100 * sync.groups_seen / sync.max_id));
}

function syncProgressLabel(sync) {
    const downloaded = `${sync.files_downloaded} / ${sync.files_to_download} files`;
    return `${sync.phase === 'configs' ? 'Importing configs' : downloaded} (${humanFileSize(sync.bytes_downloaded)})`;
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

/** The progress and outcome of a secondary's sync. */
export function SyncStatus({sync, running}) {
    if (!sync) {
        return null;
    }
    return <div>
        {running && <Progress percent={syncPercent(sync)} label={syncProgressLabel(sync)}/>}
        <p>
            <b>Last successful sync:</b> {sync.last_success_at ? isoDatetimeToAgoPopup(sync.last_success_at) : 'Never'}
        </p>
        {!running && sync.finished_at && <p>
            <b>Last sync:</b> {sync.files_downloaded} files downloaded
            ({humanFileSize(sync.bytes_downloaded)}), {sync.files_failed} failed
        </p>}
        {sync.disk_full && <Message kind='error' icon='hdd' title='The drive is full'>
            Some files were not synced because the drive is nearly full.
        </Message>}
        {sync.last_error && !running && <Message kind='error' icon='warning' title='Sync problem'>
            {sync.last_error}
        </Message>}
        {sync.last_skip_reason && !running && <p style={{color: 'var(--muted)'}}>
            Not synced: {sync.last_skip_reason}
        </p>}
    </div>
}

/** Covers the app while a secondary syncs; its API refuses requests until the sync finishes. */
export function SyncingOverlay() {
    const {status} = React.useContext(StatusContext);
    const role = useSyncRole();
    const running = role === 'secondary' && status?.flags?.sync_running === true;

    if (!running) {
        return null;
    }
    return <div className='wrolpi-sync-overlay' role='alertdialog' aria-modal='true' aria-label='Syncing'
                style={{
                    position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center',
                    justifyContent: 'center', padding: 16, background: 'rgba(0, 0, 0, 0.6)',
                }}>
        <SyncingPanel sync={status.sync} onCancel={cancelSync}/>
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
        <Progress percent={syncPercent(sync)} label={sync ? syncProgressLabel(sync) : null}/>
        <Button color='red' onClick={onCancel} style={{marginTop: '1em'}}>Stop Sync</Button>
    </Panel>
}

/** The Settings panel: this WROLPi's role, and (for a secondary) its primary and sync window. */
export function SyncSection() {
    const {settings, fetchSettings} = React.useContext(SettingsContext);
    const {status} = React.useContext(StatusContext);
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
    React.useEffect(() => {
        if (loaded) {
            setState({
                role: role || 'primary',
                sync_primary_url: primaryUrl || '',
                sync_window_start: windowStart || '',
                sync_window_end: windowEnd || '',
            });
        }
    }, [loaded, role, primaryUrl, windowStart, windowEnd]);

    if (!settings) {
        return null;
    }

    const secondary = state.role === 'secondary';
    const saved = secondary && settings.role === 'secondary' && settings.sync_primary_url;
    const running = status?.flags?.sync_running === true;

    const save = async () => {
        setSaving(true);
        try {
            const response = await saveSyncSettings(state);
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
        const response = await runSync();
        if (response?.ok) {
            toast({type: 'info', title: 'Sync requested', description: 'The sync starts in a few seconds.', time: 3000});
        }
    };

    return <Panel>
        <Header as='h3' icon='copy'>Sync</Header>
        <p>
            A <b>secondary</b> WROLPi keeps a copy of a <b>primary</b> WROLPi's library: its files, tags,
            channels, domains, playlists, and other library settings. Files deleted on the primary are kept.
        </p>
        <div style={{margin: '0.5em 0', maxWidth: '20em'}}>
            <label><b>This WROLPi is</b></label>
            <Select data={roleOptions} value={state.role} allowDeselect={false} disabled={wrolMode}
                    onChange={value => setState({...state, role: value})}/>
        </div>

        {secondary && <>
            <Message kind='warning' icon='warning' title='A secondary is overwritten'>
                Every sync replaces this WROLPi's library with the primary's; changes made here are lost.
                It does not download, and it is unavailable while it syncs.
            </Message>
            <div style={{margin: '0.5em 0', maxWidth: '30em'}}>
                <label><b>Primary address</b></label>
                <TextInput placeholder='https://192.168.0.10' value={state.sync_primary_url} disabled={wrolMode}
                           onChange={e => setState({...state, sync_primary_url: e.currentTarget.value})}/>
            </div>
        </>}

        {(secondary || settings.backup_directory) && <>
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
                Within the window, a secondary syncs every 15 minutes, and the backup drive is updated every hour.
                Leave both empty to sync only with "Sync Now" and "Back Up Now".
            </p>
        </>}

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

        {settings.role === 'secondary' && <SyncStatus sync={status?.sync} running={running}/>}
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

/** The progress and outcome of copying the media directory to the backup drive. */
export function BackupStatus({backup, running}) {
    if (!backup) {
        return null;
    }
    return <div>
        {running && <Progress percent={backup.percent}
                              label={`${backup.phase === 'database' ? 'Copying the database'
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
    const [directory, setDirectory] = React.useState('');
    const [saving, setSaving] = React.useState(false);

    const savedDirectory = settings?.backup_directory || '';
    React.useEffect(() => {
        setDirectory(savedDirectory);
    }, [savedDirectory]);

    React.useEffect(() => {
        if (dockerized === false) {
            getDisks().then(setDisks).catch(e => setDisksError(e.message));
        }
    }, [dockerized]);

    if (!settings || dockerized !== false) {
        // Docker cannot reach other drives.
        return null;
    }

    const options = backupDriveOptions(disks, settings.media_directory);
    if (savedDirectory && !options.find(i => i.value === savedDirectory)) {
        // The chosen drive is unplugged; keep showing it.
        options.push({value: savedDirectory, uuid: settings.backup_device_uuid,
            label: `${savedDirectory} (not mounted)`});
    }
    const data = [{value: 'none', label: 'None'}, ...options.map(({value, label}) => ({value, label}))];
    const running = status?.flags?.backup_running === true;

    const save = async () => {
        setSaving(true);
        try {
            const chosen = options.find(i => i.value === directory);
            const response = await saveSyncSettings({
                backup_directory: chosen ? chosen.value : '',
                backup_device_uuid: chosen ? chosen.uuid : '',
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
            fails. Files deleted here are kept on the backup drive. The backup runs during the sync window.
        </p>
        {disksError && <Message kind='error' icon='warning' title='Could not list drives'>{disksError}</Message>}
        <div style={{margin: '0.5em 0', maxWidth: '30em'}}>
            <label><b>Backup drive</b></label>
            <Select data={data} value={directory || 'none'} allowDeselect={false} disabled={wrolMode}
                    onChange={value => setDirectory(value === 'none' ? '' : value)}/>
        </div>
        <div style={{display: 'flex', gap: '0.5em', flexWrap: 'wrap'}}>
            <Button color='violet' onClick={save} disabled={wrolMode || saving}>Save</Button>
            {savedDirectory && !running && <Button onClick={backUpNow} disabled={wrolMode}>Back Up Now</Button>}
            {running && <Button color='red' onClick={cancelBackup}>Stop Backup</Button>}
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
