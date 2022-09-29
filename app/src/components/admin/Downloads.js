import React, {useContext} from "react";
import {clearCompletedDownloads, clearFailedDownloads, killDownload, postDownload} from "../../api";
import {Link} from "react-router-dom";
import {
    DisableDownloadsToggle,
    secondsToElapsedPopup,
    secondsToFrequency,
    textEllipsis,
    WROLModeMessage
} from "../Common";
import {
    Confirm,
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
        }
    }


    render() {
        let {url, frequency, last_successful_download, status, location, next_download, error} = this.props;
        const {errorModalOpen} = this.state;

        const link = location ?
            (text) => <Link to={location}>{text}</Link> :
            (text) => <a href={url} target='_blank' rel='noopener noreferrer'>{text}</a>;

        let positive = false;
        if (status === 'pending') {
            positive = true;
        }

        const errorModal = <Modal
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
        </Modal>;

        return <TableRow positive={positive}>
            <TableCell>
                {link(textEllipsis(url, 50))}
            </TableCell>
            <TableCell>{secondsToFrequency(frequency)}</TableCell>
            <TableCell>{last_successful_download ? secondsToElapsedPopup(last_successful_download) : null}</TableCell>
            <TableCell>{secondsToElapsedPopup(next_download)}</TableCell>
            <TableCell>{error && errorModal}{link('View')}</TableCell>
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
        let positive = false;
        let negative = false;
        let warning = false;
        if (status === 'pending' || status === 'new') {
            positive = status === 'pending';
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
            negative = status === 'failed';
            warning = status === 'deferred';
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
            <TableRow positive={positive} negative={negative} warning={warning}>
                <TableCell>
                    {link(textEllipsis(url, 50))}
                </TableCell>
                <TableCell>{completedAtCell}</TableCell>
                {buttonCell}
            </TableRow>
        );
    }
}

export function Downloads() {
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
                <TableHeaderCell>View</TableHeaderCell>
            </TableRow>
        </TableHeader>
    );

    let onceTable = tablePlaceholder;
    if (onceDownloads && onceDownloads.length === 0) {
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
    if (recurringDownloads && recurringDownloads.length === 0) {
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
