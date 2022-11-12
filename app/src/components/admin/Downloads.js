import React, {useContext} from "react";
import {clearCompletedDownloads, clearFailedDownloads, deleteDownload, killDownload, postDownload} from "../../api";
import {Link} from "react-router-dom";
import {
    DisableDownloadsToggle,
    isEmpty,
    secondsToElapsedPopup,
    secondsToFrequency,
    textEllipsis,
    useTitle,
    WROLModeMessage
} from "../Common";
import {
    Button as SemanticButton,
    Confirm,
    Loader,
    Modal,
    PlaceholderLine,
    TableBody,
    TableCell,
    TableHeader,
    TableHeaderCell,
    TableRow
} from "semantic-ui-react";
import {Button, Header, Placeholder, Table} from "../Theme";
import {ThemeContext} from "../../contexts/contexts";
import {useDownloads} from "../../hooks/customHooks";

function ClearCompleteDownloads({callback}) {
    const [disabled, setDisabled] = React.useState(false);

    async function localClearDownloads() {
        setDisabled(true);
        try {
            await clearCompletedDownloads();
        } finally {
            setDisabled(false);
            if (callback) {
                callback()
            }
        }
    }

    return <>
        <Button
            onClick={localClearDownloads}
            disabled={disabled}
            color='yellow'
        >Clear Completed</Button>
    </>
}

function ClearFailedDownloads({callback}) {
    const [open, setOpen] = React.useState(false);
    const [disabled, setDisabled] = React.useState(false);

    async function localDeleteFailed() {
        setDisabled(true);
        try {
            await clearFailedDownloads();
        } finally {
            setDisabled(false);
            setOpen(false);
            if (callback) {
                callback()
            }
        }
    }

    return <>
        <Button
            onClick={() => setOpen(true)}
            disabled={disabled}
            color='red'
        >Clear Failed</Button>
        <Confirm
            open={open}
            content='Are you sure you want to delete failed downloads?  They will not be retried.'
            confirmButton='Delete'
            onCancel={() => setOpen(false)}
            onConfirm={localDeleteFailed}
        />
    </>
}

class DownloadRow extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            errorModalOpen: false,
            deleteOpen: false,
        }
    }

    openDelete = (e) => {
        if (e) {
            e.preventDefault();
        }
        this.setState({deleteOpen: true});
    }

    closeDelete = (e) => {
        if (e) {
            e.preventDefault();
        }
        this.setState({deleteOpen: false});
    }

    handleDelete = async (e) => {
        if (e) {
            e.preventDefault();
        }
        const {id} = this.props;
        try {
            await deleteDownload(id);
        } finally {
            this.closeDelete();
        }
    }

    render() {
        let {url, frequency, last_successful_download, status, location, next_download, error} = this.props;
        const {errorModalOpen, deleteOpen} = this.state;

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
            <Modal.Header>Download Error</Modal.Header>
            <Modal.Content>
                <pre style={{overflowX: 'scroll'}}>{error}</pre>
            </Modal.Content>
            <Modal.Actions>
                <SemanticButton onClick={() => this.setState({errorModalOpen: false})}>Close</SemanticButton>
            </Modal.Actions>
        </Modal>;

        const deleteButton = <>
            <Button icon='trash' onClick={this.openDelete} color='red'/>
            <Confirm
                open={deleteOpen}
                content='Are you sure you want to delete this download?'
                confirmButton='Delete'
                onCancel={this.closeDelete}
                onConfirm={this.handleDelete}
            />
        </>;

        return <TableRow>
            <TableCell>
                {link(textEllipsis(url, 50))}
            </TableCell>
            <TableCell>{secondsToFrequency(frequency)}</TableCell>
            <TableCell>
                {last_successful_download ? secondsToElapsedPopup(last_successful_download) : null}
                {status === 'pending' ? <Loader active inline size='tiny'/> : null}
            </TableCell>
            <TableCell>{secondsToElapsedPopup(next_download)}</TableCell>
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
        this.state = {
            stopOpen: false,
            startOpen: false,
            errorModalOpen: false,
        };
    }

    openStop = () => {
        this.setState({stopOpen: true});
    }

    closeStop = () => {
        this.setState({stopOpen: false});
    }

    openStart = () => {
        this.setState({startOpen: true});
    }

    closeStart = () => {
        this.setState({startOpen: false});
    }

    handleStop = async (e) => {
        e.preventDefault();
        await killDownload(this.props.id);
        this.closeStop();
        await this.props.fetchDownloads();
    };

    handleStart = async (e) => {
        e.preventDefault();
        let downloader = this.props.downloader || null;
        await postDownload(`${this.props.url}`, downloader);
        this.closeStart();
        await this.props.fetchDownloads();
    };

    render() {
        let {url, last_successful_download, status, location, error} = this.props;
        let {stopOpen, startOpen, errorModalOpen} = this.state;

        const link = location ?
            (text) => <Link to={location}>{text}</Link> :
            (text) => <a href={url} target='_blank' rel='noopener noreferrer'>{text}</a>;

        let completedAtCell = last_successful_download ? secondsToElapsedPopup(last_successful_download) : null;
        let buttonCell = <TableCell/>;
        if (status === 'pending' || status === 'new') {
            buttonCell = (
                <TableCell>
                    <Button
                        onClick={this.openStop}
                        color='red'
                    >Stop</Button>
                    <Confirm
                        open={stopOpen}
                        content='Are you sure you want to stop this download?  It will not be retried.'
                        confirmButton='Stop'
                        onCancel={this.closeStop}
                        onConfirm={this.handleStop}
                    />
                </TableCell>
            );
        } else if (status === 'failed' || status === 'deferred') {
            buttonCell = (
                <TableCell>
                    <Button
                        onClick={this.openStop}
                        color='red'
                    >Stop</Button>
                    <Confirm
                        open={stopOpen}
                        content='Are you sure you want to stop this download?  It will not be retried.'
                        confirmButton='Stop'
                        onCancel={this.closeStop}
                        onConfirm={this.handleStop}
                    />
                    <Button
                        onClick={this.openStart}
                        color='green'
                    >Retry</Button>
                    <Confirm
                        open={startOpen}
                        content='Are you sure you want to restart this download?'
                        confirmButton='Start'
                        onCancel={this.closeStart}
                        onConfirm={this.handleStart}
                    />
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
                    onClose={() => this.setState({errorModalOpen: false})}
                    onOpen={() => this.setState({errorModalOpen: true})}
                    open={errorModalOpen}
                    trigger={<Button icon='exclamation circle' color='red'/>}
                >
                    <Modal.Header>Download Error</Modal.Header>
                    <Modal.Content>
                        <pre style={{overflowX: 'scroll'}}>{error}</pre>
                    </Modal.Content>
                    <Modal.Actions>
                        <Button onClick={() => this.setState({errorModalOpen: false})}>Close</Button>
                    </Modal.Actions>
                </Modal>
            )
        }

        return (
            <TableRow>
                <TableCell>
                    {link(textEllipsis(url, 50))}
                </TableCell>
                <TableCell>
                    {completedAtCell}
                    {status === 'pending' ? <Loader active inline size='tiny'/> : null}
                </TableCell>
                {buttonCell}
            </TableRow>
        );
    }
}

