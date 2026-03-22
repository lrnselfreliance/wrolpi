import {APIButton} from "../Common";
import {Button, Header, Icon, Loader, Modal, Popup, Table} from "../Theme";
import React, {useContext, useEffect, useState} from "react";
import {TableBody, TableCell, TableHeader, TableHeaderCell, TableRow} from "semantic-ui-react";
import {TableRowPlaceholder} from "../Placeholder";
import {getConfigText, getConfigBackups, postConfigBackupImport, postConfigBackupPreview} from "../../api";
import {ThemeContext} from "../../contexts/contexts";

function WarningIcon({ok}) {
    // null is empty, true is valid, false is invalid.
    const trigger = <Icon
        color={ok === true ? 'violet' : ok === false ? 'red' : 'grey'}
        name={ok === true ? 'check' : ok === false ? 'close' : 'check'}
    />;
    const content = ok === true ? 'Valid and can be imported.' : ok === false ? 'Invalid, can be overwritten.' : 'Empty config, can be overwritten.';
    return <Popup trigger={trigger} content={content}/>
}

const TYPE_LABELS = {
    tag: 'Tags',
    tag_file: 'Tag Files',
    tag_zim: 'Tag Zims',
    channel: 'Channels',
    domain: 'Domains',
    download: 'Downloads',
    inventory: 'Inventories',
};

const TYPE_COLUMNS = {
    tag: [{key: 'name', header: 'Name'}],
    tag_file: [{key: 'tag', header: 'Tag'}, {key: 'path', header: 'Path'}],
    tag_zim: [{key: 'tag', header: 'Tag'}, {key: 'zim', header: 'Zim'}, {key: 'entry', header: 'Entry'}],
    channel: [{key: 'name', header: 'Name'}, {key: 'directory', header: 'Directory'}],
    domain: [{key: 'name', header: 'Name'}, {key: 'directory', header: 'Directory'}],
    download: [{key: 'url', header: 'URL'}, {key: 'downloader', header: 'Downloader'}],
    inventory: [{key: 'name', header: 'Name'}],
};

function groupItemsByType(items) {
    const groups = {};
    for (const item of items) {
        if (!groups[item.type]) {
            groups[item.type] = [];
        }
        groups[item.type].push(item);
    }
    return Object.entries(groups).map(([type, items]) => ({
        type, label: TYPE_LABELS[type] || type, items,
    }));
}

function PreviewItemTable({items, negative, inverted}) {
    if (!items.length) return null;
    const columns = TYPE_COLUMNS[items[0].type] || [{key: 'type', header: 'Item'}];
    return <Table compact basic='very' size='small' inverted={!!inverted} style={{marginBottom: '0.5em'}}>
        <TableHeader>
            <TableRow>
                {columns.map(col => <TableHeaderCell key={col.key}>{col.header}</TableHeaderCell>)}
            </TableRow>
        </TableHeader>
        <TableBody>
            {items.map((item, i) => <TableRow key={i} negative={negative}>
                {columns.map(col =>
                    <TableCell key={col.key}>{item[col.key] || ''}</TableCell>
                )}
            </TableRow>)}
        </TableBody>
    </Table>;
}

const formatDate = (d) => d ? `${d.substring(0, 4)}-${d.substring(4, 6)}-${d.substring(6, 8)}` : '';

