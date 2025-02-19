import React, {useState} from "react";
import {Grid, Input, StatisticLabel, StatisticValue, TableCell, TableRow,} from "semantic-ui-react";
import {createChannel, deleteChannel, refreshChannel, tagChannel, tagChannelInfo, updateChannel} from "../api";
import {
    APIButton,
    BackButton,
    ErrorMessage,
    humanFileSize,
    humanNumber,
    InfoPopup,
    SearchInput,
    secondsToFrequency,
    secondsToFullDuration,
    SimpleAccordion,
    Toggle,
    useTitle,
    WROLModeMessage
} from "./Common";
import {Link, useNavigate, useParams} from "react-router-dom";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import {useChannel, useChannels, useOneQuery} from "../hooks/customHooks";
import _ from "lodash";
import {
    Button,
    Form,
    Header,
    Loader,
    Modal,
    ModalActions,
    ModalContent,
    ModalHeader,
    Segment,
    Statistic
} from "./Theme";
import {Media, ThemeContext} from "../contexts/contexts";
import {SortableTable} from "./SortableTable";
import {toast} from "react-semantic-toasts-2";
import {RecurringDownloadsTable} from "./admin/Downloads";
import {TagsContext, TagsSelector} from "../Tags";
import {InputForm, ToggleForm} from "../hooks/useForm";
import {ChannelDownloadForm, DestinationForm, DownloadTagsSelector} from "./Download";


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


