import React, {useState} from "react";
import {Grid, StatisticLabel, StatisticValue,} from "semantic-ui-react";
import {createChannel, deleteChannel, refreshChannel, tagChannel, tagChannelInfo} from "../api";
import {CollectionTagModal} from "./collections/CollectionTagModal";
import {
    APIButton,
    BackButton,
    ErrorMessage,
    humanFileSize,
    humanNumber,
    InfoPopup,
    SearchInput,
    secondsToFullDuration,
    SimpleAccordion,
    useTitle,
    WROLModeMessage
} from "./Common";
import {Link, useNavigate, useParams} from "react-router-dom";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import {useChannel, useChannels, useOneQuery} from "../hooks/customHooks";
import _ from "lodash";
import {Button, Form, Header, Loader, Modal, Segment, Statistic} from "./Theme";
import {toast} from "react-semantic-toasts-2";
import {RecurringDownloadsTable} from "./admin/Downloads";
import {InputForm, ToggleForm} from "../hooks/useForm";
import {ChannelDownloadForm, DestinationForm, DownloadTagsSelector} from "./Download";
import {CollectionTable} from "./collections/CollectionTable";
import {CollectionEditForm} from "./collections/CollectionEditForm";

// Channel table column configuration
const CHANNEL_COLUMNS = [
    {key: 'name', label: 'Name', sortable: true, width: 7},
    {key: 'tag_name', label: 'Tag', sortable: true, width: 2},
    {key: 'video_count', label: 'Videos', sortable: true, align: 'right', width: 2},
    {
        key: 'min_download_frequency',
        label: 'Download Frequency',
        sortable: true,
        format: 'frequency',
        width: 2,
        hideOnMobile: true
    },
    {key: 'total_size', label: 'Size', sortable: true, align: 'right', format: 'bytes', width: 2, hideOnMobile: true},
    {key: 'actions', label: 'Manage', sortable: false, type: 'actions', width: 1}
];

const CHANNEL_ROUTES = {
    list: '/videos/channel',
    edit: '/videos/channel/:id/edit',
    search: '/videos/channel/:id/video',
    id_field: 'channel_id'
};

function ChannelStatistics({statistics}) {
    if (!statistics) {
        return <></>
    }

    return <Segment>
        <Header as='h1'>Statistics</Header>
        <Statistic>
            <StatisticValue>{statistics.video_count}</StatisticValue>
            <StatisticLabel>Videos</StatisticLabel>
        </Statistic>
        <Statistic>
            <StatisticValue>{humanFileSize(statistics.size, true)}</StatisticValue>
            <StatisticLabel>Total Size</StatisticLabel>
        </Statistic>
        <Statistic>
            <StatisticValue>{humanFileSize(statistics.largest_video, true)}</StatisticValue>
            <StatisticLabel>Largest Video</StatisticLabel>
        </Statistic>
        <Statistic>
            <StatisticValue>{secondsToFullDuration(statistics.length)}</StatisticValue>
            <StatisticLabel>Total Duration</StatisticLabel>
        </Statistic>
        <Statistic>
            <StatisticValue>{humanNumber(statistics.video_tags)}</StatisticValue>
            <StatisticLabel>Video Tags</StatisticLabel>
        </Statistic>
    </Segment>
}