function BackupDateRow({date, previews, previewsLoaded, onSelect}) {
    const mergeLoaded = previewsLoaded?.merge;
    const overwriteLoaded = previewsLoaded?.overwrite;
    const mergePreview = previews?.merge;
    const overwritePreview = previews?.overwrite;

    const hasChanges = (p) => p && (p.add.length > 0 || p.remove.length > 0);
    const mergeHasChanges = hasChanges(mergePreview);
    const overwriteHasChanges = hasChanges(overwritePreview);

    let mergeCell;
    if (!mergeLoaded) {
        mergeCell = <Loader size='mini' active inline/>;
    } else if (mergePreview === null) {
        mergeCell = <Popup trigger={<Icon name='warning sign' color='red'/>} content='Failed to load preview'/>;
    } else if (mergeHasChanges) {
        mergeCell = <Button size='mini' color='green' onClick={() => onSelect(date, 'merge', mergePreview)}>
            <Icon name='plus'/> Merge
        </Button>;
    } else {
        mergeCell = <span style={{color: 'grey', fontStyle: 'italic'}}>No changes</span>;
    }

    let overwriteCell;
    if (!overwriteLoaded) {
        overwriteCell = <Loader size='mini' active inline/>;
    } else if (overwritePreview === null) {
        overwriteCell = <Popup trigger={<Icon name='warning sign' color='red'/>} content='Failed to load preview'/>;
    } else if (overwriteHasChanges) {
        overwriteCell = <Button size='mini' color='orange' onClick={() => onSelect(date, 'overwrite', overwritePreview)}>
            <Icon name='refresh'/> Overwrite
        </Button>;
    } else {
        overwriteCell = <span style={{color: 'grey', fontStyle: 'italic'}}>No changes</span>;
    }

    return <TableRow>
        <TableCell>{formatDate(date)}</TableCell>
        <TableCell>{mergeCell}</TableCell>
        <TableCell>{overwriteCell}</TableCell>
    </TableRow>;
}