export function ChannelPage({create, header}) {
    // Used to display messages to maintainer.
    const [error, setError] = useState(false);
    const [success, setSuccess] = useState(false);
    const [messageHeader, setMessageHeader] = useState();
    const [messageContent, setMessageContent] = useState();

    const [downloadModalOpen, setDownloadModalOpen] = useState(false);

    const navigate = useNavigate();
    const {channelId} = useParams();
    const {SingleTag} = React.useContext(TagsContext);

    const [tagEditModalOpen, setTagEditModalOpen] = useState(false);
    const [newTagName, setNewTagName] = useState(null);
    const [moveToTagDirectory, setMoveToTagDirectory] = useState(true);
    const [newTagDirectory, setNewTagDirectory] = useState('');

    const {channel, form, fetchChannel} = useChannel(channelId);

    useTitle(_.isEmpty(channel) ? null : `${channel.name} Channel`);

    React.useEffect(() => {
        if (channel && channel.tag_name !== newTagName) {
            setNewTagName(channel.tag_name);
        }
    }, [channel]);

    if (!create && !form.ready) {
        // Waiting for editing Channel to be fetched.
        return <Loader active/>;
    }

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
        };

        let response = null;
        try {
            if (create !== undefined) {
                // Can create a Channel with a Tag.
                body.tag_name = _.isEmpty(channel.tag_name) ? null : channel.tag_name[0];
                response = await createChannel(body);
            } else {
                response = await updateChannel(channelId, body);
            }
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
            let channel = data['channel'];

            if (response.status === 201) {
                setSuccessMessage(
                    'Channel created',
                    <span>
                        Your channel was created.  View it <Link to={`/videos/channel/${channel.id}/edit`}>here</Link>
                    </span>
                );
            } else {
                await fetchChannel();
                toast({
                    type: 'success',
                    title: 'Channel updated',
                    description: 'The channel was updated',
                })
            }

        } else if (response) {
            // Some error occurred.
            let error = await response.json();
            let cause = error.cause;
            if (cause && cause.code === 'CHANNEL_DIRECTORY_CONFLICT') {
                setErrorMessage(
                    'Invalid directory',
                    'This directory is already used by another channel',
                    'directory',
                );
            } else if (cause && cause.code === 'CHANNEL_NAME_CONFLICT') {
                setErrorMessage(
                    'Invalid name',
                    'This channel name is already taken',
                    'name',
                );
            } else {
                setErrorMessage('Invalid channel', error.message || error.error || 'Unable to save channel.  See logs.');
            }
        } else {
            console.error('Did not get a response for channel!');
        }
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
            setErrorMessage('Failed to delete', 'Failed to delete this channel, check logs.');
        }
    }

    let downloads = channel && channel.downloads ? channel.downloads : null;

    const afterNewDownloadSave = async () => {
        setDownloadModalOpen(false);
        await form.fetcher();
    }

    const onDelete = async () => {
        await form.fetcher();
        setDownloadModalOpen(false);
    }

    const handleTagEditChannel = async () => {
        try {
            await tagChannel(channelId, newTagName, moveToTagDirectory ? newTagDirectory : null);
            setTagEditModalOpen(false);
        } catch (e) {
            console.error('Failed to tag channel', e);
        } finally {
            setTimeout(async () => {
                // Delay fetch because config needs to be written.
                await fetchChannel();
            }, 500);
        }
    }

    const handleTagSelectMoveSuggestion = async (newTagName_) => {
        setNewTagName(newTagName_);
        try {
            // Get suggested Tag directory for this Tag and Channel.
            const videosDestination = await tagChannelInfo(channelId, newTagName_);
            setNewTagDirectory(videosDestination);
        } catch (e) {
            console.error('Failed to tag channel', e);
        }
    }

    let tagEditModal;
    if (!create) {
        // User is editing the Tag of the Channel.
        tagEditModal = <Modal
            open={tagEditModalOpen}
            onClose={() => setTagEditModalOpen(false)}
            closeIcon
        >
            <ModalHeader>{channel.tag_name ? 'Modify Tag' : 'Add Tag'}</ModalHeader>
            <ModalContent>
                <Grid columns={1}>
                    <Grid.Row>
                        <Grid.Column>
                            <TagsSelector
                                limit={1}
                                selectedTagNames={newTagName ? [newTagName] : []}
                                onAdd={handleTagSelectMoveSuggestion}
                                onRemove={() => handleTagSelectMoveSuggestion(null)}
                            />
                        </Grid.Column>
                    </Grid.Row>
                    <Grid.Row>
                        <Grid.Column>
                            <Toggle
                                label='Move to directory: '
                                checked={moveToTagDirectory}
                                onChange={setMoveToTagDirectory}
                            />
                        </Grid.Column>
                    </Grid.Row>
                    <Grid.Row>
                        <Grid.Column>
                            <Input fluid
                                   value={newTagDirectory}
                                   onChange={(e, {value}) => setNewTagDirectory(value)}
                                   disabled={!moveToTagDirectory}
                            />
                        </Grid.Column>
                    </Grid.Row>
                </Grid>
            </ModalContent>
            <ModalActions>
                <Button onClick={() => setTagEditModalOpen(false)}>Cancel</Button>
                <APIButton
                    color='violet'
                    onClick={handleTagEditChannel}
                    obeyWROLMode={true}
                >{moveToTagDirectory ? 'Move' : 'Save'}</APIButton>
            </ModalActions>
        </Modal>;
    }

    let channelUrlRow;
    if (channel && channel.url) {
        channelUrlRow = <Grid.Row columns={1}>
            <Grid.Column>
                <Header as='h4'>URL</Header>
                <a href={channel.url}>{channel.url}</a>
            </Grid.Column>
        </Grid.Row>;
    }

    let channelRssUrlRow;
    if (channel && channel.rss_url) {
        channelRssUrlRow = <Grid.Row columns={1}>
            <Grid.Column>
                <Header as='h4'>RSS URL</Header>
                <a href={channel.rss_url}>{channel.rss_url}</a>
            </Grid.Column>
        </Grid.Row>;
    }

    let channelTagRow;
    if (channel && channel.tag_name) {
        channelTagRow = <Grid.Row columns={1}>
            <Grid.Column>
                {channel.tag_name && !create && <SingleTag name={channel.tag_name}/>}
            </Grid.Column>
        </Grid.Row>;
    }

    const downloadMissingDataInfo = 'Automatically download missing comments, etc, in the background.';
    const downloadMissingDataLabel = <>Download Missing Data<InfoPopup content={downloadMissingDataInfo}/></>;
    const downloadMissingDataRow = <Grid.Row>
        <Grid.Column>
            <ToggleForm
                form={form}
                label={downloadMissingDataLabel}
                path='download_missing_data'
            />
        </Grid.Column>
    </Grid.Row>;

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
        {!create &&
            <Link to={`/videos/channel/${channel.id}/video`}>
                <Button>Videos</Button>
            </Link>}

        <Segment>
            <Header as="h1">{header}</Header>
            <WROLModeMessage content='Channel page is disabled while WROL Mode is enabled.'/>
            <Form
                id="editChannel"
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
                    {channelTagRow}
                    {downloadMissingDataRow}
                    {!create && (channel.url || channel.rss_url) &&
                        <SimpleAccordion title='Details'>
                            <Grid>
                                {channelUrlRow}
                                {channelRssUrlRow}
                            </Grid>
                        </SimpleAccordion>}
                    {messageRow}
                    <Grid.Row>
                        <Grid.Column width={8}>
                            {!create ?
                                <>
                                    <APIButton
                                        color='red'
                                        size='small'
                                        confirmContent='Are you sure you want to delete this channel?  No video files will be deleted.'
                                        confirmButton='Delete'
                                        confirmHeader='Delete Channel?'
                                        onClick={handleDelete}
                                        obeyWROLMode={true}
                                        style={{marginTop: '1em'}}
                                    >Delete</APIButton>
                                    <APIButton
                                        color='blue'
                                        size='small'
                                        onClick={handleRefreshChannel}
                                        obeyWROLMode={true}
                                        style={{marginTop: '1em'}}
                                    >Refresh</APIButton>
                                    <Button
                                        size='small'
                                        onClick={() => setTagEditModalOpen(true)}
                                        color='green'
                                    >Tag</Button>
                                    {tagEditModal}
                                </>
                                : <DownloadTagsSelector
                                    form={form}
                                    limit={1}
                                    path='tag_name'
                                    name='tag_name'
                                />
                            }
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

        {!create && <Segment>
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
                <ModalContent>
                    <Header as='h2'>New Channel Download</Header>
                    <ChannelDownloadForm
                        channel_id={channelId}
                        onSuccess={afterNewDownloadSave}
                        onCancel={() => setDownloadModalOpen(false)}
                        onDelete={onDelete}
                    />
                </ModalContent>
            </Modal>

            <RecurringDownloadsTable downloads={downloads} fetchDownloads={fetchChannel} onDelete={onDelete}/>
        </Segment>}

        {channel && channel.statistics && <ChannelStatistics statistics={channel.statistics}/>}
    </>
}

