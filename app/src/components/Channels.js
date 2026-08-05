import React, {useState} from "react";
import {useHotkeys} from "react-hotkeys-hook";
import {createChannel, deleteChannel, refreshChannel, tagChannel, tagChannelInfo} from "../api";
import {CollectionTagModal} from "./collections/CollectionTagModal";
import {CollectionReorganizeModal} from "./collections/CollectionReorganizeModal";
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
import {Link, useNavigate, useParams} from "react-router";
import {useChannel, useChannels, useOneQuery} from "../hooks/customHooks";
import _ from "lodash";
import {
    Button,
    Grid,
    Group,
    Header,
    Loading,
    Message,
    Modal,
    Panel,
    Stack,
    Statistic,
    StatisticGroup,
    toast,
} from "./ui";
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

    return <Panel>
        <Header as='h1'>Statistics</Header>
        <StatisticGroup>
            <Statistic value={statistics.video_count} label='Videos'/>
            <Statistic value={humanFileSize(statistics.size, true)} label='Total Size'/>
            <Statistic value={humanFileSize(statistics.largest_video, true)} label='Largest Video'/>
            <Statistic value={secondsToFullDuration(statistics.length)} label='Total Duration'/>
            <Statistic value={humanNumber(statistics.video_tags)} label='Video Tags'/>
        </StatisticGroup>
    </Panel>
}