export function ChannelEditPage() {
    const navigate = useNavigate();
    const {channelId} = useParams();

    const [tagEditModalOpen, setTagEditModalOpen] = useState(false);
    const [downloadModalOpen, setDownloadModalOpen] = useState(false);

    const {channel, form, fetchChannel} = useChannel(channelId);

    useTitle(_.isEmpty(channel) ? null : `${channel.name} Channel`);

    if (!form.ready) {
        return <Loader active/>;
    }

    const handleRefreshChannel = async (e) => {
        if (e) {
            e.preventDefault();
        }
        await refreshChannel(channelId);
    }

    const handleDelete = async () => {
        try {
            let response = await deleteChannel(channelId);
            if (response.status === 204) {
                navigate('/videos/channel');
            }
        } catch (e) {
            console.error('Failed to delete channel', e);
        }
    }

    // Handler for tag modal save
    const handleTagSave = async (tagName, directory) => {
        try {
            await tagChannel(channelId, tagName, directory);
            toast({
                type: 'success',
                title: 'Channel Tagged',
                description: `Channel has been tagged with "${tagName}"`,
                time: 3000,
            });
        } catch (e) {
            console.error('Failed to tag channel', e);
        } finally {
            setTimeout(async () => {
                await fetchChannel();
            }, 500);
        }
    };

    // Handler for fetching tag info
    const handleGetTagInfo = async (tagName) => {
        return await tagChannelInfo(channelId, tagName);
    };

    const afterNewDownloadSave = async () => {
        setDownloadModalOpen(false);
        await form.fetcher();
    }

    const onDelete = async () => {
        await form.fetcher();
        setDownloadModalOpen(false);
    }

    const handleSubmit = async (e) => {
        if (e) e.preventDefault();
        try {
            await form.onSubmit();
            toast({
                type: 'success',
                title: 'Channel Updated',
                description: 'Channel was successfully updated',
                time: 3000,
            });
            await fetchChannel();
        } catch (e) {
            console.error('Failed to update channel:', e);
        }
    };

    const deleteButton = <APIButton
        color='red'
        size='small'
        confirmContent='Are you sure you want to delete this channel? No video files will be deleted.'
        confirmButton='Delete'
        confirmHeader='Delete Channel?'
        onClick={handleDelete}
        obeyWROLMode={true}
        style={{marginTop: '1em'}}
    >Delete</APIButton>;

    const refreshButton = <APIButton
        color='blue'
        size='small'
        onClick={handleRefreshChannel}
        obeyWROLMode={true}
        style={{marginTop: '1em'}}
    >Refresh</APIButton>;

    const tagButton = <Button
        type="button"
        size='small'
        onClick={() => setTagEditModalOpen(true)}
        color='green'
        style={{marginTop: '1em'}}
    >Tag</Button>;

    const actionButtons = <>
        {deleteButton}
        {refreshButton}
        {tagButton}
    </>;

    const downloadMissingDataInfo = 'Automatically download missing comments, etc, in the background.';
    const downloadMissingDataLabel = <>Download Missing Data<InfoPopup content={downloadMissingDataInfo}/></>;

    return <>
        <BackButton/>
        <Link to={`/videos/channel/${channel.id}/video`}>
            <Button>Videos</Button>
        </Link>

        <CollectionEditForm
            form={form}
            title="Edit Channel"
            wrolModeContent='Channel editing is disabled while in WROL Mode.'
            actionButtons={actionButtons}
            appliedTagName={channel?.tag_name}
            onSubmit={handleSubmit}
        >
            <Grid.Row>
                <Grid.Column width={8}>
                    <InputForm
                        form={form}
                        label="Channel Name"
                        name="name"
                        placeholder="Short Channel Name"
                        required={true}
                    />
                </Grid.Column>
                <Grid.Column width={8}>
                    <DestinationForm
                        form={form}
                        label='Directory'
                        name='directory'
                        path='directory'
                        required={true}
                    />
                </Grid.Column>
            </Grid.Row>
            <Grid.Row>
                <Grid.Column>
                    <ToggleForm
                        form={form}
                        label={downloadMissingDataLabel}
                        path='download_missing_data'
                    />
                </Grid.Column>
            </Grid.Row>
            {(channel.url || channel.rss_url) &&
                <Grid.Row>
                    <Grid.Column>
                        <SimpleAccordion title='Details'>
                            <Grid>
                                {channel.url && <Grid.Row columns={1}>
                                    <Grid.Column>
                                        <Header as='h4'>URL</Header>
                                        <a href={channel.url}>{channel.url}</a>
                                    </Grid.Column>
                                </Grid.Row>}
                                {channel.rss_url && <Grid.Row columns={1}>
                                    <Grid.Column>
                                        <Header as='h4'>RSS URL</Header>
                                        <a href={channel.rss_url}>{channel.rss_url}</a>
                                    </Grid.Column>
                                </Grid.Row>}
                            </Grid>
                        </SimpleAccordion>
                    </Grid.Column>
                </Grid.Row>}
        </CollectionEditForm>

        {/* Tag Modal */}
        <CollectionTagModal
            open={tagEditModalOpen}
            onClose={() => setTagEditModalOpen(false)}
            currentTagName={channel.tag_name}
            originalDirectory={channel.directory}
            getTagInfo={handleGetTagInfo}
            onSave={handleTagSave}
            collectionName="Channel"
            hasDirectory={!!channel.directory}
        />

        {/* Downloads Segment */}
        <Segment>
            <Grid columns={2}>
                <Grid.Row>
                    <Grid.Column>
                        <Header as='h1'>Downloads</Header>
                    </Grid.Column>
                    <Grid.Column>
                        <Button floated='right'
                                onClick={() => setDownloadModalOpen(!downloadModalOpen)}
                        >
                            New Download
                        </Button>
                    </Grid.Column>
                </Grid.Row>
            </Grid>
            <Modal open={downloadModalOpen} closeIcon onClose={() => setDownloadModalOpen(false)}>
                <Modal.Content>
                    <Header as='h2'>New Channel Download</Header>
                    <ChannelDownloadForm
                        channel_id={channelId}
                        onSuccess={afterNewDownloadSave}
                        onCancel={() => setDownloadModalOpen(false)}
                        onDelete={onDelete}
                    />
                </Modal.Content>
            </Modal>

            <RecurringDownloadsTable downloads={channel?.downloads} fetchDownloads={fetchChannel} onDelete={onDelete}/>
        </Segment>

        {channel && channel.statistics && <ChannelStatistics statistics={channel.statistics}/>}
    </>;
}

