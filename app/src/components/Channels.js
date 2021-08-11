import React from "react";
import {Accordion, Button, Checkbox, Form, Grid, Header, Input, Loader, Responsive, Segment} from "semantic-ui-react";
import {
    createChannel,
    deleteChannel,
    downloadChannel,
    getChannel,
    getChannels,
    getConfig,
    getDirectories,
    refreshChannel,
    updateChannel,
    validateRegex
} from "../api";
import _ from "lodash";
import Container from "semantic-ui-react/dist/commonjs/elements/Container";
import {APIForm, frequencyOptions, RequiredAsterisk, secondsToFrequency} from "./Common";
import {Link} from "react-router-dom";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import Confirm from "semantic-ui-react/dist/commonjs/addons/Confirm";
import Table from "semantic-ui-react/dist/commonjs/collections/Table";
import {ChannelPlaceholder} from "./Placeholder";
import Dropdown from "semantic-ui-react/dist/commonjs/modules/Dropdown";
import Icon from "semantic-ui-react/dist/commonjs/elements/Icon";


class DirectoryInput extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            directories: [],
            mediaDirectory: null,
            directory: '',
        }

        this.handleChange = this.handleChange.bind(this);
    }

    async componentDidMount() {
        let global_config = await getConfig();
        let directories = await getDirectories(this.state.directory);
        this.setState({
            directories,
            mediaDirectory: global_config.media_directory,
            directory: this.props.value,
        });
    }

    async componentDidUpdate(prevProps, prevState, snapshot) {
        if (prevState.directory !== this.state.directory) {
            let directories = await getDirectories(this.state.directory);
            this.setState({directories});
        }
    }

    async handleChange(e, {name, value}) {
        e.preventDefault();
        this.setState({[name]: value}, () => this.props.setInput(e, {name, value}));
    }

    render() {
        let {directories, mediaDirectory, directory} = this.state;

        return (
            <div>
                <Input
                    disabled={this.props.disabled}
                    name='directory'
                    list='directories'
                    error={this.props.error}
                    label={mediaDirectory}
                    value={directory}
                    onChange={this.handleChange}
                    placeholder='videos/channel directory'
                />
                <datalist id='directories'>
                    {directories.map((i) => <option key={i} value={i}>{i}</option>)}
                </datalist>
            </div>
        );
    }
}


class ChannelPage extends APIForm {

    constructor(props) {
        super(props);

        this.state = {
            ...this.state,
            deleteOpen: false,
            validRegex: true,
            original: {},
            activeIndex: -1,
            inputs: {
                name: '',
                directory: '',
                mkdir: false,
                url: '',
                match_regex: '',
                generate_posters: true,
                calculate_duration: true,
                download_frequency: 604800,
            },
            errors: {},
        };

        this.calculateDuration = React.createRef();
        this.generatePosters = React.createRef();
        this.mkdir = React.createRef();
    }

    async componentDidMount() {
        if (!this.props.create) {
            let channel_link = this.props.match.params.channel_link;
            let channel = await getChannel(channel_link);
            this.initFormValues(channel);
        }
    }

    checkRegex = async (event, {name, value}) => {
        event.persist();
        await this.handleInputChange(event, {name, value});
        let valid = await validateRegex(value);
        this.setState({validRegex: valid});
    }

    handleConfirm = async () => {
        this.setState({deleteOpen: false});
        let response = await deleteChannel(this.props.match.params.channel_link);
        if (response.status === 204) {
            this.props.history.push({
                pathname: '/videos/channel'
            });
        } else {
            this.setError('Failed to delete', 'Failed to delete this channel, check logs.');
        }
    }

