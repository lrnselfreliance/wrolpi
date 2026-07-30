import React from "react";
import {
    batchClearDownloads,
    batchDeleteDownloads,
    batchRetryDownloads,
    clearCompletedDownloads,
    deleteDownload,
    deleteOnceDownloads,
    killDownload,
    restartDownload,
    retryOnceDownloads
} from "../../api";
import {Link} from "react-router";
import {
    APIButton,
    CookiesLockedMessage,
    DisableDownloadsToggle,
    DailyLimitMessage,
    DownloadWindowMessage,
    ErrorMessage,
    formatFrequency,
    humanBandwidth,
    humanFileSize,
    isoDatetimeToElapsedPopup,
    useLocalStorage,
    useTitle,
    WROLModeMessage
} from "../Common";
import {
    Button,
    ButtonGroup,
    Checkbox,
    Header,
    IconButton,
    Label,
    Loader,
    Modal,
    Panel,
    Placeholder,
    Progress,
    Table,
} from "../ui";
import {useDownloads} from "../../hooks/customHooks";
import {
    EditArchiveDownloadForm,
    EditChannelDownloadForm,
    EditRSSDownloadForm,
    EditScrapeFilesDownloadForm,
    EditVideosDownloadForm,
    EditZimDownloadForm
} from "../Download";
import {Downloaders} from "../Vars";
import {SortableTable} from "../SortableTable";

function DownloadProgressModal({progress, url}) {
    const [open, setOpen] = React.useState(false);
    const [navColor] = useLocalStorage('nav_color', 'violet');

    const speedText = humanBandwidth(progress.speed);
    const etaText = progress.eta || '...';
    const buttonLabel = `${speedText} / ${etaText}`;

    return <>
        <Button size='small' onClick={() => setOpen(true)} style={{marginLeft: '0.5em'}}>
            {buttonLabel}
        </Button>
        <Modal closeIcon open={open} onClose={() => setOpen(false)} size='small'>
            <Modal.Header>Download Progress</Modal.Header>
            <Modal.Content>
                <Progress
                    percent={progress.percent}
                    color={navColor}
                    label={`${humanFileSize(progress.bytes_downloaded)} / ${humanFileSize(progress.total_bytes)}`}
                />
                <Table>
                    <Table.Body>
                        <Table.Row>
                            <Table.Cell style={{fontWeight: 600}}>Speed</Table.Cell>
                            <Table.Cell>{speedText}</Table.Cell>
                        </Table.Row>
                        <Table.Row>
                            <Table.Cell style={{fontWeight: 600}}>ETA</Table.Cell>
                            <Table.Cell>{progress.eta || 'Calculating...'}</Table.Cell>
                        </Table.Row>
                        <Table.Row>
                            <Table.Cell style={{fontWeight: 600}}>Downloaded</Table.Cell>
                            <Table.Cell>{humanFileSize(progress.bytes_downloaded)} / {humanFileSize(progress.total_bytes)}</Table.Cell>
                        </Table.Row>
                        {url && <Table.Row>
                            <Table.Cell style={{fontWeight: 600}}>URL</Table.Cell>
                            <Table.Cell style={{wordBreak: 'break-all'}}>{url}</Table.Cell>
                        </Table.Row>}
                    </Table.Body>
                </Table>
            </Modal.Content>
            <Modal.Actions>
                <Button role='cancel' onClick={() => setOpen(false)}>Close</Button>
            </Modal.Actions>
        </Modal>
    </>;
}

function ClearDownloadsButton({callback, selectedIds, clearSelection}) {
    const hasSelection = selectedIds && selectedIds.length > 0;

    async function localClearDownloads() {
        try {
            if (hasSelection) {
                await batchClearDownloads(selectedIds);
                if (clearSelection) clearSelection();
            } else {
                await clearCompletedDownloads();
            }
        } finally {
            if (callback) {
                callback()
            }
        }
    }

    const label = hasSelection ? `Clear (${selectedIds.length})` : 'Clear';

    return <>
        <APIButton
            onClick={localClearDownloads}
            color='violet'
            obeyWROLMode={true}
        >{label}</APIButton>
    </>
}