export function ChannelEditPage() {
    const navigate = useNavigate();
    const {channelId} = useParams();

    const [tagEditModalOpen, setTagEditModalOpen] = useState(false);
    const [downloadModalOpen, setDownloadModalOpen] = useState(false);
    const [reorganizeModalOpen, setReorganizeModalOpen] = useState(false);

    const {channel, form, fetchChannel} = useChannel(channelId);

    useTitle(_.isEmpty(channel) ? null : `${channel.name} Channel`);

    if (!form.ready) {
        return <Loading/>;
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
        role='danger'
        size='small'
        confirmContent='Are you sure you want to delete this channel? No video files will be deleted.'
        confirmButton='Delete'
        confirmHeader='Delete Channel?'
        onClick={handleDelete}
        obeyWROLMode={true}
        style={{marginTop: '1em'}}
    >Delete</APIButton>;

    const refreshButton = <APIButton
        role='primary'
        size='small'
        onClick={handleRefreshChannel}
        obeyWROLMode={true}
        style={{marginTop: '1em'}}
    >Refresh</APIButton>;

    const tagButton = <Button
        type="button"
        size='small'
        onClick={() => setTagEditModalOpen(true)}
        role='primary'
        style={{marginTop: '1em'}}
    >Tag</Button>;

    const reorganizeButton = (
        <APIButton
            role='retry'
            size='small'
            onClick={() => setReorganizeModalOpen(true)}
            obeyWROLMode={true}
            style={{marginTop: '1em'}}
        >Reorganize Files</APIButton>
    );

    const actionButtons = <>
        {deleteButton}
        {refreshButton}
        {tagButton}
        {reorganizeButton}
    </>;

    const downloadMissingDataInfo = 'Automatically download missing comments, etc, in the background.';
    const downloadMissingDataLabel = <>Download Missing Data<InfoPopup content={downloadMissingDataInfo}/></>;

    return <>
        <BackButton/>
        <Link to={`/videos/channel/${channel.id}/video`}>
            <Button>Videos</Button>
        </Link>

        {channel?.needs_reorganization && (
            <Message kind='warning' title='File Format Changed'>
                <p>
                    The file name format has changed. Click "Reorganize Files" to move existing files
                    to match the new format.
                </p>
            </Message>
        )}

        <CollectionEditForm
            form={form}
            title="Edit Channel"
            wrolModeContent='Channel editing is disabled while in WROL Mode.'
            actionButtons={actionButtons}
            appliedTagName={channel?.tag_name}
            onSubmit={handleSubmit}
        >
            <Grid>
                <Grid.Col span={{base: 12, sm: 6}}>
                    <InputForm
                        form={form}
                        label="Channel Name"
                        name="name"
                        placeholder="Short Channel Name"
                        required={true}
                    />
                </Grid.Col>
                <Grid.Col span={{base: 12, sm: 6}}>
                    <DestinationForm
                        form={form}
                        label='Directory'
                        name='directory'
                        path='directory'
                        required={true}
                    />
                </Grid.Col>
                <Grid.Col span={12}>
                    <ToggleForm
                        form={form}
                        label={downloadMissingDataLabel}
                        path='download_missing_data'
                    />
                </Grid.Col>
                {(channel.url || channel.rss_url) &&
                    <Grid.Col span={12}>
                        <SimpleAccordion title='Details'>
                            <Stack gap='sm'>
                                {channel.url && <div>
                                    <Header as='h4'>URL</Header>
                                    <a href={channel.url}>{channel.url}</a>
                                </div>}
                                {channel.rss_url && <div>
                                    <Header as='h4'>RSS URL</Header>
                                    <a href={channel.rss_url}>{channel.rss_url}</a>
                                </div>}
                            </Stack>
                        </SimpleAccordion>
                    </Grid.Col>}
            </Grid>
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

        {/* Reorganize Modal */}
        <CollectionReorganizeModal
            open={reorganizeModalOpen}
            onClose={() => setReorganizeModalOpen(false)}
            collectionId={channel?.collection_id}
            collectionName={channel?.name}
            onComplete={fetchChannel}
            needsReorganization={channel?.needs_reorganization}
        />

        {/* Downloads Segment */}
        <Panel>
            <Group justify='space-between' align='center' wrap='wrap'>
                <Header as='h1'>Downloads</Header>
                <Button onClick={() => setDownloadModalOpen(!downloadModalOpen)}>
                    New Download
                </Button>
            </Group>
            <Modal size='small' open={downloadModalOpen} onClose={() => setDownloadModalOpen(false)}>
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
        </Panel>

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
        messageRow = <Grid.Col span={12}>
            {error &&
                <Message kind='error' title={messageHeader}>{messageContent}</Message>}
            {success &&
                <Message kind='success' title={messageHeader}>{messageContent}</Message>}
        </Grid.Col>
    }

    return <>
        <BackButton/>

        <Panel>
            <Header as="h1">New Channel</Header>
            <WROLModeMessage content='Channel creation is disabled while WROL Mode is enabled.'/>
            <form
                id="newChannel"
                autoComplete="off"
                onSubmit={e => e.preventDefault()}
            >
                <Grid>
                    <Grid.Col span={{base: 12, sm: 6}}>
                        <InputForm
                            form={form}
                            label="Channel Name"
                            name="name"
                            placeholder="Short Channel Name"
                            required={true}
                        />
                    </Grid.Col>
                    <Grid.Col span={{base: 12, sm: 6}}>
                        <DestinationForm
                            form={form}
                            label='Directory'
                            name='directory'
                            path='directory'
                            required={true}
                        />
                    </Grid.Col>
                    <Grid.Col span={12}>
                        <ToggleForm
                            form={form}
                            label={downloadMissingDataLabel}
                            path='download_missing_data'
                        />
                    </Grid.Col>
                    {messageRow}
                    <Grid.Col span={{base: 12, sm: 8}}>
                        <DownloadTagsSelector
                            form={form}
                            limit={1}
                            path='tag_name'
                            name='tag_name'
                        />
                    </Grid.Col>
                    <Grid.Col span={{base: 12, sm: 4}}>
                        <div style={{textAlign: 'right'}}>
                            <APIButton
                                role='primary'
                                size='big'
                                onClick={handleSubmit}
                                disabled={form.disabled}
                                obeyWROLMode={true}
                            >Save</APIButton>
                        </div>
                    </Grid.Col>
                </Grid>
            </form>
        </Panel>
    </>;
}

export function ChannelsPage() {
    useTitle('Channels');

    const [channels] = useChannels();
    const [searchStr, setSearchStr] = useOneQuery('name');
    const searchInputRef = React.useRef();

    useHotkeys('f', (e) => {
        e.preventDefault();
        if (searchInputRef.current) {
            searchInputRef.current.focus();
        }
    }, {enableOnFormTags: false});

    // Header section matching DomainsPage pattern.  No `mb`: this is a top-level block of the
    // page, and the page's stack spaces it -- its own margin was added to that gap.
    const header = <Group justify='space-between' align='flex-end' wrap='wrap'>
        <SearchInput
            placeholder='Name filter...'
            size='large'
            searchStr={searchStr}
            disabled={!Array.isArray(channels) || channels.length === 0}
            onClear={() => setSearchStr('')}
            onChange={setSearchStr}
            onSubmit={null}
            inputRef={searchInputRef}
        />
        <Link to='/videos/channel/new'>
            <Button role='primary'>New Channel</Button>
        </Link>
    </Group>;

    // Empty state
    if (channels && channels.length === 0) {
        return <>
            {header}
            <Message title='No channels exist yet!'>
                <Link to='/videos/channel/new'>Create one.</Link>
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