    handleSubmit = async (e) => {
        e.preventDefault();
        let {inputs} = this.state;
        let response = null;
        try {
            this.setLoading();

            if (this.props.create) {
                response = await createChannel(inputs);
            } else {
                response = await updateChannel(this.props.match.params.channel_link, inputs);
            }

        } finally {
            this.clearLoading();
        }

        if (response === null) {
            throw Error('Response was null');
        }

        if (response.status >= 200 && response.status < 300) {
            let location = response.headers.get('Location');
            let channelResponse = await fetch(location);
            let data = await channelResponse.json();
            let channel = data['channel'];

            if (response.status === 201) {
                this.setSuccess(
                    'Channel created',
                    <span>
                        Your channel was created.  View it <Link to={`/videos/channel/${channel.link}/edit`}>here</Link>
                    </span>
                );
            } else {
                this.initFormValues(channel);
                this.setSuccess('Channel updated', 'Your channel was updated');
                this.checkDirty();
            }

        } else {
            // Some error occurred.
            let error = await response.json();
            let cause = error.cause;
            if (error.code === 3 || (cause && cause.code === 3)) {
                this.setError(
                    'Invalid directory',
                    'This directory does not exist.',
                    'directory',
                );
            } else if (cause && cause.code === 7) {
                this.setError(
                    'Invalid directory',
                    'This directory is already used by another channel',
                    'directory',
                );
            } else if (cause && cause.code === 5) {
                this.setError(
                    'Invalid name',
                    'This channel name is already taken',
                    'name',
                );
            } else {
                this.setError('Invalid channel', 'Unable to save channel.  See logs.');
            }
        }
    }

    handleAdvancedClick = (e, titleProps) => {
        const {index} = titleProps
        const {activeIndex} = this.state
        const newIndex = activeIndex === index ? -1 : index

        this.setState({activeIndex: newIndex})
    }

    downloadChannel = async (e) => {
        e.preventDefault();
        return await downloadChannel(this.props.match.params.channel_link);
    }

    refreshChannel = async (e) => {
        e.preventDefault();
        return await refreshChannel(this.props.match.params.channel_link);
    }

    handleDeleteButton = (e) => {
        e.preventDefault();
        this.setState({deleteOpen: true});
    }