function RetryDownloadsButton({callback, selectedIds, clearSelection}) {
    const hasSelection = selectedIds && selectedIds.length > 0;

    async function localRetryOnce() {
        try {
            if (hasSelection) {
                await batchRetryDownloads(selectedIds);
                if (clearSelection) clearSelection();
            } else {
                await retryOnceDownloads();
            }
        } finally {
            if (callback) {
                callback()
            }
        }
    }

    const label = hasSelection ? `Retry (${selectedIds.length})` : 'Retry';

    return <APIButton
        role='retry'
        onClick={localRetryOnce}
        obeyWROLMode={true}
    >{label}</APIButton>
}

function DeleteOnceDownloadsButton({callback, selectedIds, clearSelection}) {
    const hasSelection = selectedIds && selectedIds.length > 0;

    async function localDeleteOnce() {
        try {
            if (hasSelection) {
                await batchDeleteDownloads(selectedIds);
                if (clearSelection) clearSelection();
            } else {
                await deleteOnceDownloads();
            }
        } finally {
            if (callback) {
                callback()
            }
        }
    }

    const label = hasSelection ? `Delete (${selectedIds.length})` : 'Delete';
    const confirmContent = hasSelection
        ? `Are you sure you want to delete ${selectedIds.length} download(s)?`
        : 'Are you sure you want to delete all downloads?  Some may be retried!';

    return <APIButton
        role='danger'
        onClick={localDeleteOnce}
        confirmContent={confirmContent}
        confirmButton='Delete'
        obeyWROLMode={true}
    >{label}</APIButton>
}


function RecurringDownloadRow({download, fetchDownloads, onDelete}) {
    const [errorModalOpen, setErrorModalOpen] = React.useState(false);
    const [editModalOpen, setEditModalOpen] = React.useState(false);

    const handleRestart = async () => {
        const {id} = download;
        try {
            await restartDownload(id);
        } finally {
            if (fetchDownloads) {
                await fetchDownloads();
            }
        }
    }

    const handleEditOpen = () => setEditModalOpen(true);
    const handleEditClose = () => setEditModalOpen(false);
    const handleErrorOpen = () => setErrorModalOpen(true);
    const handleErrorClose = () => setErrorModalOpen(false);

    let {
        url,
        frequency,
        last_successful_download,
        status,
        location,
        next_download,
        error,
        downloader,
    } = download;

    const link = location ?
        (text) => <Link to={location}>{text}</Link> :
        (text) => <a href={url} target='_blank' rel='noopener noreferrer'>{text}</a>;

    const errorModal = <Modal
        closeIcon
        onClose={handleErrorClose}
        open={errorModalOpen}
    >
        <Modal.Header>Download Error</Modal.Header>
        <Modal.Content>
            <pre style={{overflowX: 'scroll'}}>{error}</pre>
        </Modal.Content>
        <Modal.Actions>
            <Button role='cancel' onClick={handleErrorClose}>Close</Button>
        </Modal.Actions>
    </Modal>;

    const errorTrigger = <IconButton icon='exclamation triangle' label='Download error' color='orange'
                                     onClick={handleErrorOpen}/>;

    const hideEdit = downloader === Downloaders.MapCatalog || downloader === Downloaders.MapExtract;
    const editButton = hideEdit ? null :
        <IconButton icon='edit' label='Edit download' onClick={handleEditOpen}/>;

    const restartButton = <APIButton
        role='retry'
        icon='redo'
        confirmContent='Are you sure you want to restart this download?'
        confirmButton='Restart'
        onClick={handleRestart}
        obeyWROLMode={true}
    />;

    // Show "now" if we have passed the next_download.
    let next = 'now';
    if (next_download && new Date() < new Date(next_download)) {
        next = isoDatetimeToElapsedPopup(next_download);
    }

    const onSuccess = async () => {
        if (fetchDownloads) {
            await fetchDownloads();
        }
        handleEditClose();
    }

    const localOnDelete = async () => {
        try {
            await deleteDownload(download.id);
            await onDelete();
        } finally {
            await fetchDownloads();
            handleEditClose();
        }
    }

    let editForm;
    if (downloader === Downloaders.VideoChannel) {
        editForm = <EditChannelDownloadForm
            download={download}
            onCancel={handleEditClose}
            onSuccess={onSuccess}
            onDelete={localOnDelete}
        />;
    } else if (downloader === Downloaders.RSS) {
        editForm = <EditRSSDownloadForm
            download={download}
            onDelete={localOnDelete}
            onCancel={handleEditClose}
            onSuccess={onSuccess}
        />;
    } else if (downloader === Downloaders.KiwixCatalog) {
        editForm = <EditZimDownloadForm
            download={download}
            onDelete={localOnDelete}
            onCancel={handleEditClose}
            onSuccess={onSuccess}
        />;
    } else if (downloader === Downloaders.ScrapeHtml) {
        editForm = <EditScrapeFilesDownloadForm
            download={download}
            onDelete={localOnDelete}
            onCancel={handleEditClose}
            onSuccess={onSuccess}
        />;
    }

    const editModal = <Modal closeIcon
                             open={editModalOpen}
                             onClose={handleEditClose}
    >
        <Modal.Header>Edit Download</Modal.Header>
        <Modal.Content>
            {editForm}
        </Modal.Content>
    </Modal>;

    return <Table.Row failed={!!error && !download.progress}>
        <Table.Cell className='column-ellipsis'>
            {link(url)}
        </Table.Cell>
        <Table.Cell>{formatFrequency(frequency)}</Table.Cell>
        <Table.Cell>
            {last_successful_download && isoDatetimeToElapsedPopup(last_successful_download)}
            {status === 'pending' && !download.progress && <Loader size='xs'/>}
            {download.progress && <DownloadProgressModal progress={download.progress} url={download.url}/>}
        </Table.Cell>
        <Table.Cell>{next}</Table.Cell>
        <Table.Cell style={{textAlign: 'right'}}>
            {error && !download.progress && errorTrigger}
            {editButton}
            {restartButton}
        </Table.Cell>
        {errorModal}
        {editModal}
    </Table.Row>
}

