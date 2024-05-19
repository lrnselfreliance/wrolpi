import React, {useState} from "react";
import {
    AccordionContent,
    AccordionTitle,
    Grid,
    StatisticLabel,
    StatisticValue,
    TableCell,
    TableRow,
} from "semantic-ui-react";
import {createChannel, deleteChannel, downloadChannel, refreshChannel, updateChannel, validateRegex} from "../api";
import {
    APIButton,
    BackButton,
    DirectoryInput,
    ErrorMessage,
    frequencyOptions,
    humanFileSize,
    RequiredAsterisk,
    SearchInput,
    secondsToFrequency,
    secondsToFullDuration,
    Toggle,
    useTitle,
    WROLModeMessage
} from "./Common";
import {Link, useNavigate, useParams} from "react-router-dom";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import Icon from "semantic-ui-react/dist/commonjs/elements/Icon";
import {useChannel, useChannels, useOneQuery} from "../hooks/customHooks";
import _ from "lodash";
import {Accordion, Button, Form, FormField, FormGroup, FormInput, Header, Loader, Segment, Statistic} from "./Theme";
import Dropdown from "semantic-ui-react/dist/commonjs/modules/Dropdown";
import {Media, ThemeContext} from "../contexts/contexts";
import {SortableTable} from "./SortableTable";
import {toast} from "react-semantic-toasts-2";


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
    </Segment>
}


