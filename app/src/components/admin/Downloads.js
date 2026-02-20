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
    ErrorMessage,
    formatFrequency,
    isoDatetimeToElapsedPopup,
    useTitle,
    WROLModeMessage
} from "../Common";
import {
    Button as SButton,
    ButtonGroup,
    Checkbox,
    Icon,
    Label,
    Loader,
    PlaceholderLine,
    TableBody,
    TableCell,
    TableFooter,
    TableHeader,
    TableHeaderCell,
    TableRow
} from "semantic-ui-react";
import {Button, Header, Modal, Placeholder, Segment, Table} from "../Theme";
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
        color='green'
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
        color='red'
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
        onOpen={handleErrorOpen}
        open={errorModalOpen}
        trigger={<Button icon='exclamation circle' color='orange'/>}
    >
        <Modal.Header>Download Error</Modal.Header>
        <Modal.Content>
            <pre style={{overflowX: 'scroll'}}>{error}</pre>
        </Modal.Content>
        <Modal.Actions>
            <SButton onClick={handleEditClose}>Close</SButton>
        </Modal.Actions>
    </Modal>;

    const editButton = <Button icon='edit' onClick={handleEditOpen}/>;

    const restartButton = <APIButton
        color='green'
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

    return <TableRow>
        <TableCell className='column-ellipsis'>
            {link(url)}
        </TableCell>
        <TableCell>{formatFrequency(frequency)}</TableCell>
        <TableCell>
            {last_successful_download && isoDatetimeToElapsedPopup(last_successful_download)}
            {status === 'pending' && <Loader active inline size='tiny'/>}
        </TableCell>
        <TableCell>{next}</TableCell>
        <TableCell textAlign='right'>
            {error && errorModal}
            {editButton}
            {restartButton}
        </TableCell>
        {editModal}
    </TableRow>
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
    let buttonCell = <TableCell/>;
    if (status === 'pending' || status === 'new') {
        buttonCell = (
            <TableCell>
                <ButtonGroup>
                    <APIButton
                        color='red'
                        icon='stop circle'
                        onClick={handleStop}
                        confirmContent='Are you sure you want to stop this download?  It will not be retried.'
                        confirmButton='Stop'
                        obeyWROLMode={true}
                    />
                    {status === 'new' && (downloader === Downloaders.Video || downloader === Downloaders.Archive) && (
                        <Button
                            icon='edit'
                            color='blue'
                            onClick={handleEditOpen}
                        />
                    )}
                </ButtonGroup>
            </TableCell>
        );
    } else if (status === 'failed' || status === 'deferred') {
        buttonCell = (
            <TableCell>
                <ButtonGroup>
                    <APIButton
                        color='red'
                        icon='trash'
                        onClick={handleDelete}
                        confirmContent='Are you sure you want to delete this download?'
                        confirmButton='Delete'
                        obeyWROLMode={true}
                    />
                    {(downloader === Downloaders.Video || downloader === Downloaders.Archive) && status !== 'pending' && (
                        <Button
                            icon='edit'
                            color='blue'
                            onClick={handleEditOpen}
                        />
                    )}
                    <APIButton
                        color='green'
                        icon='redo'
                        confirmContent='Are you sure you want to restart this download?'
                        confirmButton='Start'
                        onClick={handleRestart}
                        obeyWROLMode={true}
                    />
                </ButtonGroup>
            </TableCell>
        );
    } else if (status === 'complete' && location) {
        buttonCell = (
            <TableCell>
                {link('View')}
            </TableCell>
        );
    }
    if (error) {
        completedAtCell = (
            <Modal
                closeIcon
                trigger={<Button icon='exclamation circle' color='red'/>}
            >
                <Modal.Header>Download Error</Modal.Header>
                <Modal.Content>
                    <pre style={{overflowX: 'scroll'}}>{error}</pre>
                </Modal.Content>
            </Modal>
        )
    }

    // Create edit modal for video or archive downloads
    let editModal = null;

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
                        <p style={{marginTop: '1em', color: '#666'}}>
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
                        <p style={{marginTop: '1em', color: '#666'}}>
                            From: <a href={parentDownloadUrl} target='_blank' rel='noopener noreferrer'>
                                {parentDownloadUrl}
                            </a>
                        </p>
                    )}
                </Modal.Content>
            </Modal>
        );
    }

    return <TableRow>
        <TableCell collapsing>
            <Checkbox
                checked={isSelected}
                onChange={() => onSelect(id)}
            />
        </TableCell>
        <TableCell className='column-ellipsis'>
            {link(url)}
        </TableCell>
        <TableCell>
            {completedAtCell}
            {status === 'pending' ? <Loader active inline size='tiny'/> : null}
        </TableCell>
        {buttonCell}
        {editModal}
    </TableRow>
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

    const footer = <TableFooter>
        <TableRow>
            <TableHeaderCell colSpan={4}>
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
            </TableHeaderCell>
        </TableRow>
    </TableFooter>;

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
        return <Segment>No downloads are scheduled.</Segment>
    } else if (downloads === undefined) {
        return <ErrorMessage>Unable to fetch downloads</ErrorMessage>
    }
    return <Placeholder>
        <PlaceholderLine/>
        <PlaceholderLine/>
    </Placeholder>
}

export function RecurringDownloadsTable({downloads, fetchDownloads, onDelete}) {
    if (downloads && downloads.length >= 1) {
        return <Table compact className='table-ellipsis'>
            <TableHeader>
                <TableRow>
                    <TableHeaderCell width={8}>URL</TableHeaderCell>
                    <TableHeaderCell width={2}>Download Frequency</TableHeaderCell>
                    <TableHeaderCell width={2}>Completed At</TableHeaderCell>
                    <TableHeaderCell width={1}>Next</TableHeaderCell>
                    <TableHeaderCell width={3} textAlign='right'>Control</TableHeaderCell>
                </TableRow>
            </TableHeader>
            <TableBody>
                {downloads.map(i => {
                    return <RecurringDownloadRow
                        key={i.id}
                        fetchDownloads={fetchDownloads}
                        download={i}
                        onDelete={onDelete}
                    />
                })}
            </TableBody>
        </Table>
    } else if (downloads) {
        return <Segment>No downloads are scheduled.</Segment>
    } else if (downloads === undefined) {
        return <ErrorMessage>Unable to fetch downloads</ErrorMessage>
    }
    return <Placeholder>
        <PlaceholderLine/>
        <PlaceholderLine/>
    </Placeholder>
}

export function DownloadsPage() {
    useTitle('Downloads');

    const {onceDownloads, recurringDownloads, pendingOnceDownloads, fetchDownloads} = useDownloads();

    const pendingOnceDownloadsSpan = pendingOnceDownloads > 0 ?
        <Label color='violet' size='large'>{pendingOnceDownloads}</Label>
        : null;

    return <>
        <WROLModeMessage content='Downloads are disabled because WROL Mode is enabled.'/>
        <DisableDownloadsToggle/>
        <CookiesLockedMessage/>

        <Header as='h1'>Downloads {pendingOnceDownloadsSpan}</Header>
        <OnceDownloadsTable downloads={onceDownloads} fetchDownloads={fetchDownloads}/>

        <Header as='h1'>Recurring Downloads</Header>
        <RecurringDownloadsTable downloads={recurringDownloads} fetchDownloads={fetchDownloads}/>
    </>
}