function OnceDownloadRow({download, fetchDownloads, isSelected, onSelect}) {
    const [editModalOpen, setEditModalOpen] = React.useState(false);

    const {url, last_successful_download, status, location, error, downloader, settings, id, tag_names} = download;
    const parentDownloadUrl = settings?.parent_download_url;

    const handleDelete = async () => {
        try {
            await deleteDownload(id);
        } finally {
            await fetchDownloads();
        }
    };

    const handleStop = async () => {
        try {
            await killDownload(id);
        } finally {
            await fetchDownloads();
        }
    };

    const handleRestart = async () => {
        try {
            await restartDownload(id);
        } finally {
            await fetchDownloads();
        }
    };

    const handleEditOpen = () => setEditModalOpen(true);
    const handleEditClose = () => setEditModalOpen(false);

    const handleEditSuccess = async () => {
        await fetchDownloads();
        handleEditClose();
    };

    // Open downloads (/download), or external links in an anchor.
    const link = location && !location.startsWith('/download') ?
        (text) => <Link to={location}>{text}</Link> :
        (text) => <a href={location || url} target='_blank' rel='noopener noreferrer'>{text}</a>;

    let completedAtCell = last_successful_download ? isoDatetimeToElapsedPopup(last_successful_download) : null;
    let buttonCell = <Table.Cell/>;
    if (status === 'pending' || status === 'new') {
        buttonCell = (
            <Table.Cell>
                <ButtonGroup>
                    <APIButton
                        role='danger'
                        icon='stop'
                        onClick={handleStop}
                        confirmContent='Are you sure you want to stop this download?  It will not be retried.'
                        confirmButton='Stop'
                        obeyWROLMode={true}
                    />
                    {status === 'new' && (downloader === Downloaders.Video || downloader === Downloaders.Archive) && (
                        <IconButton
                            icon='edit'
                            label='Edit download'
                            color='blue'
                            onClick={handleEditOpen}
                        />
                    )}
                </ButtonGroup>
            </Table.Cell>
        );
    } else if (status === 'failed' || status === 'deferred') {
        buttonCell = (
            <Table.Cell>
                <ButtonGroup>
                    <APIButton
                        role='danger'
                        icon='trash'
                        onClick={handleDelete}
                        confirmContent='Are you sure you want to delete this download?'
                        confirmButton='Delete'
                        obeyWROLMode={true}
                    />
                    {(downloader === Downloaders.Video || downloader === Downloaders.Archive) && status !== 'pending' && (
                        <IconButton
                            icon='edit'
                            label='Edit download'
                            color='blue'
                            onClick={handleEditOpen}
                        />
                    )}
                    <APIButton
                        role='retry'
                        icon='redo'
                        confirmContent='Are you sure you want to restart this download?'
                        confirmButton='Start'
                        onClick={handleRestart}
                        obeyWROLMode={true}
                    />
                </ButtonGroup>
            </Table.Cell>
        );
    } else if (status === 'complete' && location) {
        buttonCell = (
            <Table.Cell>
                {link('View')}
            </Table.Cell>
        );
    }

    // Create edit modal for video or archive downloads
    let editModal = null;
    let errorModal = null;
    const [errorModalOpen, setErrorModalOpen] = React.useState(false);

    if (error && !download.progress) {
        completedAtCell = (
            <IconButton icon='exclamation triangle' label='Download error' color='red'
                        onClick={() => setErrorModalOpen(true)}/>
        )
        errorModal = <Modal
            closeIcon
            open={errorModalOpen}
            onClose={() => setErrorModalOpen(false)}
        >
            <Modal.Header>Download Error</Modal.Header>
            <Modal.Content>
                <pre style={{overflowX: 'scroll'}}>{error}</pre>
            </Modal.Content>
        </Modal>
    }

    if (downloader === Downloaders.Video) {
        editModal = (
            <Modal
                closeIcon
                open={editModalOpen}
                onClose={handleEditClose}
            >
                <Modal.Header>Edit Video Download</Modal.Header>
                <Modal.Content>
                    <EditVideosDownloadForm
                        download={{
                            urls: url,
                            settings: settings || {},
                            id: id,
                            tag_names: tag_names || []
                        }}
                        onCancel={handleEditClose}
                        onSuccess={handleEditSuccess}
                        onDelete={handleDelete}
                    />
                    {parentDownloadUrl && (
                        <p style={{marginTop: '1em', color: 'var(--muted)'}}>
                            From: <a href={parentDownloadUrl} target='_blank' rel='noopener noreferrer'>
                            {parentDownloadUrl}
                        </a>
                        </p>
                    )}
                </Modal.Content>
            </Modal>
        );
    } else if (downloader === Downloaders.Archive) {
        editModal = (
            <Modal
                closeIcon
                open={editModalOpen}
                onClose={handleEditClose}
            >
                <Modal.Header>Edit Archive Download</Modal.Header>
                <Modal.Content>
                    <EditArchiveDownloadForm
                        download={{
                            urls: url,
                            tag_names: tag_names || [],
                            id: id
                        }}
                        onCancel={handleEditClose}
                        onSuccess={handleEditSuccess}
                        onDelete={handleDelete}
                    />
                    {parentDownloadUrl && (
                        <p style={{marginTop: '1em', color: 'var(--muted)'}}>
                            From: <a href={parentDownloadUrl} target='_blank' rel='noopener noreferrer'>
                            {parentDownloadUrl}
                        </a>
                        </p>
                    )}
                </Modal.Content>
            </Modal>
        );
    }

    return <Table.Row failed={status === 'failed' || status === 'deferred'}>
        <Table.Cell>
            <Checkbox
                checked={isSelected}
                onChange={() => onSelect(id)}
            />
        </Table.Cell>
        <Table.Cell className='column-ellipsis'>
            {link(url)}
        </Table.Cell>
        <Table.Cell>
            {completedAtCell}
            {status === 'pending' && !download.progress ? <Loader size='xs'/> : null}
            {download.progress && <DownloadProgressModal progress={download.progress} url={download.url}/>}
        </Table.Cell>
        {buttonCell}
        {errorModal}
        {editModal}
    </Table.Row>
}