function BackupsModal({open, onClose, fileName, fetchConfigs}) {
    const {inverted} = useContext(ThemeContext);
    const [dates, setDates] = useState([]);
    const [datesLoading, setDatesLoading] = useState(true);
    const [previews, setPreviews] = useState({});
    const [previewsLoaded, setPreviewsLoaded] = useState({});
    const [selectedAction, setSelectedAction] = useState(null); // {date, mode, preview}
    const [applying, setApplying] = useState(false);

    // Fetch backup dates on open.
    useEffect(() => {
        if (!open) return;
        let cancelled = false;
        setDatesLoading(true);
        setDates([]);
        setPreviews({});
        setPreviewsLoaded({});
        setSelectedAction(null);
        setApplying(false);

        getConfigBackups(fileName).then(result => {
            if (cancelled) return;
            setDates(result?.dates || []);
            setDatesLoading(false);
        });

        return () => { cancelled = true; };
    }, [open, fileName]);

    // Progressively fetch previews for each date, newest first.
    useEffect(() => {
        if (!open || dates.length === 0) return;
        let cancelled = false;

        const loadPreviews = async () => {
            for (const date of dates) {
                if (cancelled) break;

                const [mergeResult, overwriteResult] = await Promise.all([
                    postConfigBackupPreview(fileName, date, 'merge'),
                    postConfigBackupPreview(fileName, date, 'overwrite'),
                ]);
                if (cancelled) break;
                setPreviews(prev => ({
                    ...prev,
                    [date]: {merge: mergeResult?.preview || null, overwrite: overwriteResult?.preview || null}
                }));
                setPreviewsLoaded(prev => ({...prev, [date]: {merge: true, overwrite: true}}));
            }
        };

        loadPreviews();
        return () => { cancelled = true; };
    }, [open, dates, fileName]);

    const handleSelect = (date, mode, preview) => {
        setSelectedAction({date, mode, preview});
    };

    const handleApply = async () => {
        if (!selectedAction) return;
        setApplying(true);
        await postConfigBackupImport(fileName, selectedAction.date, selectedAction.mode);
        await fetchConfigs();
        setApplying(false);
        handleClose();
    };

    const handleBack = () => {
        setSelectedAction(null);
    };

    const handleClose = () => {
        onClose();
    };

    // Confirmation view: show the diff for the selected action.
    if (selectedAction) {
        const {date, mode, preview} = selectedAction;
        const modeLabel = mode === 'merge' ? 'Merge' : 'Overwrite';

        return <Modal open={open} onClose={handleClose} closeIcon size='large'>
            <Modal.Header>
                {modeLabel}: {fileName} ({formatDate(date)})
            </Modal.Header>
            <Modal.Content>
                {applying
                    ? <div style={{textAlign: 'center', padding: '2em'}}>
                        <Loader active inline='centered'>Applying backup...</Loader>
                    </div>
                    : <>
                        {preview.add.length > 0 && <>
                            <Header as='h4' color='green'>
                                <Icon name='plus'/> {preview.add.length} item{preview.add.length !== 1 ? 's' : ''} to add
                            </Header>
                            <div style={{maxHeight: '300px', overflowY: 'auto', marginBottom: '1em'}}>
                                {groupItemsByType(preview.add).map(group =>
                                    <React.Fragment key={group.type}>
                                        <Header as='h5' inverted={!!inverted}
                                                style={{marginBottom: '0.3em'}}>{group.label}</Header>
                                        <PreviewItemTable items={group.items} inverted={inverted}/>
                                    </React.Fragment>
                                )}
                            </div>
                        </>}

                        {preview.remove.length > 0 && <>
                            <Header as='h4' color='red'>
                                <Icon name='minus'/> {preview.remove.length} item{preview.remove.length !== 1 ? 's' : ''} to
                                remove
                            </Header>
                            <div style={{maxHeight: '300px', overflowY: 'auto', marginBottom: '1em'}}>
                                {groupItemsByType(preview.remove).map(group =>
                                    <React.Fragment key={group.type}>
                                        <Header as='h5' inverted={!!inverted}
                                                style={{marginBottom: '0.3em'}}>{group.label}</Header>
                                        <PreviewItemTable items={group.items} negative inverted={inverted}/>
                                    </React.Fragment>
                                )}
                            </div>
                        </>}

                        <p style={{color: 'grey'}}>{preview.unchanged} unchanged
                            item{preview.unchanged !== 1 ? 's' : ''}</p>
                    </>
                }
            </Modal.Content>
            <Modal.Actions>
                {!applying && <>
                    <Button onClick={handleBack}>Back</Button>
                    <Button color='green' onClick={handleApply}>
                        <Icon name='check'/> Apply
                    </Button>
                </>}
            </Modal.Actions>
        </Modal>;
    }

    // Backups list view.
    return <Modal open={open} onClose={handleClose} closeIcon size='small'>
        <Modal.Header>Restore Backup: {fileName}</Modal.Header>
        <Modal.Content>
            {datesLoading
                ? <div style={{textAlign: 'center', padding: '2em'}}>
                    <Loader active inline='centered'>Loading backups...</Loader>
                </div>
                : dates.length === 0
                    ? <p>No backups available for this config.</p>
                    : <div style={{maxHeight: '400px', overflowY: 'auto'}}>
                        <Table compact unstackable>
                            <TableHeader>
                                <TableRow>
                                    <TableHeaderCell>Date</TableHeaderCell>
                                    <TableHeaderCell>Merge</TableHeaderCell>
                                    <TableHeaderCell>Overwrite</TableHeaderCell>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {dates.map(date =>
                                    <BackupDateRow
                                        key={date}
                                        date={date}
                                        previews={previews[date]}
                                        previewsLoaded={previewsLoaded[date]}
                                        onSelect={handleSelect}
                                    />
                                )}
                            </TableBody>
                        </Table>
                    </div>
            }
        </Modal.Content>
        <Modal.Actions>
            <Button onClick={handleClose}>Close</Button>
        </Modal.Actions>
    </Modal>;
}

function ConfigContentModal({open, onClose, fileName}) {
    const [content, setContent] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!open) return;
        let cancelled = false;
        setLoading(true);
        setContent(null);
        getConfigText(fileName).then(result => {
            if (cancelled) return;
            setContent(result);
            setLoading(false);
        }).catch(() => {
            if (cancelled) return;
            setContent(null);
            setLoading(false);
        });
        return () => { cancelled = true; };
    }, [open, fileName]);

    return <Modal open={open} onClose={onClose} closeIcon size='large'>
        <Modal.Header>{fileName}</Modal.Header>
        <Modal.Content scrolling>
            {loading
                ? <Loader active inline='centered'/>
                : content
                    ? <pre style={{whiteSpace: 'pre-wrap', wordBreak: 'break-word'}}>{content}</pre>
                    : <p>Failed to load config contents.</p>
            }
        </Modal.Content>
        <Modal.Actions>
            <Button onClick={onClose}>Close</Button>
        </Modal.Actions>
    </Modal>;
}