export function ChannelEditPage(props) {
    return <ChannelPage header="Edit Channel" {...props}/>;
}

export function ChannelNewPage(props) {
    useTitle('New Channel');
    return <ChannelPage header='New Channel' {...props} create/>
}

function ChannelRow({channel}) {
    const {SingleTag} = React.useContext(TagsContext);

    const videosTo = `/videos/channel/${channel.id}/video`;

    const {inverted} = React.useContext(ThemeContext);
    const editTo = `/videos/channel/${channel.id}/edit`;
    const buttonClass = `ui button secondary ${inverted}`;

    return <TableRow>
        <TableCell>
            <Link to={videosTo}>{channel.name}</Link>
        </TableCell>
        <TableCell>
            {channel.tag_name ? <SingleTag name={channel.tag_name}/> : null}
        </TableCell>
        <TableCell>
            {channel.video_count}
        </TableCell>
        <TableCell>
            {channel.url && channel.minimum_frequency ? secondsToFrequency(channel.minimum_frequency) : null}
        </TableCell>
        <TableCell>
            {channel.size ? humanFileSize(channel.size) : null}
        </TableCell>
        <TableCell textAlign='right'>
            <Link className={buttonClass} to={editTo}>Edit</Link>
        </TableCell>
    </TableRow>;
}

function MobileChannelRow({channel}) {
    const {SingleTag} = React.useContext(TagsContext);

    const editTo = `/videos/channel/${channel.id}/edit`;
    const videosTo = `/videos/channel/${channel.id}/video`;
    return <TableRow verticalAlign='top'>
        <TableCell width={10} colSpan={2}>
            <Link as='h3' to={videosTo}>
                <h3>
                    {channel.name}
                </h3>
                {channel.tag_name ? <SingleTag name={channel.tag_name}/> : null}
            </Link>
            <p>
                Videos: {channel.video_count}
            </p>
        </TableCell>
        <TableCell width={6} colSpan={2} textAlign='right'>
            <p>
                <Link className="ui button secondary" to={editTo}>Edit</Link>
            </p>
        </TableCell>
    </TableRow>;
}