export function OnceDownloadsTable({downloads, fetchDownloads}) {
    const [selectedIds, setSelectedIds] = React.useState([]);

    // Clear selection when downloads change (e.g., after deletion)
    React.useEffect(() => {
        if (downloads) {
            // Remove any selected IDs that no longer exist
            const downloadIds = new Set(downloads.map(d => d.id));
            setSelectedIds(prev => prev.filter(id => downloadIds.has(id)));
        }
    }, [downloads]);

    const onSelect = (id) => {
        if (selectedIds.includes(id)) {
            setSelectedIds(selectedIds.filter(i => i !== id));
        } else {
            setSelectedIds([...selectedIds, id]);
        }
    };

    const clearSelection = () => setSelectedIds([]);

    const toggleSelectAll = () => {
        if (downloads && selectedIds.length === downloads.length) {
            setSelectedIds([]);
        } else if (downloads) {
            setSelectedIds(downloads.map(d => d.id));
        }
    };

    const tableHeaders = [
        {
            key: 'select',
            text: <Checkbox
                checked={downloads && downloads.length > 0 && selectedIds.length === downloads.length}
                indeterminate={selectedIds.length > 0 && selectedIds.length < (downloads?.length || 0)}
                onChange={toggleSelectAll}
            />,
            sortBy: null
        },
        {key: 'url', text: 'URL', sortBy: i => i.url.toLowerCase()},
        {key: 'completed_at', text: 'Completed At', sortBy: i => i.last_successful_download || ''},
        {key: 'control', text: 'Control', sortBy: null},
    ];

    const rowFunc = (download) => (
        <OnceDownloadRow
            key={download.id}
            download={download}
            fetchDownloads={fetchDownloads}
            isSelected={selectedIds.includes(download.id)}
            onSelect={onSelect}
        />
    );

    const footer = <Table.Footer>
        <Table.Row>
            <Table.HeaderCell colSpan={4}>
                <ClearDownloadsButton
                    callback={fetchDownloads}
                    selectedIds={selectedIds}
                    clearSelection={clearSelection}
                />
                <RetryDownloadsButton
                    callback={fetchDownloads}
                    selectedIds={selectedIds}
                    clearSelection={clearSelection}
                />
                <DeleteOnceDownloadsButton
                    callback={fetchDownloads}
                    selectedIds={selectedIds}
                    clearSelection={clearSelection}
                />
            </Table.HeaderCell>
        </Table.Row>
    </Table.Footer>;

    if (downloads && downloads.length >= 1) {
        return <SortableTable
            tableHeaders={tableHeaders}
            data={downloads}
            rowFunc={rowFunc}
            rowKey='id'
            footer={footer}
            tableProps={{className: 'table-ellipsis'}}
        />
    } else if (downloads) {
        return <Panel>No downloads are scheduled.</Panel>
    } else if (downloads === undefined) {
        return <ErrorMessage>Unable to fetch downloads</ErrorMessage>
    }
    return <Placeholder lines={2}/>
}