    render() {
        return (
            <Container>
                <Header as="h1">{this.props.header}</Header>
                <Form
                    id="editChannel"
                    onSubmit={this.handleSubmit}
                    error={this.state.error}
                    success={this.state.success}
                    autoComplete="off"
                >

                    <Form.Group>
                        <Form.Field width={8}>
                            <Form.Input
                                required
                                label="Channel Name"
                                name="name"
                                type="text"
                                placeholder="Short Channel Name"
                                disabled={this.state.disabled}
                                error={this.state.errors.name}
                                value={this.state.inputs.name}
                                onChange={this.handleInputChange}
                            />
                        </Form.Field>
                        <Form.Field width={8}>
                            <label>
                                Directory <RequiredAsterisk/>
                            </label>
                            <DirectoryInput
                                disabled={!this.props.create}
                                value={this.state.inputs.directory}
                                setInput={this.handleInputChange}
                            />
                        </Form.Field>
                    </Form.Group>
                    {
                        this.props.create &&
                        <Form.Group>
                            <Form.Field width={8}/>
                            <Form.Field width={8}>
                                <Form.Field>
                                    <Checkbox
                                        toggle
                                        label="Create this directory, if it doesn't exist."
                                        name="mkdir"
                                        ref={this.mkdir}
                                        disabled={this.state.disabled}
                                        error={this.state.errors.mkdir}
                                        checked={this.state.inputs.mkdir}
                                        onClick={() => this.handleCheckbox(this.mkdir)}
                                    />
                                </Form.Field>
                            </Form.Field>
                        </Form.Group>
                    }
                    <Form.Group>
                        <Form.Field width={16}>
                            <Form.Input
                                label="URL"
                                name="url"
                                type="url"
                                disabled={this.state.disabled}
                                placeholder='https://example.com/channel/videos'
                                error={this.state.errors.url}
                                value={this.state.inputs.url}
                                onChange={this.handleInputChange}
                            />
                        </Form.Field>
                    </Form.Group>

                    <Form.Group>
                        <Form.Field>
                            <label>Download Frequency</label>
                            <Dropdown selection
                                      name='download_frequency'
                                      disabled={this.state.disabled}
                                      placeholder='Frequency'
                                      error={this.state.errors.download_frequency}
                                      value={this.state.inputs.download_frequency}
                                      options={frequencyOptions}
                                      onChange={this.handleInputChange}
                            />
                        </Form.Field>
                    </Form.Group>

                    <Accordion>
                        <Accordion.Title
                            onClick={this.handleAdvancedClick}
                            index={0}
                            active={this.state.activeIndex === 0}
                        >
                            <Icon name='dropdown'/>
                            Advanced Settings
                        </Accordion.Title>
                        <Accordion.Content
                            active={this.state.activeIndex === 0}
                        >
                            <Segment secondary>
                                <Header as="h4">
                                    The following settings are encouraged by default, modify them at your own risk.
                                </Header>
                                <Form.Field>
                                    <Form.Input
                                        label="Title Match Regex"
                                        name="match_regex"
                                        type="text"
                                        disabled={this.state.disabled}
                                        error={!this.state.validRegex}
                                        placeholder='.*([Nn]ame Matching).*'
                                        value={this.state.inputs.match_regex}
                                        onChange={this.checkRegex}
                                    />
                                </Form.Field>

                                <Form.Field>
                                    <Checkbox
                                        toggle
                                        label="Generate posters, if not found"
                                        name="generate_posters"
                                        disabled={this.state.disabled}
                                        checked={this.state.inputs.generate_posters}
                                        ref={this.generatePosters}
                                        onClick={() => this.handleCheckbox(this.generatePosters)}
                                    />
                                </Form.Field>
                                <Form.Field>
                                    <Checkbox
                                        toggle
                                        label="Calculate video duration"
                                        name="calculate_duration"
                                        disabled={this.state.disabled}
                                        checked={this.state.inputs.calculate_duration}
                                        ref={this.calculateDuration}
                                        onClick={() => this.handleCheckbox(this.calculateDuration)}
                                    />
                                </Form.Field>
                            </Segment>
                        </Accordion.Content>
                    </Accordion>

                    <Container style={{marginTop: '2em'}}>
                        <Message error
                                 header={this.state.message_header}
                                 content={this.state.message_content}
                        />
                        <Message success
                                 header={this.state.message_header}
                                 content={this.state.message_content}
                        />

                        <Button
                            color="green"
                            type="submit"
                            disabled={this.state.disabled || !this.state.dirty}
                            floated='right'
                        >
                            {this.state.disabled ? <Loader active inline/> : 'Save'}
                        </Button>

                        <Button
                            secondary
                            floated='right'
                            onClick={() => this.props.history.goBack()}
                        >
                            Cancel
                        </Button>

                        {!this.props.create &&
                        <>
                            <Button color='red' onClick={this.handleDeleteButton}>
                                Delete
                            </Button>
                            <Confirm
                                open={this.state.deleteOpen}
                                content='Are you sure you want to delete this channel?  No video files will be deleted.'
                                confirmButton='Delete'
                                onCancel={() => this.setState({deleteOpen: false})}
                                onConfirm={this.handleConfirm}
                            />
                            <Button color='blue' onClick={this.downloadChannel}>
                                Download
                            </Button>
                            <Button color='inverted blue' onClick={this.refreshChannel}>
                                Refresh
                            </Button>
                        </>
                        }
                    </Container>
                </Form>
            </Container>
        )
    }
}

export function EditChannel(props) {
    return (
        <ChannelPage header="Edit Channel" {...props}/>
    )
}

export function NewChannel(props) {
    return (
        <ChannelPage header='New Channel' {...props} create/>
    )
}

class ChannelRow extends React.Component {
    constructor(props) {
        super(props);
        this.editTo = `/videos/channel/${props.channel.link}/edit`;
        this.videosTo = `/videos/channel/${props.channel.link}/video`;
    }

    render() {
        return (
            <Table.Row>
                <Table.Cell>
                    <Link to={this.videosTo}>{this.props.channel.name}</Link>
                </Table.Cell>
                <Table.Cell>
                    {this.props.channel.video_count}
                </Table.Cell>
                <Table.Cell>
                    {secondsToFrequency(this.props.channel.download_frequency)}
                </Table.Cell>
                <Table.Cell textAlign='right'>
                    <Link className="ui button secondary" to={this.editTo}>Edit</Link>
                </Table.Cell>
            </Table.Row>
        )
    }
}

class MobileChannelRow extends ChannelRow {

