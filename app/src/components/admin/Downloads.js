import React from "react";
import {clearCompletedDownloads, clearFailedDownloads, deleteDownload, killDownload, postDownload} from "../../api";
import {Link} from "react-router-dom";
import {
    APIButton,
    DisableDownloadsToggle,
    isoDatetimeToElapsedPopup,
    secondsToFrequency,
    textEllipsis,
    useTitle,
    WROLModeMessage
} from "../Common";
import {
    Button as SButton,
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
import _ from "lodash";

function ClearCompleteDownloads({callback}) {
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
            color='yellow'
            obeyWROLMode={true}
        >Clear Completed</APIButton>
    </>
}

function ClearFailedDownloads({callback}) {
    async function localDeleteFailed() {
        try {
            await clearFailedDownloads();
        } finally {
            if (callback) {
                callback()
            }
        }
    }

    return <APIButton
        color='red'
        onClick={localDeleteFailed}
        confirmContent='Are you sure you want to delete failed downloads?  They will not be retried.'
        confirmButton='Delete'
        obeyWROLMode={true}
    >
        Clear Failed
    </APIButton>
}

class DownloadRow extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            errorModalOpen: false,
        }
    }

    handleDelete = async () => {
        const {id} = this.props;
        try {
            await deleteDownload(id);
        } finally {
            if (this.props.fetchDownloads) {
                this.props.fetchDownloads();
            }
        }
    }

    render() {
        let {url, frequency, last_successful_download, status, location, next_download, error} = this.props;
        const {errorModalOpen} = this.state;

        const link = location ?
            (text) => <Link to={location}>{text}</Link> :
            (text) => <a href={url} target='_blank' rel='noopener noreferrer'>{text}</a>;

        const errorModal = <Modal
            closeIcon
            onClose={() => this.setState({errorModalOpen: false})}
            onOpen={() => this.setState({errorModalOpen: true})}
            open={errorModalOpen}
            trigger={<Button icon='exclamation circle' color='orange'/>}
        >
            <ModalHeader>Download Error</ModalHeader>
            <ModalContent>
                <pre style={{overflowX: 'scroll'}}>{error}</pre>
            </ModalContent>
            <ModalActions>
                <SButton onClick={() => this.setState({errorModalOpen: false})}>Close</SButton>
            </ModalActions>
        </Modal>;

        const deleteButton = <>
            <APIButton
                color='red'
                icon='trash'
                confirmContent='Are you sure you want to delete this download?'
                confirmButton='Delete'
                onClick={this.handleDelete}
                obeyWROLMode={true}
            />
        </>;

        // Show "now" if we have passed the next_download.
        let next = 'now';
        if (next_download) {
            if (new Date() < new Date(next_download)) {
                next = isoDatetimeToElapsedPopup(next_download);
            }
        }

        return <TableRow>
            <TableCell>
                {link(textEllipsis(url, 50))}
            </TableCell>
            <TableCell>{secondsToFrequency(frequency)}</TableCell>
            <TableCell>
                {last_successful_download ? isoDatetimeToElapsedPopup(last_successful_download) : null}
                {status === 'pending' ? <Loader active inline size='tiny'/> : null}
            </TableCell>
            <TableCell>{next}</TableCell>
            <TableCell>
                {error && errorModal}
                {deleteButton}
            </TableCell>
        </TableRow>
    }
}

class StoppableRow extends React.Component {
    constructor(props) {
        super(props);
    }

    handleDelete = async () => {
        await deleteDownload(this.props.id);
        await this.props.fetchDownloads();
    };

    handleStop = async () => {
        await killDownload(this.props.id);
        await this.props.fetchDownloads();
    };

    handleStart = async () => {
        let downloader = this.props.downloader;
        await postDownload(`${this.props.url}`, downloader);
        await this.props.fetchDownloads();
    };