export function ChannelNewPage() {
    useTitle('New Channel');

    // Used to display messages to maintainer.
    const [error, setError] = useState(false);
    const [success, setSuccess] = useState(false);
    const [messageHeader, setMessageHeader] = useState();
    const [messageContent, setMessageContent] = useState();

    const {channel, form} = useChannel(null);

    const setErrorMessage = (header, message) => {
        setError(true);
        setSuccess(false);
        setMessageHeader(header);
        setMessageContent(message);
    }

    const setSuccessMessage = (header, message) => {
        setError(false);
        setSuccess(true);
        setMessageHeader(header);
        setMessageContent(message);
    }

    const handleSubmit = async () => {
        const body = {
            name: channel.name,
            directory: channel.directory,
            url: channel.url,
            download_missing_data: channel.download_missing_data,
            tag_name: _.isEmpty(channel.tag_name) ? null : channel.tag_name[0],
        };

        let response = null;
        try {
            response = await createChannel(body);
        } catch (e) {
            console.error(e);
            toast({
                type: 'error',
                title: 'Unexpected server response',
                description: 'Could not save channel',
                time: 5000,
            });
            return;
        }

        if (response && response.ok) {
            let location = response.headers.get('Location');
            let channelResponse = await fetch(location);
            let data = await channelResponse.json();
            let newChannel = data['channel'];

            setSuccessMessage(
                'Channel created',
                <span>
                    Your channel was created. View it <Link to={`/videos/channel/${newChannel.id}/edit`}>here</Link>
                </span>
            );
        } else if (response) {
            let error = await response.json();
            let cause = error.cause;
            if (cause && cause.code === 'CHANNEL_DIRECTORY_CONFLICT') {
                setErrorMessage(
                    'Invalid directory',
                    'This directory is already used by another channel',
                );
            } else if (cause && cause.code === 'CHANNEL_NAME_CONFLICT') {
                setErrorMessage(
                    'Invalid name',
                    'This channel name is already taken',
                );
            } else {
                setErrorMessage('Invalid channel', error.message || error.error || 'Unable to save channel. See logs.');
            }
        } else {
            console.error('Did not get a response for channel!');
        }
    }

    const downloadMissingDataInfo = 'Automatically download missing comments, etc, in the background.';
    const downloadMissingDataLabel = <>Download Missing Data<InfoPopup content={downloadMissingDataInfo}/></>;

    let messageRow;
    if (error || success) {
        messageRow = <Grid.Row columns={1}>
            <Grid.Column>
                {error &&
                    <Message negative
                             header={messageHeader}
                             content={messageContent}
                    />}
                {success &&
                    <Message positive
                             header={messageHeader}
                             content={messageContent}
                    />}
            </Grid.Column>
        </Grid.Row>
    }

    return <>
        <BackButton/>

        <Segment>
            <Header as="h1">New Channel</Header>
            <WROLModeMessage content='Channel creation is disabled while WROL Mode is enabled.'/>
            <Form
                id="newChannel"
                error={error}
                success={success}
                autoComplete="off"
            >
                <Grid stackable columns={2}>
                    <Grid.Row>
                        <Grid.Column>
                            <InputForm
                                form={form}
                                label="Channel Name"
                                name="name"
                                placeholder="Short Channel Name"
                                required={true}
                            />
                        </Grid.Column>
                        <Grid.Column>
                            <DestinationForm
                                form={form}
                                label='Directory'
                                name='directory'
                                path='directory'
                                required={true}
                            />
                        </Grid.Column>
                    </Grid.Row>
                    <Grid.Row>
                        <Grid.Column>
                            <ToggleForm
                                form={form}
                                label={downloadMissingDataLabel}
                                path='download_missing_data'
                            />
                        </Grid.Column>
                    </Grid.Row>
                    {messageRow}
                    <Grid.Row>
                        <Grid.Column width={8}>
                            <DownloadTagsSelector
                                form={form}
                                limit={1}
                                path='tag_name'
                                name='tag_name'
                            />
                        </Grid.Column>
                        <Grid.Column>
                            <APIButton
                                color='violet'
                                size='big'
                                floated='right'
                                onClick={handleSubmit}
                                disabled={form.disabled}
                                obeyWROLMode={true}
                            >Save</APIButton>
                        </Grid.Column>
                    </Grid.Row>
                </Grid>
            </Form>
        </Segment>
    </>;
}

