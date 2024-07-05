import React from "react";
import {
    clearCompletedDownloads,
    deleteDownload,
    deleteOnceDownloads,
    killDownload,
    putDownload,
    restartDownload,
    retryOnceDownloads
} from "../../api";
import {Link} from "react-router-dom";
import {
    APIButton,
    DisableDownloadsToggle,
    ErrorMessage,
    frequencyOptions,
    isoDatetimeToElapsedPopup,
    secondsToFrequency,
    useTitle,
    validURL,
    WROLModeMessage
} from "../Common";
import {
    Button as SButton,
    Dimmer,
    Dropdown,
    Grid,
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
import {
    Button,
    Form,
    FormField,
    FormInput,
    Header,
    Modal,
    ModalActions,
    ModalContent,
    ModalHeader,
    Placeholder,
    Segment,
    Table
} from "../Theme";
import {useDownloads, useWROLMode} from "../../hooks/customHooks";
import {toast} from "react-semantic-toasts-2";
import {ChannelDownloadForm} from "../Channels";

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


export function DownloadEditForm({afterSave, closeModal, download}) {
    const [state, setState] = React.useState({
        url: download.url || '',
        frequency: download.frequency,
        excluded_urls: download.settings ? download.settings.excluded_urls : '',
        destination: download.settings ? download.settings.destination : '',
    })
    const [disabled, setDisabled] = React.useState(useWROLMode());
    const [loading, setLoading] = React.useState(false);
    const [urlValid, setUrlValid] = React.useState(true);

    const handleInputChange = (e, {name, value}) => {
        if (e) {
            e.preventDefault();
        }
        if (name === 'url') {
            setUrlValid(validURL(value));
        }
        setState({...state, [name]: value});
    }

    const handleSubmit = async () => {
        setLoading(true);
        setDisabled(true);
        try {
            const response = await putDownload(
                [state.url],
                download.id,
                download.downloader,
                download.sub_downloader,
                state.frequency,
                state.excluded_urls,
            );
            if (!response.ok) {
                throw 'Updating download failed';
            }
            if (afterSave) {
                afterSave();
            }
        } finally {
            setLoading(false);
            setDisabled(false);
        }
    }

    const handleClose = (e) => {
        if (e) e.preventDefault();
        closeModal();
    }

    const handleDelete = async () => {
        await deleteDownload(download.id);
        if (afterSave) {
            afterSave();
        }
        if (closeModal) {
            closeModal();
        }
    };

    const deleteDownloadButton = <APIButton
        color='red'
        floated='left'
        onClick={handleDelete}
        confirmContent='Are you sure you want to delete this download?'
        confirmButton='Delete'
        disabled={disabled}
        obeyWROLMode={true}
    >Delete</APIButton>;

    return <Form onSubmit={handleSubmit}>
        {loading && <Dimmer active><Loader/></Dimmer>}
        <Grid columns={2} stackable>
            <Grid.Row>
                <Grid.Column width={12}>
                    <FormInput
                        label='URL'
                        name='url'
                        type='url'
                        value={state.url}
                        placeholder='https://example.com/videos'
                        onChange={handleInputChange}
                        error={!urlValid}
                    />
                </Grid.Column>
                <Grid.Column width={4}>
                    <FormField>
                        <label>Download Frequency</label>
                        <Dropdown selection
                                  name='frequency'
                                  placeholder='Frequency'
                                  value={state.frequency}
                                  disabled={disabled}
                                  options={frequencyOptions.slice(1)}
                                  onChange={handleInputChange}
                        />
                    </FormField>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row>
                <Grid.Column>
                    <FormInput
                        label='Excluded URLs'
                        name='excluded_urls'
                        type='text'
                        value={state.excluded_urls}
                        onChange={handleInputChange}
                    />
                </Grid.Column>
                <Grid.Column>
                    <FormInput
                        label='Destination'
                        name='destination'
                        type='text'
                        value={state.destination}
                        onChange={handleInputChange}
                    />
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={1}>
                <Grid.Column textAlign='right'>
                    {deleteDownloadButton}
                    <Button onClick={handleClose}>Cancel</Button>
                    <Button color='violet' disabled={!urlValid}>Save</Button>
                </Grid.Column>
            </Grid.Row>
        </Grid>
    </Form>
}


class RecurringDownloadRow extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            errorModalOpen: false,
            editModalOpen: false,
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

    handleRestart = async () => {
        const {id} = this.props;
        try {
            const response = await restartDownload(id);
            if (response.status !== 204) {
                throw Error('Unable to restart download');
            }
        } catch (e) {
            toast({
                type: 'error',
                title: 'Error',
                description: 'Unable to restart download',
                time: 5000,
            })
            throw e;
        } finally {
            if (this.props.fetchDownloads) {
                this.props.fetchDownloads();
            }
        }
    }

    render() {
        let {
            url,
            frequency,
            last_successful_download,
            status,
            location,
            next_download,
            error,
            downloader,
            channel_id
        } = this.props;
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

        const editButton = <>
            <Button icon='edit' onClick={() => this.setState({editModalOpen: true})}/>
        </>

        const restartButton = <>
            <APIButton
                color='green'
                icon='redo'
                confirmContent='Are you sure you want to restart this download?'
                confirmButton='Restart'
                onClick={this.handleRestart}
                obeyWROLMode={true}
            />
        </>;

        // Show "now" if we have passed the next_download.
        let next = 'now';
        if (next_download && new Date() < new Date(next_download)) {
            next = isoDatetimeToElapsedPopup(next_download);
        }

        const handleClose = () => this.setState({editModalOpen: false});
        const afterSave = () => {
            if (this.props.fetchDownloads) {
                this.props.fetchDownloads();
            }
            handleClose();
        }
        const editModal = <Modal closeIcon
                                 open={this.state.editModalOpen}
                                 onClose={handleClose}
        >
            <ModalHeader>Edit Download</ModalHeader>
            <ModalContent>
                {downloader === 'video_channel' ?
                    <ChannelDownloadForm download={this.props} closeModal={handleClose}
                                         afterSave={afterSave}/>
                    : <DownloadEditForm download={this.props} closeModal={handleClose}
                                        afterSave={afterSave}/>
                }
            </ModalContent>
        </Modal>;

        return <TableRow>
            <TableCell className='column-ellipsis'>
                {link(url)}
            </TableCell>
            <TableCell>{secondsToFrequency(frequency)}</TableCell>
            <TableCell>
                {last_successful_download ? isoDatetimeToElapsedPopup(last_successful_download) : null}
                {status === 'pending' ? <Loader active inline size='tiny'/> : null}
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
}

class OnceDownloadRow extends React.Component {
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

    handleRestart = async () => {
        try {
            await restartDownload(this.props.id);
        } catch (e) {
            toast({
                type: 'error',
                title: 'Error',
                description: 'Unable to restart download',
                time: 5000,
            })
            throw e;
        }
        await this.props.fetchDownloads();
    };

    render() {
        let {url, last_successful_download, status, location, error} = this.props;

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
                        icon='redo'
                        confirmContent='Are you sure you want to restart this download?'
                        confirmButton='Start'
                        onClick={this.handleRestart}
                        obeyWROLMode={true}
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
            <TableCell className='column-ellipsis'>
                {link(url)}
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

export function RecurringDownloadsTable({downloads, fetchDownloads}) {
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
                {downloads.map(i => <RecurringDownloadRow key={i.id} fetchDownloads={fetchDownloads} {...i}/>)}
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