export function Downloads() {
    useTitle('Downloads');

    const {t} = useContext(ThemeContext);

    const {onceDownloads, recurringDownloads, fetchDownloads} = useDownloads();

    const tablePlaceholder = <Placeholder>
        <PlaceholderLine/>
        <PlaceholderLine/>
    </Placeholder>;

    const stoppableHeader = (
        <TableHeader>
            <TableRow>
                <TableHeaderCell>URL</TableHeaderCell>
                <TableHeaderCell>Completed At</TableHeaderCell>
                <TableHeaderCell>Control</TableHeaderCell>
            </TableRow>
        </TableHeader>
    );

    const nonStoppableHeader = (
        <TableHeader>
            <TableRow>
                <TableHeaderCell>URL</TableHeaderCell>
                <TableHeaderCell>Download Frequency</TableHeaderCell>
                <TableHeaderCell>Completed At</TableHeaderCell>
                <TableHeaderCell>Next</TableHeaderCell>
                <TableHeaderCell>Control</TableHeaderCell>
            </TableRow>
        </TableHeader>
    );

    let onceTable = tablePlaceholder;
    if (isEmpty(onceDownloads)) {
        onceTable = <p {...t}>No downloads are scheduled.</p>
    } else if (onceDownloads) {
        onceTable = (
            <>
                <ClearCompleteDownloads callback={fetchDownloads}/>
                <ClearFailedDownloads callback={fetchDownloads}/>
                <Table>
                    {stoppableHeader}
                    <TableBody>
                        {onceDownloads.map((i) =>
                            <StoppableRow fetchDownloads={fetchDownloads} key={i.id} {...i}/>
                        )}
                    </TableBody>
                </Table>
            </>);
    }

    let recurringTable = tablePlaceholder;
    if (isEmpty(recurringDownloads)) {
        recurringTable = <p {...t}>No recurring downloads are scheduled.</p>
    } else if (recurringDownloads) {
        recurringTable = <Table>
            {nonStoppableHeader}
            <TableBody>
                {recurringDownloads.map((i) => <DownloadRow key={i.id} {...i}/>)}
            </TableBody>
        </Table>;
    }

    return <>
        <WROLModeMessage content='Downloads are disabled because WROL Mode is enabled.'/>
        <DisableDownloadsToggle/>
        <Header as='h1'>Downloads</Header>
        {onceTable}

        <Header as='h1'>Recurring Downloads</Header>
        {recurringTable}
    </>
}