    render() {
        return <Table.Row verticalAlign='top'>
            <Table.Cell width={10} colSpan={2}>
                <p>
                    <Link as='h3' to={this.videosTo}>
                        <h3>
                            {this.props.channel.name}
                        </h3>
                    </Link>
                </p>
                <p>
                    Videos: {this.props.channel.video_count}
                </p>
                <p>
                    Frequency: {secondsToFrequency(this.props.channel.download_frequency)}
                </p>
            </Table.Cell>
            <Table.Cell width={6} colSpan={2} textAlign='right'>
                <p>
                    <Link className="ui button secondary" to={this.editTo}>Edit</Link>
                </p>
            </Table.Cell>
        </Table.Row>;
    }
}

function NewChannelButton() {
    return (
        <Grid.Row>
            <Grid.Column/>
            <Grid.Column textAlign='right'>
                <Link to='/videos/channel/new'>
                    <Button secondary>New Channel</Button>
                </Link>
            </Grid.Column>
        </Grid.Row>
    );
}

export class Channels extends React.Component {

    initialState = {
        channels: null,
        value: '',
        results: [],
    };

    constructor(props) {
        super(props);
        this.state = this.initialState;
    }

    async componentDidMount() {
        let channels = await getChannels();
        this.setState({channels, results: channels});
    }

    handleSearchChange = async (e, {value}) => {
        this.setState({value});

        setTimeout(() => {
            if (this.state.value.length < 1) {
                return this.setState({value, results: this.state.channels});
            }

            const re = new RegExp(_.escapeRegExp(this.state.value), 'i');
            const isMatch = (result) => re.test(result.name);

            this.setState({
                results: _.filter(this.state.channels, isMatch),
            });
        }, 300);
    };

    render() {
        let header = (
            <Grid columns={2} style={{marginBottom: '1em'}}>
                <Grid.Column>
                    <Header as='h1'>Channels</Header>
                </Grid.Column>
                <Grid.Column textAlign='right'>
                    <Form onSubmit={this.handleSearch}>
                        <Input
                            icon='search'
                            placeholder='Name filter...'
                            size="large"
                            name="filterStr"
                            value={this.state.value}
                            onChange={this.handleSearchChange}/>
                    </Form>
                </Grid.Column>
                <NewChannelButton/>
            </Grid>
        );

        let tableHeader = (
            <Table.Header>
                <Table.Row>
                    <Table.HeaderCell width={8}>Name</Table.HeaderCell>
                    <Table.HeaderCell width={2}>Videos</Table.HeaderCell>
                    <Table.HeaderCell width={2}>Frequency</Table.HeaderCell>
                    <Table.HeaderCell width={2} colSpan={3} textAlign='center'>Manage</Table.HeaderCell>
                </Table.Row>
            </Table.Header>
        );

        let body;
        if (this.state.channels === null) {
            // Placeholders while fetching
            body = <Table striped basic size='large'>
                {tableHeader}
                <Table.Body>
                    <Table.Row>
                        <Table.Cell><ChannelPlaceholder/></Table.Cell>
                        <Table.Cell/>
                        <Table.Cell/>
                        <Table.Cell/>
                    </Table.Row>
                </Table.Body>
            </Table>
        } else if (this.state.channels.length === 0) {
            body = <Message>
                <Message.Header>No channels exist yet!</Message.Header>
                <Message.Content><Link to='/videos/channel/new'>Create one.</Link></Message.Content>
            </Message>
        } else {
            body = (
                <>
                    <Responsive minWidth={770}>
                        <Table striped basic size='large'>
                            {tableHeader}
                            <Table.Body>
                                {this.state.results.map((channel) => <ChannelRow key={channel.link}
                                                                                 channel={channel}/>)}
                            </Table.Body>
                        </Table>
                    </Responsive>
                    <Responsive maxWidth={769}>
                        <Table striped basic unstackable size='medium'>
                            <Table.Body>
                                {this.state.results.map((channel) =>
                                    <MobileChannelRow key={channel.link} channel={channel}/>)}
                            </Table.Body>
                        </Table>
                    </Responsive>
                </>
            )
        }

        return (
            <>
                {header}
                {body}
            </>
        )
    }
}