function ConfigTableRow({config, importConfig, saveConfig, fetchConfigs}) {
    const {file_name, valid, successful_import, has_backup_import} = config;
    const [backupsModalOpen, setBackupsModalOpen] = useState(false);
    const [contentModalOpen, setContentModalOpen] = useState(false);

    const localImportConfig = async () => {
        await importConfig(file_name);
        await fetchConfigs();
    }

    const localSaveConfig = async () => {
        await saveConfig(file_name);
        await fetchConfigs();
    }

    const importButton = <APIButton
        icon='upload'
        disabled={!valid}
        onClick={localImportConfig}
    />;

    let saveButton;
    if (successful_import) {
        saveButton = <APIButton
            color='grey'
            icon='download'
            onClick={localSaveConfig}
        />;
    } else {
        // Warn the user they may overwrite because import was not successful.
        saveButton = <APIButton
            color='grey'
            icon='download'
            onClick={localSaveConfig}
            confirmButton='Overwrite'
            confirmContent='Config was not imported successfully, overwrite the config?  Data may be lost!'
        />;
    }

    return <TableRow>
        <TableCell><span style={{cursor: 'pointer'}} onClick={() => setContentModalOpen(true)}>{file_name}</span></TableCell>
        <TableCell><WarningIcon ok={successful_import}/></TableCell>
        <TableCell><WarningIcon ok={valid}/></TableCell>
        <TableCell className="hide-on-mobile">
            {has_backup_import
                ? <Button icon size='mini' onClick={() => setBackupsModalOpen(true)}>
                    <Icon name='undo'/>
                </Button>
                : null
            }
        </TableCell>
        <TableCell>{importButton}</TableCell>
        <TableCell>{saveButton}</TableCell>
        {backupsModalOpen && <BackupsModal
            open={backupsModalOpen}
            onClose={() => setBackupsModalOpen(false)}
            fileName={file_name}
            fetchConfigs={fetchConfigs}
        />}
        {contentModalOpen && <ConfigContentModal
            open={contentModalOpen}
            onClose={() => setContentModalOpen(false)}
            fileName={file_name}
        />}
    </TableRow>
}

export function ConfigsTable({configs, loading, importConfig, saveConfig, fetchConfigs}) {
    let body = <TableRow>
        <TableCell colSpan={6}><TableRowPlaceholder/></TableCell>
    </TableRow>

    if (loading) {
        // Configs are being fetched again.
    } else if (configs === undefined) {
        body = <TableRow>
            <TableCell colSpan={6}>Failed to fetch configs</TableCell>
        </TableRow>;
    } else if (configs && Object.keys(configs).length === 0) {
        body = <TableRow>
            <TableCell colSpan={6}>No configs exist. Try tagging some files.</TableCell>
        </TableRow>;
    } else if (configs) {
        body = Object.entries(configs).map(([key, value]) =>
            <ConfigTableRow
                key={key}
                config={value}
                importConfig={importConfig}
                saveConfig={saveConfig}
                fetchConfigs={fetchConfigs}
            />
        );
    }

    return <Table unstackable striped compact>
        <TableHeader>
            <TableRow>
                <TableHeaderCell width={8}>File Name</TableHeaderCell>
                <TableHeaderCell width={1}>Imported</TableHeaderCell>
                <TableHeaderCell width={1}>Valid</TableHeaderCell>
                <TableHeaderCell width={3} className="hide-on-mobile">Restore</TableHeaderCell>
                <TableHeaderCell width={1}>Import</TableHeaderCell>
                <TableHeaderCell width={1}>Save</TableHeaderCell>
            </TableRow>
        </TableHeader>

        <TableBody>
            {body}
        </TableBody>
    </Table>
}