export function RecurringDownloadsTable({downloads, fetchDownloads, onDelete}) {
    if (downloads && downloads.length >= 1) {
        return <Table className='table-ellipsis'>
            <Table.Header>
                <Table.Row>
                    <Table.HeaderCell style={{width: '50%'}}>URL</Table.HeaderCell>
                    <Table.HeaderCell style={{width: '12.5%'}}>Download Frequency</Table.HeaderCell>
                    <Table.HeaderCell style={{width: '12.5%'}}>Completed At</Table.HeaderCell>
                    <Table.HeaderCell style={{width: '6.25%'}}>Next</Table.HeaderCell>
                    <Table.HeaderCell style={{width: '18.75%', textAlign: 'right'}}>Control</Table.HeaderCell>
                </Table.Row>
            </Table.Header>
            <Table.Body>
                {downloads.map(i => {
                    return <RecurringDownloadRow
                        key={i.id}
                        fetchDownloads={fetchDownloads}
                        download={i}
                        onDelete={onDelete}
                    />
                })}
            </Table.Body>
        </Table>
    } else if (downloads) {
        return <Panel>No downloads are scheduled.</Panel>
    } else if (downloads === undefined) {
        return <ErrorMessage>Unable to fetch downloads</ErrorMessage>
    }
    return <Placeholder lines={2}/>
}

export function DownloadsPage() {
    useTitle('Downloads');

    const {onceDownloads, recurringDownloads, pendingOnceDownloads, fetchDownloads} = useDownloads();

    const pendingOnceDownloadsSpan = pendingOnceDownloads > 0 ?
        <Label color='violet'>{pendingOnceDownloads}</Label>
        : null;

    return <>
        <WROLModeMessage content='Downloads are disabled because WROL Mode is enabled.'/>
        <DownloadWindowMessage/>
        <DailyLimitMessage/>
        <DisableDownloadsToggle/>
        <CookiesLockedMessage/>

        <Header as='h1'>Downloads {pendingOnceDownloadsSpan}</Header>
        <OnceDownloadsTable downloads={onceDownloads} fetchDownloads={fetchDownloads}/>

        <Header as='h1'>Recurring Downloads</Header>
        <RecurringDownloadsTable downloads={recurringDownloads} fetchDownloads={fetchDownloads}/>
    </>
}