export function ChannelsPage() {
    useTitle('Channels');

    const {channels} = useChannels();
    const [searchStr, setSearchStr] = useOneQuery('name');
    // Hides Channels with few videos.
    const [hideSmall, setHideSmall] = React.useState(true);
    const enoughChannelsToHideSmall = channels && channels.length > 20;

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

    const headers = [
        {key: 'name', text: 'Name', sortBy: [i => i['name'].toLowerCase()], width: 8},
        {key: 'tag', text: 'Tag', sortBy: [i => i['tag_name'], i => i['name'].toLowerCase()], width: 2},
        {key: 'video_count', text: 'Videos', sortBy: [i => i['video_count'], i => i['name'].toLowerCase()], width: 2},
        {
            key: 'download_frequency',
            text: 'Download Frequency',
            sortBy: [i => i['minimum_frequency'], i => i['name'].toLowerCase()],
            width: 2
        },
        {key: 'size', text: 'Size', sortBy: [i => i['size'], i => i['name'].toLowerCase()], width: 2},
        {key: 'manage', text: 'Manage', width: 2},
    ];
    const mobileHeaders = [
        {key: 'name', text: 'Name', sortBy: [i => i['name'].toLowerCase()]},
        {key: 'video_count', text: 'Videos', sortBy: [i => i['video_count'], i => i['name'].toLowerCase()]},
        {key: 'manage', text: 'Manage'},
    ];

    if (channels && channels.length === 0) {
        return <>
            {header}
            <Message>
                <Message.Header>No channels exist yet!</Message.Header>
                <Message.Content><Link to='/videos/channel/new'>Create one.</Link></Message.Content>
            </Message>
        </>
    } else if (channels === undefined) {
        return <>
            {header}
            <ErrorMessage>Could not fetch Channels</ErrorMessage>
        </>
    }

    let filteredChannels = channels;
    if (searchStr && Array.isArray(channels)) {
        const re = new RegExp(_.escapeRegExp(searchStr), 'i');
        filteredChannels = channels.filter(i => re.test(i['name']));
    } else if (channels && hideSmall && enoughChannelsToHideSmall) {
        // Get the top 80% of Channels.
        let index80 = Math.floor(channels.length * 0.8);
        const sortedChannels = channels.sort((a, b) => b.video_count - a.video_count);
        let percentile = sortedChannels[index80].video_count;
        filteredChannels = channels.filter(i => {
            return i.video_count > percentile || i.name.toLowerCase() === 'wrolpi'
        });
        if (filteredChannels.length < 21) {
            // Filtering hid too many Channels, show them all.
            filteredChannels = channels;
        }
    }

    return <>
        {header}
        <Media at='mobile'>
            <SortableTable
                tableProps={{striped: true, size: 'small', unstackable: true}}
                data={filteredChannels}
                tableHeaders={mobileHeaders}
                defaultSortColumn='name'
                rowKey='id'
                rowFunc={(i, sortData) => <MobileChannelRow key={i.id} channel={i} sortData={sortData}/>}
            />
        </Media>
        <Media greaterThanOrEqual='tablet'>
            <SortableTable
                tableProps={{striped: true, size: 'large', unstackable: true, compact: true}}
                data={filteredChannels}
                tableHeaders={headers}
                defaultSortColumn='name'
                rowKey='id'
                rowFunc={(i, sortData) => <ChannelRow key={i.id} channel={i} sortData={sortData}/>}
            />
        </Media>
        <Grid textAlign='center'>
            <Grid.Row>
                <Grid.Column>
                    <Button
                        style={{marginTop: '1em'}}
                        onClick={() => setHideSmall(!hideSmall)}
                        size='big'
                        disabled={!enoughChannelsToHideSmall}
                    >Show {hideSmall ? 'More' : 'Less'}</Button>
                </Grid.Column>
            </Grid.Row>
        </Grid>
    </>
}
