import React, {useState} from "react";
import {
    AccordionContent,
    AccordionTitle,
    Grid,
    Input,
    Responsive,
    StatisticLabel,
    StatisticValue,
    TableBody,
    TableCell,
    TableHeader,
    TableHeaderCell,
    TableRow,
} from "semantic-ui-react";
import {createChannel, deleteChannel, downloadChannel, refreshChannel, updateChannel, validateRegex} from "../api";
import Container from "semantic-ui-react/dist/commonjs/elements/Container";
import {
    frequencyOptions,
    humanFileSize, isEmpty,
    RequiredAsterisk,
    secondsToDate,
    secondsToFrequency,
    Toggle,
    useTitle,
    WROLModeMessage
} from "./Common";
import {Link, useNavigate, useParams} from "react-router-dom";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import Confirm from "semantic-ui-react/dist/commonjs/addons/Confirm";
import {ChannelPlaceholder} from "./Placeholder";
import Icon from "semantic-ui-react/dist/commonjs/elements/Icon";
import {useChannel, useChannels, useDirectories, useSettings} from "../hooks/customHooks";
import {toast} from "react-semantic-toasts";
import _ from "lodash";
import {
    Accordion,
    Button,
    Form,
    FormField,
    FormGroup,
    FormInput,
    Header,
    Loader,
    Segment,
    Statistic,
    Table
} from "./Theme";
import Dropdown from "semantic-ui-react/dist/commonjs/modules/Dropdown";


function DirectoryInput({disabled, error, placeholder, setInput, value, required}) {
    const {directory, directories, setDirectory} = useDirectories(value);
    const {settings} = useSettings();

    if (!directories || !settings) {
        return <></>;
    }

    const localSetInput = (e, {value}) => {
        setInput(value);
        setDirectory(value);
    }

    const {media_directory} = settings;

    return (
        <div>
            <Input
                required={required}
                disabled={disabled}
                name='directory'
                list='directories'
                error={error}
                label={media_directory}
                value={directory}
                onChange={localSetInput}
                placeholder={placeholder}
            />
            <datalist id='directories'>
                {directories.map(i => <option key={i} value={i}>{i}</option>)}
            </datalist>
        </div>
    );
}

function ChannelStatistics({statistics}) {
    if (!statistics) {
        return <></>
    }

    return (
        <>
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
        </>
    )
}


function ChannelPage({create, header}) {
    const [loading, setLoading] = useState(false);
    const [disabled, setDisabled] = useState(false);
    const [deleteOpen, setDeleteOpen] = useState(false);
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
        e.preventDefault();
        const body = {
            name: channel.name,
            directory: channel.directory,
            mkdir: channel.mkdir,
            url: channel.url,
            download_frequency: channel.download_frequency,
            match_regex: channel.match_regex,
        };
        let response = null;
        try {
            setLoading(true);

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
        } finally {
            setLoading(false);
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
                setSuccessMessage('Channel updated', 'Your channel was updated');
            }

        } else if (response) {
            // Some error occurred.
            let error = await response.json();
            let cause = error.cause;
            if (error.code === 3 || (cause && cause.code === 3)) {
                setErrorMessage(
                    'Invalid directory',
                    'This directory does not exist.',
                    'directory',
                );
            } else if (cause && cause.code === 7) {
                setErrorMessage(
                    'Invalid directory',
                    'This directory is already used by another channel',
                    'directory',
                );
            } else if (cause && cause.code === 5) {
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
        e.preventDefault();
        return await downloadChannel(channelId);
    }

    const handleRefreshChannel = async (e) => {
        e.preventDefault();
        return await refreshChannel(channelId);
    }

    const handleDeleteConfirm = async () => {
        setDeleteOpen(false);
        let response = await deleteChannel(channelId);
        if (response.status === 204) {
            navigate('/videos/channel');
        } else {
            setSuccessMessage('Failed to delete', 'Failed to delete this channel, check logs.');
        }
    }

    const handleDeleteButton = (e) => {
        e.preventDefault();
        setDeleteOpen(true);
    }

    const handleCancel = (e) => {
        e.preventDefault();
        navigate(-1);
    }

    return <Container fluid>
        <Header as="h1">{header}</Header>
        <WROLModeMessage content='Channel page is disabled while WROL Mode is enabled.'/>
        <Form
            id="editChannel"
            onSubmit={handleSubmit}
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
                    <Dropdown selection
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

            <Container>
                <Message error
                         header={messageHeader}
                         content={messageContent}
                />
                <Message success
                         header={messageHeader}
                         content={messageContent}
                />

                <Button
                    color="green"
                    type="submit"
                    floated='right'
                >
                    {disabled ? <Loader active inline/> : 'Save'}
                </Button>

                <Button
                    secondary
                    floated='right'
                    onClick={handleCancel}
                >
                    Cancel
                </Button>

                {!create &&
                    <>
                        <Button color='red' onClick={handleDeleteButton}>
                            Delete
                        </Button>
                        <Confirm
                            open={deleteOpen}
                            content='Are you sure you want to delete this channel?  No video files will be deleted.'
                            confirmButton='Delete'
                            onCancel={() => setDeleteOpen(false)}
                            onConfirm={handleDeleteConfirm}
                        />
                        <Button
                            color='violet'
                            onClick={handleDownloadChannel}
                            disabled={!channel.url || !channel.download_frequency}
                        >
                            Download
                        </Button>
                        <Button color='blue' onClick={handleRefreshChannel}>
                            Refresh
                        </Button>
                        <Button onClick={() => navigate(`/videos/channel/${channel.id}/video`)}>
                            Videos
                        </Button>
                    </>
                }
            </Container>
        </Form>
        {channel.statistics && <ChannelStatistics statistics={channel.statistics}/>}
    </Container>
}

