import React from "react";
import {Button, Checkbox, Form, Grid, Header, Input, Loader} from "semantic-ui-react";
import {
    createChannel,
    deleteChannel,
    getChannel,
    getChannels,
    getConfig,
    getDirectories,
    updateChannel,
    validateRegex
} from "../api";
import _ from "lodash";
import Container from "semantic-ui-react/dist/commonjs/elements/Container";
import {APIForm, RequiredAsterisk, VIDEOS_API} from "./Common";
import {Link} from "react-router-dom";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import Confirm from "semantic-ui-react/dist/commonjs/addons/Confirm";
import Table from "semantic-ui-react/dist/commonjs/collections/Table";
import Popup from "semantic-ui-react/dist/commonjs/modules/Popup";
import {ChannelPlaceholder} from "./Placeholder";


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
            mediaDirectory: `${global_config.media_directory}/`,
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
                    name='directory'
                    list='directories'
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
            inputs: {
                name: '',
                directory: '',
                mkdir: false,
                url: '',
                match_regex: '',
                generate_posters: true,
                calculate_duration: true,
            },
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

            if (response !== null && response.status === 201) {
                let location = response.headers.get('Location');
                let channelResponse = await fetch(location);
                let data = await channelResponse.json();
                let channel = data['channel'];

                this.setState({
                    success: true,
                    message_header: 'Channel created',
                    message_content: <span>
                        Your channel was created.  View it <Link to={`/videos/channel/${channel.link}/edit`}>here</Link>
                    </span>,
                });

            } else if (response !== null) {
                // Some error occurred.
                let message = await response.json();
                if (message.code === 3) {
                    this.setError('Invalid channel', message.error)
                } else {
                    this.setError('Invalid channel', 'Unable to save channel.  See logs.')
                }
            }
        }
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
                                value={this.state.inputs.name}
                                onChange={this.handleInputChange}
                            />
                        </Form.Field>
                        <Form.Field width={8}>
                            <label>
                                Directory <RequiredAsterisk/>
                            </label>
                            <DirectoryInput
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
                                value={this.state.inputs.url}
                                onChange={this.handleInputChange}
                            />
                        </Form.Field>
                    </Form.Group>

                    <Header as="h4" style={{'marginTop': '3em'}}>
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
                            value={this.state.match_regex}
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

                    <Message error
                             header={this.state.message_header}
                             content={this.state.message_content}
                    />
                    <Message success
                             header={this.state.message_header}
                             content={this.state.message_content}
                    />

                    <Button
                        color="blue"
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

                    {!this.state.create && <>
                        <Button color='red' onClick={() => this.setState({deleteOpen: true})}>Delete</Button>
                        <Confirm
                            open={this.state.deleteOpen}
                            content='Are you sure you want to delete this channel?  No video files will be deleted.'
                            confirmButton='Delete'
                            onCancel={() => this.setState({deleteOpen: false})}
                            onConfirm={this.handleConfirm}
                        />
                    </>
                    }
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
        <ChannelPage header='New Channel' create/>
    )
}

function ChannelRow(props) {
    let editTo = `/videos/channel/${props.channel.link}/edit`;
    let videosTo = `/videos/channel/${props.channel.link}/video`;

    async function downloadVideos(e) {
        e.preventDefault();
        let url = `${VIDEOS_API}:download/${props.channel.link}`;
        await fetch(url, {method: 'POST'});
    }

    async function refreshVideos(e) {
        e.preventDefault();
        let url = `${VIDEOS_API}:refresh/${props.channel.link}`;
        await fetch(url, {method: 'POST'});
    }

    return (
        <Table.Row>
            <Table.Cell>
                <Link to={videosTo}>{props.channel.name}</Link>
            </Table.Cell>
            <Table.Cell>
                {props.channel.video_count}
            </Table.Cell>
            <Table.Cell textAlign='right'>
                <Popup
                    header="Download any missing videos"
                    on="hover"
                    trigger={<Button
                        primary
                        onClick={downloadVideos}
                        disabled={!!!props.channel.url}
                    >
                        Download Videos
                    </Button>}
                />
            </Table.Cell>
            <Table.Cell textAlign='right'>
                <Popup
                    header="Search for any local videos"
                    on="hover"
                    trigger={<Button primary inverted onClick={refreshVideos}>Refresh Files</Button>}
                />
            </Table.Cell>
            <Table.Cell textAlign='right'>
                <Link className="ui button secondary" to={editTo}>Edit</Link>
            </Table.Cell>
        </Table.Row>
    )
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
            <Grid columns={2}>
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
                    <Table.HeaderCell width={2} colSpan={3} textAlign='center'>Manage</Table.HeaderCell>
                </Table.Row>
            </Table.Header>
        );

        let body = null;
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
            body = <Table striped basic size='large'>
                {tableHeader}
                <Table.Body>
                    {this.state.results.map((channel) => <ChannelRow key={channel.link} channel={channel}/>)}
                </Table.Body>
            </Table>
        }

        return (
            <>
                {header}
                {body}
            </>
        )
    }
}