export function ChannelsPage() {
    useTitle('Channels');

    const [channels] = useChannels();
    const [searchStr, setSearchStr] = useOneQuery('name');

    // Header section matching DomainsPage pattern
    const header = <div style={{marginBottom: '1em'}}>
        <Grid stackable columns={2}>
            <Grid.Row>
                <Grid.Column>
                    <SearchInput
                        placeholder='Name filter...'
                        size='large'
                        searchStr={searchStr}
                        disabled={!Array.isArray(channels) || channels.length === 0}
                        onClear={() => setSearchStr('')}
                        onChange={setSearchStr}
                        onSubmit={null}
                    />
                </Grid.Column>
                <Grid.Column textAlign='right'>
                    <Link to='/videos/channel/new'>
                        <Button secondary>New Channel</Button>
                    </Link>
                </Grid.Column>
            </Grid.Row>
        </Grid>
    </div>;

    // Empty state
    if (channels && channels.length === 0) {
        return <>
            {header}
            <Message>
                <Message.Header>No channels exist yet!</Message.Header>
                <Message.Content><Link to='/videos/channel/new'>Create one.</Link></Message.Content>
            </Message>
        </>;
    }

    // Error state
    if (channels === undefined) {
        return <>
            {header}
            <ErrorMessage>Could not fetch Channels</ErrorMessage>
        </>;
    }

    return <>
        {header}
        <CollectionTable
            collections={channels}
            columns={CHANNEL_COLUMNS}
            routes={CHANNEL_ROUTES}
            searchStr={searchStr}
        />
    </>;
}
