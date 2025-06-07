import React from "react";
import {
    clearCompletedDownloads,
    deleteDownload,
    deleteOnceDownloads,
    killDownload,
    restartDownload,
    retryOnceDownloads
} from "../../api";
import {Link} from "react-router-dom";
import {
    APIButton,
    DisableDownloadsToggle,
    ErrorMessage,
    isoDatetimeToElapsedPopup,
    secondsToFrequency,
    useTitle,
    WROLModeMessage
} from "../Common";
import {
    Button as SButton, ButtonGroup,
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
import {Button, Header, Modal, ModalActions, ModalContent, ModalHeader, Placeholder, Segment, Table} from "../Theme";
import {useDownloads} from "../../hooks/customHooks";
import {
    EditChannelDownloadForm,
    EditRSSDownloadForm,
    EditScrapeFilesDownloadForm,
    EditZimDownloadForm,
    EditVideosDownloadForm,
    EditArchiveDownloadForm
} from "../Download";
import {Downloaders} from "../Vars";

function ClearDownloadsButton({callback}) {
    async function localClearDownloads() {
        try {
            await clearCompletedDownloads();
        } finally {
            if (callback) {
                callback()
            }
        }
    }

    return <>
        <APIButton
            onClick={localClearDownloads}
            color='violet'
            obeyWROLMode={true}
        >Clear</APIButton>
    </>
}

function RetryDownloadsButton({callback}) {
    async function localRetryOnce() {
        try {
            await retryOnceDownloads();
        } finally {
            if (callback) {
                callback()
            }
        }
    }

    return <APIButton
        color='green'
        onClick={localRetryOnce}
        obeyWROLMode={true}
    >Retry</APIButton>
}

function DeleteOnceDownloadsButton({callback}) {
    async function localDeleteOnce() {
        try {
            await deleteOnceDownloads();
        } finally {
            if (callback) {
                callback()
            }
        }
    }

    return <APIButton
        color='red'
        onClick={localDeleteOnce}
        confirmContent='Are you sure you want to delete all downloads?  Some may be retried!'
        confirmButton='Delete'
        obeyWROLMode={true}
    >Delete</APIButton>
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
        <ModalHeader>Download Error</ModalHeader>
        <ModalContent>
            <pre style={{overflowX: 'scroll'}}>{error}</pre>
        </ModalContent>
        <ModalActions>
            <SButton onClick={handleEditClose}>Close</SButton>
        </ModalActions>
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
        <ModalHeader>Edit Download</ModalHeader>
        <ModalContent>
            {editForm}
        </ModalContent>
    </Modal>;

    return <TableRow>
        <TableCell className='column-ellipsis'>
            {link(url)}
        </TableCell>
        <TableCell>{secondsToFrequency(frequency)}</TableCell>
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

class OnceDownloadRow extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            editModalOpen: false
        };
    }

    handleDelete = async () => {
        try {
            await deleteDownload(this.props.id);
        } finally {
            await this.props.fetchDownloads();
        }
    };

    handleStop = async () => {
        try {
            await killDownload(this.props.id);
        } finally {
            await this.props.fetchDownloads();
        }
    };

    handleRestart = async () => {
        try {
            await restartDownload(this.props.id);
        } finally {
            await this.props.fetchDownloads();
        }
    };

    handleEditOpen = () => {
        this.setState({ editModalOpen: true });
    };

    handleEditClose = () => {
        this.setState({ editModalOpen: false });
    };

    handleEditSuccess = async () => {
        await this.props.fetchDownloads();
        this.handleEditClose();
    };

    render() {
        let {url, last_successful_download, status, location, error, downloader, settings, id} = this.props;

        // Open downloads (/download), or external links in an anchor.
        const link = location && !location.startsWith('/download') ?
            (text) => <Link to={location}>{text}</Link> :
            (text) => <a href={location || url} target='_blank' rel='noopener noreferrer'>{text}</a>;

        let completedAtCell = last_successful_download ? isoDatetimeToElapsedPopup(last_successful_download) : null;
        let buttonCell = <TableCell/>;
        if (status === 'pending' || status === 'new') {
            buttonCell = (
                <TableCell>
                    <APIButton
                        color='red'
                        onClick={this.handleStop}
                        confirmContent='Are you sure you want to stop this download?  It will not be retried.'
                        confirmButton='Stop'
                        obeyWROLMode={true}
                    >Stop</APIButton>
                </TableCell>
            );
        } else if (status === 'failed' || status === 'deferred') {
            buttonCell = (
                <TableCell>
                    <ButtonGroup>

                    <APIButton
                        color='red'
                        icon='trash'
                        onClick={this.handleDelete}
                        confirmContent='Are you sure you want to delete this download?'
                        confirmButton='Delete'
                        obeyWROLMode={true}
                    />
                    {(downloader === Downloaders.Video || downloader === Downloaders.Archive) && status !== 'pending' && (
                        <Button
                            icon='edit'
                            color='blue'
                            onClick={this.handleEditOpen}
                        />
                    )}
                    <APIButton
                        color='green'
                        icon='redo'
                        confirmContent='Are you sure you want to restart this download?'
                        confirmButton='Start'
                        onClick={this.handleRestart}
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
                    <ModalHeader>Download Error</ModalHeader>
                    <ModalContent>
                        <pre style={{overflowX: 'scroll'}}>{error}</pre>
                    </ModalContent>
                </Modal>
            )
        }

        // Create edit modal for video or archive downloads
        let editModal = null;

        if (downloader === Downloaders.Video) {
            editModal = (
                <Modal
                    closeIcon
                    open={this.state.editModalOpen}
                    onClose={this.handleEditClose}
                >
                    <ModalHeader>Edit Video Download</ModalHeader>
                    <ModalContent>
                        <EditVideosDownloadForm
                            download={{
                                urls: url,
                                settings: settings || {},
                                id: id
                            }}
                            onCancel={this.handleEditClose}
                            onSuccess={this.handleEditSuccess}
                            onDelete={this.handleDelete}
                        />
                    </ModalContent>
                </Modal>
            );
        } else if (downloader === Downloaders.Archive) {
            editModal = (
                <Modal
                    closeIcon
                    open={this.state.editModalOpen}
                    onClose={this.handleEditClose}
                >
                    <ModalHeader>Edit Archive Download</ModalHeader>
                    <ModalContent>
                        <EditArchiveDownloadForm
                            download={{
                                urls: url,
                                tag_names: settings?.tag_names || [],
                                id: id
                            }}
                            onCancel={this.handleEditClose}
                            onSuccess={this.handleEditSuccess}
                            onDelete={this.handleDelete}
                        />
                    </ModalContent>
                </Modal>
            );
        }

        return <TableRow>
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
}