    render() {
        let {url, last_successful_download, status, location, error} = this.props;

        // Open downloads (/download), or external links in an anchor.
        const link = location && !location.startsWith('/download') ?
            (text) => <Link to={location}>{text}</Link> :
            (text) => <a href={url} target='_blank' rel='noopener noreferrer'>{text}</a>;

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
                    <APIButton
                        color='red'
                        icon='trash'
                        onClick={this.handleDelete}
                        confirmContent='Are you sure you want to delete this download?'
                        confirmButton='Delete'
                        obeyWROLMode={true}
                    />
                    <APIButton
                        color='green'
                        confirmContent='Are you sure you want to restart this download?'
                        confirmButton='Start'
                        onClick={this.handleStart}
                        obeyWROLMode={true}
                    >Retry</APIButton>
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

        return <TableRow>
            <TableCell>
                {link(textEllipsis(url, 50))}
            </TableCell>
            <TableCell>
                {completedAtCell}
                {status === 'pending' ? <Loader active inline size='tiny'/> : null}
            </TableCell>
            {buttonCell}
        </TableRow>
    }
}

export function OnceDownloadsTable({downloads, fetchDownloads}) {
    if (downloads && _.isEmpty(downloads)) {
        return <Segment>No downloads are scheduled.</Segment>;
    } else if (downloads) {
        return <>
            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHeaderCell>URL</TableHeaderCell>
                        <TableHeaderCell>Completed At</TableHeaderCell>
                        <TableHeaderCell>Control</TableHeaderCell>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {downloads.map(i => <StoppableRow fetchDownloads={fetchDownloads} key={i.id} {...i}/>)}
                </TableBody>
                <TableFooter>
                    <TableRow>
                        <TableHeaderCell colSpan={3}>
                            <ClearCompleteDownloads callback={fetchDownloads}/>
                            <ClearFailedDownloads callback={fetchDownloads}/>
                        </TableHeaderCell>
                    </TableRow>
                </TableFooter>
            </Table>
        </>;
    } else {
        return <Placeholder>
            <PlaceholderLine/>
            <PlaceholderLine/>
        </Placeholder>;
    }
}

export function RecurringDownloadsTable({downloads, fetchDownloads}) {
    if (downloads && _.isEmpty(downloads)) {
        return <Segment>No downloads are scheduled.</Segment>;
    } else if (downloads) {
        return <Table>
            <TableHeader>
                <TableRow>
                    <TableHeaderCell>URL</TableHeaderCell>
                    <TableHeaderCell>Download Frequency</TableHeaderCell>
                    <TableHeaderCell>Completed At</TableHeaderCell>
                    <TableHeaderCell>Next</TableHeaderCell>
                    <TableHeaderCell>Control</TableHeaderCell>
                </TableRow>
            </TableHeader>
            <TableBody>
                {downloads.map(i => <DownloadRow key={i.id} fetchDownloads={fetchDownloads} {...i}/>)}
            </TableBody>
        </Table>;
    } else {
        return <Placeholder>
            <PlaceholderLine/>
            <PlaceholderLine/>
        </Placeholder>;
    }
}

export function DownloadsPage() {
    useTitle('Downloads');

    const {onceDownloads, recurringDownloads, pendingOnceDownloads, fetchDownloads} = useDownloads();

    const pendingOnceDownloadsSpan = pendingOnceDownloads > 0 ? <span>({pendingOnceDownloads})</span> : null;

    return <>
        <WROLModeMessage content='Downloads are disabled because WROL Mode is enabled.'/>
        <DisableDownloadsToggle/>

        <Header as='h1'>Downloads {pendingOnceDownloadsSpan}</Header>
        <OnceDownloadsTable downloads={onceDownloads} fetchDownloads={fetchDownloads}/>

        <Header as='h1'>Recurring Downloads</Header>
        <RecurringDownloadsTable downloads={recurringDownloads} fetchDownloads={fetchDownloads}/>
    </>
}