export function EditChannel(props) {
    return <ChannelPage header="Edit Channel" {...props}/>;
}

export function NewChannel(props) {
    useTitle('New Channel');
    return <ChannelPage header='New Channel' {...props} create/>
}

function ChannelRow({channel}) {
    const navigate = useNavigate();

    const editTo = `/videos/channel/${channel.id}/edit`;
    const videosTo = `/videos/channel/${channel.id}/video`;

    return <TableRow>
        <TableCell>
            <Link to={videosTo}>{channel.name}</Link>
        </TableCell>
        <TableCell>
            {channel.video_count}
        </TableCell>
        <TableCell>
            {channel.url && channel.info_date ? secondsToDate(channel.info_date) : null}
        </TableCell>
        <TableCell>
            {channel.url && channel.download_frequency ? secondsToFrequency(channel.download_frequency) : null}
        </TableCell>
        <TableCell textAlign='right'>
            <Button secondary onClick={() => navigate(editTo)}>Edit</Button>
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


export function Channels() {
    useTitle('Channels');

    const {channels} = useChannels();
    const [searchStr, setSearchStr] = useState('');

    const handleInputChange = (e, {value}) => {
        e.preventDefault();
        setSearchStr(value);
    }

    let header = <Grid columns={2} style={{marginBottom: '1em'}}>
        <Grid.Column>
            <Header as='h1'>Channels</Header>
        </Grid.Column>
        <Grid.Column textAlign='right'>
            <Input
                icon='search'
                placeholder='Name filter...'
                size="large"
                name="filterStr"
                value={searchStr}
                onChange={handleInputChange}/>
        </Grid.Column>
        <Grid.Row>
            <Grid.Column/>
            <Grid.Column textAlign='right'>
                <Link to='/videos/channel/new'>
                    <Button secondary>New Channel</Button>
                </Link>
            </Grid.Column>
        </Grid.Row>;
    </Grid>;

    let tableHeader = <TableHeader>
        <TableRow>
            <TableHeaderCell width={8}>Name</TableHeaderCell>
            <TableHeaderCell width={2}>Videos</TableHeaderCell>
            <TableHeaderCell width={2}>Last Update</TableHeaderCell>
            <TableHeaderCell width={2}>Frequency</TableHeaderCell>
            <TableHeaderCell width={2} colSpan={3} textAlign='center'>Manage</TableHeaderCell>
        </TableRow>
    </TableHeader>;

    if (channels === null) {
        // Placeholders while fetching
        return <>
            {header}
            <Table compact striped basic size='large'>
                {tableHeader}
                <TableBody>
                    <TableRow>
                        <TableCell><ChannelPlaceholder/></TableCell>
                        <TableCell/>
                        <TableCell/>
                        <TableCell/>
                    </TableRow>
                </TableBody>
            </Table>
        </>
    } else if (isEmpty(channels)) {
        return <>
            {header}
            <Message>
                <Message.Header>No channels exist yet!</Message.Header>
                <Message.Content><Link to='/videos/channel/new'>Create one.</Link></Message.Content>
            </Message>
        </>
    }

    let filteredChannels = channels;
    if (searchStr) {
        const re = new RegExp(_.escapeRegExp(searchStr), 'i');
        filteredChannels = channels.filter(i => re.test(i['name']));
    }

    return <>
        {header}
        <Responsive minWidth={770}>
            <Table compact striped size='large'>
                {tableHeader}
                <TableBody>
                    {filteredChannels.map(channel => <ChannelRow key={channel.id} channel={channel}/>)}
                </TableBody>
            </Table>
        </Responsive>
        <Responsive maxWidth={769}>
            <Table striped unstackable size='small'>
                <TableBody>
                    {filteredChannels.map(channel => <MobileChannelRow key={channel.id} channel={channel}/>)}
                </TableBody>
            </Table>
        </Responsive>
    </>
}