export function OnceDownloadsTable({downloads, fetchDownloads}) {
    if (downloads && downloads.length >= 1) {
        return <>
            <Table className='table-ellipsis'>
                <TableHeader>
                    <TableRow>
                        <TableHeaderCell width={11}>URL</TableHeaderCell>
                        <TableHeaderCell width={2}>Completed At</TableHeaderCell>
                        <TableHeaderCell width={2}>Control</TableHeaderCell>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {downloads.map(i => <OnceDownloadRow fetchDownloads={fetchDownloads} key={i.id} {...i}/>)}
                </TableBody>
                <TableFooter>
                    <TableRow>
                        <TableHeaderCell colSpan={3}>
                            <ClearDownloadsButton callback={fetchDownloads}/>
                            <RetryDownloadsButton callback={fetchDownloads}/>
                            <DeleteOnceDownloadsButton callback={fetchDownloads}/>
                        </TableHeaderCell>
                    </TableRow>
                </TableFooter>
            </Table>
        </>
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

        <Header as='h1'>Downloads {pendingOnceDownloadsSpan}</Header>
        <OnceDownloadsTable downloads={onceDownloads} fetchDownloads={fetchDownloads}/>

        <Header as='h1'>Recurring Downloads</Header>
        <RecurringDownloadsTable downloads={recurringDownloads} fetchDownloads={fetchDownloads}/>
    </>
}