function ChannelPage({create, header}) {
    const [disabled, setDisabled] = useState(false);
    const [validRegex, setValidRegex] = useState(true);
    const [activeIndex, setActiveIndex] = useState(-1);
    const [errors, setErrors] = useState({});
    const [error, setError] = useState(false);
    const [success, setSuccess] = useState(false);
    const [messageHeader, setMessageHeader] = useState();
    const [messageContent, setMessageContent] = useState();

    const navigate = useNavigate();
    const {channelId} = useParams();
    const {channel, changeValue, fetchChannel} = useChannel(channelId);

    let title;
    if (channel && channel.name) {
        title = channel.name;
    }
    useTitle(title);

    if (!channel) {
        return <Loader active/>;
    }

    const checkRegex = async (e, {value}) => {
        changeValue('match_regex', value);
        const valid = await validateRegex(value);
        setValidRegex(valid);
    }

    const handleCheckbox = (e, {name, checked}) => {
        if (e) {
            e.preventDefault();
        }
        changeValue(name, checked);
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
            mkdir: channel.mkdir,
            url: channel.url,
            download_frequency: channel.download_frequency,
            match_regex: channel.match_regex,
        };

        setDisabled(true);

        let response = null;
        try {
            if (create !== undefined) {
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

        if (response && response.status >= 200 && response.status < 300) {
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
            if (error.code === 'UNKNOWN_DIRECTORY' || (cause && cause.code === 'UNKNOWN_DIRECTORY')) {
                setErrorMessage(
                    'Invalid directory',
                    'This directory does not exist.',
                    'directory',
                );
            } else if (cause && cause.code === 'CHANNEL_DIRECTORY_CONFLICT') {
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

    const handleAdvancedClick = (e, {index}) => {
        setActiveIndex(activeIndex === index ? -1 : index);
    }

    const handleDownloadChannel = async (e) => {
        if (e) {
            e.preventDefault();
        }
        try {
            const response = await downloadChannel(channelId);
            if (response.status === 204) {
                toast({
                    type: 'success',
                    title: 'Download Created',
                    description: 'Channel download has been started.',
                    time: 5000,
                });
            }
        } catch (e) {
            console.error(e);
        }
    }

    const handleRefreshChannel = async (e) => {
        if (e) {
            e.preventDefault();
        }
        const response = await refreshChannel(channelId);
        if (response.status !== 204) {
            toast({
                type: 'error',
                title: 'Failed to refresh',
                description: "Failed to refresh this channel's directory",
                time: 5000,
            })
        }
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
                onSubmit={handleSubmit}
            >
                <FormGroup>
                    <FormField width={8}>
                        <FormInput required
                                   label="Channel Name"
                                   name="name"
                                   type="text"
                                   placeholder="Short Channel Name"
                                   disabled={disabled}
                                   error={errors.name}
                                   value={channel.name}
                                   onChange={(e, {value}) => changeValue('name', value)}
                        />
                    </FormField>
                    <FormField width={8}>
                        <label>
                            Directory <RequiredAsterisk/>
                        </label>
                        <DirectoryInput required
                                        disabled={create === undefined}
                                        value={channel.directory}
                                        setInput={value => changeValue('directory', value)}
                                        placeholder='videos/channel directory'
                        />
                    </FormField>
                </FormGroup>
                {
                    create !== undefined &&
                    <FormGroup>
                        <FormField width={8}/>{/* Empty field*/}
                        <FormField width={8}>
                            <FormField>
                                <Toggle
                                    toggle
                                    label="Create this directory, if it doesn't exist."
                                    name="mkdir"
                                    disabled={disabled}
                                    error={errors.mkdir}
                                    checked={channel.mkdir}
                                    onChange={i => {
                                        handleCheckbox(null, {name: 'mkdir', checked: i})
                                    }}
                                />
                            </FormField>
                        </FormField>
                    </FormGroup>
                }
                <FormGroup>
                    <FormField width={16}>
                        <FormInput
                            label="URL"
                            name="url"
                            type="url"
                            disabled={disabled}
                            placeholder='https://example.com/channel/videos'
                            error={errors.url}
                            value={channel.url}
                            onChange={handleInputChange}
                        />
                    </FormField>
                </FormGroup>

                <FormGroup>
                    <FormField>
                        <label>Download Frequency</label>
                        <Dropdown selection clearable
                                  name='download_frequency'
                                  placeholder='Frequency'
                                  error={errors.download_frequency}
                                  value={channel.download_frequency}
                                  disabled={disabled || !channel.url}
                                  options={frequencyOptions}
                                  onChange={handleInputChange}
                        />
                    </FormField>
                </FormGroup>

                <Accordion style={{marginBottom: '1em'}}>
                    <AccordionTitle
                        onClick={handleAdvancedClick}
                        index={0}
                        active={activeIndex === 0}
                    >
                        <Icon name='dropdown'/>
                        Advanced Settings
                    </AccordionTitle>
                    <AccordionContent active={activeIndex === 0}>
                        <Segment secondary>
                            <Header as="h4">
                                The following settings are encouraged by default, modify them at your own risk.
                            </Header>
                            <FormField>
                                <FormInput
                                    label="Title Match Regex"
                                    name="match_regex"
                                    type="text"
                                    disabled={disabled}
                                    error={!validRegex}
                                    placeholder='.*([Nn]ame Matching).*'
                                    value={channel.match_regex}
                                    onChange={checkRegex}
                                />
                            </FormField>
                        </Segment>
                    </AccordionContent>
                </Accordion>

                <Message error
                         header={messageHeader}
                         content={messageContent}
                />
                <Message success
                         header={messageHeader}
                         content={messageContent}
                />

                <Grid stackable columns={2}>
                    <Grid.Row>
                        <Grid.Column>
                            {!create &&
                                <>
                                    <APIButton
                                        color='red'
                                        size='small'
                                        confirmContent='Are you sure you want to delete this channel?  No video files will be deleted.'
                                        confirmButton='Delete'
                                        onClick={handleDelete}
                                        obeyWROLMode={true}
                                    >Delete</APIButton>
                                    <APIButton
                                        color='green'
                                        size='small'
                                        onClick={handleDownloadChannel}
                                        obeyWROLMode={true}
                                    >Download</APIButton>
                                    <APIButton
                                        color='blue'
                                        size='small'
                                        onClick={handleRefreshChannel}
                                        obeyWROLMode={true}
                                    >Refresh</APIButton>
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

        <div style={{marginTop: '2em'}}>
            {channel.statistics && <ChannelStatistics statistics={channel.statistics}/>}
        </div>
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
    const videosTo = `/videos/channel/${channel.id}/video`;

    const {inverted} = React.useContext(ThemeContext);
    const editTo = `/videos/channel/${channel.id}/edit`;
    const buttonClass = `ui button secondary ${inverted}`;

    return <TableRow>
        <TableCell>
            <Link to={videosTo}>{channel.name}</Link>
        </TableCell>
        <TableCell>
            {channel.video_count}
        </TableCell>
        <TableCell>
            {channel.url && channel.download_frequency ? secondsToFrequency(channel.download_frequency) : null}
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
    const editTo = `/videos/channel/${channel.id}/edit`;
    const videosTo = `/videos/channel/${channel.id}/video`;
    return <TableRow verticalAlign='top'>
        <TableCell width={10} colSpan={2}>
            <Link as='h3' to={videosTo}>
                <h3>
                    {channel.name}
                </h3>
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
        {key: 'name', text: 'Name', sortBy: 'name', width: 8},
        {key: 'video_count', text: 'Videos', sortBy: 'video_count', width: 2},
        {key: 'download_frequency', text: 'Download Frequency', sortBy: 'download_frequency', width: 2},
        {key: 'size', text: 'Size', sortBy: 'size', width: 2},
        {key: 'manage', text: 'Manage', width: 2},
    ];
    const mobileHeaders = [
        {key: 'name', text: 'Name', sortBy: 'name'},
        {key: 'video_count', text: 'Videos', sortBy: 'video_count'},
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
