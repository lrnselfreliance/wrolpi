import React, {useState} from "react";
import {Dimmer, Dropdown, Grid, Input, StatisticLabel, StatisticValue, TableCell, TableRow,} from "semantic-ui-react";
import {
    createChannel,
    createChannelDownload,
    deleteChannel,
    deleteDownload,
    refreshChannel,
    tagChannel,
    tagChannelInfo,
    updateChannel,
    updateChannelDownload
} from "../api";
import {
    APIButton,
    BackButton,
    DirectorySearch,
    ErrorMessage,
    frequencyOptions,
    HelpHeader,
    humanFileSize,
    humanNumber,
    RequiredAsterisk,
    SearchInput,
    secondsToFrequency,
    secondsToFullDuration,
    Toggle,
    useTitle,
    validURL,
    WROLModeMessage
} from "./Common";
import {Link, useNavigate, useParams} from "react-router-dom";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import {useChannel, useChannels, useOneQuery, useWROLMode} from "../hooks/customHooks";
import _ from "lodash";
import {
    Button,
    Form,
    FormField,
    FormGroup,
    FormInput,
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


function ChannelPage({create, header}) {
    const [disabled, setDisabled] = useState(false);
    const [error, setError] = useState(false);
    const [success, setSuccess] = useState(false);
    const [messageHeader, setMessageHeader] = useState();
    const [messageContent, setMessageContent] = useState();
    const [downloadModalOpen, setDownloadModalOpen] = useState(false);

    const navigate = useNavigate();
    const {channelId} = useParams();
    const {channel, ready: channelReady, changeValue, fetchChannel} = useChannel(channelId);
    const {SingleTag} = React.useContext(TagsContext);

    const [tagEditModalOpen, setTagEditModalOpen] = useState(false);
    const [newTagName, setNewTagName] = useState(null);
    const [moveToTagDirectory, setMoveToTagDirectory] = useState(true);
    const [newTagDirectory, setNewTagDirectory] = useState('');

    useTitle(_.isEmpty(channel) ? null : `${channel.name} Channel`);

    React.useEffect(() => {
        setNewTagName(channel.tag_name);
    }, [channel.tag_name]);

    if (!create && !channelReady) {
        // Waiting for editing Channel to be fetched.
        return <Loader active/>;
    }

    const handleInputChange = (e, {name, value}) => {
        if (e) {
            e.preventDefault();
        }
        changeValue(name, value);
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

    const handleSubmit = async (e) => {
        if (e) {
            e.preventDefault();
        }
        const body = {
            name: channel.name,
            directory: channel.directory,
            url: channel.url,
        };

        setDisabled(true);

        let response = null;
        try {
            if (create !== undefined) {
                // Can create a Channel with a Tag.
                body.tag_name = channel.tag_name;
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
        } finally {
            setDisabled(false);
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
                setErrorMessage('Invalid channel', 'Unable to save channel.  See logs.');
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
        await fetchChannel();
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
                >Save</APIButton>
            </ModalActions>
        </Modal>;
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
                <FormGroup>
                    <FormField width={8}>
                        <FormInput required
                                   label="Channel Name"
                                   name="name"
                                   type="text"
                                   placeholder="Short Channel Name"
                                   disabled={disabled}
                                   value={channel.name}
                                   onChange={(e, {value}) => changeValue('name', value)}
                        />
                    </FormField>
                    <FormField width={8}>
                        <label>
                            Directory <RequiredAsterisk/>
                        </label>
                        <DirectorySearch
                            value={channel.directory}
                            onSelect={value => changeValue('directory', value)}
                            placeholder='videos/channel directory'
                        />
                    </FormField>
                </FormGroup>

                <FormGroup>
                    <FormField width={16}>
                        <FormInput
                            label="URL"
                            name="url"
                            type="url"
                            placeholder='https://example.com/channel/videos'
                            value={channel.url}
                            onChange={handleInputChange}
                        />
                    </FormField>
                </FormGroup>

                {channel.tag_name && !create && <SingleTag name={channel.tag_name}/>}

                <Message error
                         header={messageHeader}
                         content={messageContent}
                />
                <Message success
                         header={messageHeader}
                         content={messageContent}
                />

                <Grid stackable columns={2}>
                    <Grid.Row style={{marginTop: '1em'}}>
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
                                : <>
                                    <TagsSelector
                                        limit={1}
                                        selectedTagNames={channel.tag_name ? [channel.tag_name] : []}
                                        onAdd={i => changeValue('tag_name', i)}
                                        onRemove={() => changeValue('tag_name', null)}
                                    />
                                </>
                            }
                        </Grid.Column>
                        <Grid.Column>
                            <APIButton
                                color='violet'
                                size='big'
                                floated='right'
                                onClick={handleSubmit}
                                disabled={disabled}
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
                        afterSave={afterNewDownloadSave}
                        closeModal={() => setDownloadModalOpen(false)}
                    />
                </ModalContent>
            </Modal>

            <RecurringDownloadsTable downloads={downloads} fetchDownloads={fetchChannel}/>
        </Segment>}

        <div style={{marginTop: '2em'}}>
            {channel.statistics && <ChannelStatistics statistics={channel.statistics}/>}
        </div>
    </>
}

export function ChannelDownloadForm({channel_id, afterSave, closeModal, download}) {
    download = download || {};
    channel_id = download ? download.channel_id || channel_id : channel_id;
    const editing = download && !_.isEmpty(download);

    const settings = download.settings ? download.settings : {};
    const oldTagNames = download && download.settings && download.settings.tag_names ? download.settings.tag_names : [];
    const [state, setState] = React.useState({
        frequency: download.frequency ? download.frequency : 604800,
        title_exclude: settings.title_exclude ? settings.title_exclude : '',
        title_include: settings.title_include ? settings.title_include : '',
        url: download ? download.url : '',
    })
    const [disabled, setDisabled] = React.useState(useWROLMode());
    const [loading, setLoading] = React.useState(false);
    const [urlValid, setUrlValid] = React.useState(true);
    const [tagNames, setTagNames] = React.useState(oldTagNames);

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
            let response;
            if (editing) {
                response = await updateChannelDownload(
                    channel_id,
                    download.id,
                    state.url,
                    state.frequency,
                    state.title_include,
                    state.title_exclude,
                    tagNames,
                );
            } else {
                response = await createChannelDownload(
                    channel_id,
                    state.url,
                    state.frequency,
                    state.title_include,
                    state.title_exclude,
                    tagNames,
                );
            }
            if (!response.ok) {
                throw 'Creating download failed';
            }
            if (afterSave) {
                await afterSave();
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
                    <HelpHeader
                        headerSize='h4'
                        headerContent='Title Match Words'
                        popupContent='List of words, separated by commas, that Video titles must contain to be downloaded.'
                        popupPosition='bottom center'
                    />
                    <FormInput
                        name="title_include"
                        type="text"
                        disabled={disabled}
                        placeholder='Shelter,Solar Power'
                        value={state.title_include}
                        onChange={handleInputChange}
                    />
                </Grid.Column>
                <Grid.Column>
                    <HelpHeader
                        headerSize='h4'
                        headerContent='Title Exclusion Words'
                        popupContent='List of words, separated by commas, that may not appear in video titles to be downloaded.'
                        popupPosition='bottom center'
                    />
                    <FormInput
                        name="title_exclude"
                        type="text"
                        disabled={disabled}
                        placeholder='Giveaway,Prize'
                        value={state.title_exclude}
                        onChange={handleInputChange}
                    />
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={1}>
                <Grid.Column>
                    <TagsSelector selectedTagNames={tagNames} onChange={(i, j) => setTagNames(i)}/>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={1}>
                <Grid.Column textAlign='right'>
                    {editing && deleteDownloadButton}
                    <Button onClick={handleClose}>Cancel</Button>
                    <Button color='violet' disabled={!urlValid}>Save</Button>
                </Grid.Column>
            </Grid.Row>
        </Grid>
    </Form>
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
