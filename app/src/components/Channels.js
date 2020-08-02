import React from "react";
import {Button, Checkbox, Form, Grid, Header, Input, Loader, Placeholder} from "semantic-ui-react";
import {createChannel, deleteChannel, getChannel, getChannels, getConfig, updateChannel, validateRegex} from "../api";
import _ from "lodash";
import Container from "semantic-ui-react/dist/commonjs/elements/Container";
import {RequiredAsterisk, VIDEOS_API} from "./Common";
import {Link} from "react-router-dom";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import Confirm from "semantic-ui-react/dist/commonjs/addons/Confirm";
import Table from "semantic-ui-react/dist/commonjs/collections/Table";
import Popup from "semantic-ui-react/dist/commonjs/modules/Popup";


function FieldPlaceholder() {
    return (
        <Form.Field>
            <Placeholder style={{'marginBottom': '0.5em'}}>
                <Placeholder.Line length="short"/>
            </Placeholder>
            <input disabled/>
        </Form.Field>
    )
}


class ChannelPage extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            channel: {},
            media_directory: null,
            disabled: false,
            open: false,
            dirty: false,
            inputs: ['name', 'directory', 'url', 'match_regex', 'generate_thumbnails', 'calculate_duration'],
            validRegex: true,
            create: !!this.props.create,
            error: false,
            success: false,
            message_header: '',
            message_content: '',

            // The properties to edit/submit
            name: '',
            directory: '',
            url: '',
            match_regex: '',
            generate_thumbnails: null,
            calculate_duration: null,
            mkdir: null,

            // Error handling
            name_error: null,
            directory_error: null,
            url_error: null,
            match_regex_error: null,
        };

        this.generateThumbnails = React.createRef();
        this.calculateDuration = React.createRef();
        this.mkdir = React.createRef();
    }

    show = (e) => {
        e.preventDefault();
        this.setState({open: true});
    }

    handleConfirm = async () => {
        this.setState({open: false});
        let response = await deleteChannel(this.props.match.params.channel_link);
        if (response.status === 204) {
            this.props.history.push({
                pathname: '/videos/channel'
            });
        } else {
            this.setState({
                error: true,
                message_header: 'Failed to delete',
                message_content: 'Failed to delete this channel, check logs.'
            })
        }
    }

    isDirty = () => {
        for (let i = 0; i < this.state.inputs.length; i++) {
            let name = this.state.inputs[i];
            if (this.state.channel[name] !== this.state[name]) {
                return true;
            }
        }
        return false;
    }

    checkDirty = () => {
        this.setState({dirty: this.isDirty()})
    }

    async componentDidMount() {
        let global_config = await getConfig();
        let newState = {
            media_directory: `${global_config.media_directory}`
        };
        if (!this.state.create) {
            let channel_link = this.props.match.params.channel_link;
            let channel = await getChannel(channel_link);
            newState = {
                channel: channel,
                name: channel.name,
                directory: channel.directory,
                url: channel.url,
                match_regex: channel.match_regex,
                generate_thumbnails: channel.generate_thumbnails,
                calculate_duration: channel.calculate_duration,
                media_directory: newState.media_directory,
            };
        }
        this.setState(newState);
    }

    setLoading = () => {
        this.setState({
            name_error: null,
            directory_error: null,
            url_error: null,
            match_regex_error: null,
            loading: true,
            disabled: true,
            error: false,
            success: false,
            message_header: '',
            message_content: '',
        })
    }

    clearLoading = () => {
        this.setState({
            loading: false,
            disabled: false,
        })
    }

    handleInputChange = async (event, {name, value}) => {
        this.setState({[name]: value}, this.checkDirty);
    }

    handleCheckbox = async (checkbox) => {
        let checked = checkbox.current.state.checked;
        let name = checkbox.current.props.name;
        this.setState({[name]: !checked}, this.checkDirty);
    }

    checkRegex = async (event, {name, value}) => {
        event.persist();
        await this.handleInputChange(event, {name, value});
        let valid = await validateRegex(value);
        this.setState({validRegex: valid});
    }

    handleSubmit = async (e) => {
        e.preventDefault();
        let channel = {
            name: this.state.name,
            directory: this.state.directory,
            url: this.state.url,
            match_regex: this.state.match_regex,
            generate_thumbnails: this.state.generate_thumbnails,
            calculate_duration: this.state.calculate_duration,
            mkdir: this.state.mkdir,
        };
        let response = null;
        try {
            this.setLoading();

            if (this.state.create) {
                response = await createChannel(channel);
            } else {
                response = await updateChannel(this.state.channel.link, channel);
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
                let error = {
                    error: true,
                    message_header: 'Invalid channel',
                    message_content: message.error,
                };

                if (message.code === 3) {
                    error.message_header = 'Invalid directory';
                }

                this.setState(error);
            }
        }
    }

    render() {
        if (this.state.create || this.state.channel) {
            return (
                <Container>
                    <Header as="h1">{this.props.header}</Header>
                    <Form
                        id="editChannel"
                        onSubmit={this.handleSubmit}
                        error={this.state.error}
                        success={this.state.success}
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
                                    value={this.state.name}
                                    onChange={this.handleInputChange}
                                />
                            </Form.Field>
                            <Form.Field width={8}>
                                <label>
                                    Directory <RequiredAsterisk/>
                                </label>
                                <Input
                                    required
                                    name="directory"
                                    type="text"
                                    disabled={this.state.disabled}
                                    label={this.state.media_directory}
                                    placeholder='videos/channel/directory'
                                    value={this.state.directory}
                                    onChange={this.handleInputChange}
                                    error={{
                                        content: 'Please enter a valid directory',
                                        pointing: 'below',
                                    }}
                                />
                            </Form.Field>
                        </Form.Group>
                        {
                            this.state.create &&
                            <Form.Group>
                                <Form.Field width={8}/>
                                <Form.Field width={8}>
                                    <Form.Field>
                                        <Checkbox
                                            toggle
                                            label="Create this directory, if it doesn't exist."
                                            name="mkdir"
                                            disabled={this.state.disabled}
                                            checked={this.state.mkdir}
                                            ref={this.mkdir}
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
                                    value={this.state.url}
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
                                label="Generate thumbnails, if not found"
                                name="generate_thumbnails"
                                disabled={this.state.disabled}
                                checked={this.state.generate_thumbnails}
                                ref={this.generateThumbnails}
                                onClick={() => this.handleCheckbox(this.generateThumbnails)}
                            />
                        </Form.Field>
                        <Form.Field>
                            <Checkbox
                                toggle
                                label="Calculate video duration"
                                name="calculate_duration"
                                disabled={this.state.disabled}
                                checked={this.state.calculate_duration}
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

                        <Link to='/videos/channel'>
                            <Button
                                secondary
                                floated='right'
                            >
                                Cancel
                            </Button>
                        </Link>

                        {!this.state.create && <>
                            <Button color='red' onClick={this.show}>Delete</Button>
                            <Confirm
                                open={this.state.open}
                                content='Are you sure you want to delete this channel?  No video files will be deleted.'
                                confirmButton='Delete'
                                onCancel={() => this.setState({open: false})}
                                onConfirm={this.handleConfirm}
                            />
                        </>
                        }
                    </Form>
                </Container>
            )
        } else {
            // Channel not loaded yet
            return (
                <Container>
                    <Header as="h1">{this.props.header}</Header>
                    <Form>
                        <div className="two fields">
                            <FieldPlaceholder/>
                            <FieldPlaceholder/>
                        </div>
                        <FieldPlaceholder/>

                        <Header as="h4" style={{'marginTop': '3em'}}>
                            <Placeholder>
                                <Placeholder.Line length="very long"/>
                            </Placeholder>
                        </Header>
                        <FieldPlaceholder/>
                        <FieldPlaceholder/>
                    </Form>
                </Container>
            )
        }
    }
}

export function EditChannel(props) {
    return (
        <ChannelPage header="Edit Channel" {...props}/>
    )
}

export function NewChannel(props) {
    return (
        <ChannelPage header="Create New Channel" {...props} create/>
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
                Videos: {props.channel.video_count}
            </Table.Cell>
            <Table.Cell textAlign='right'>
                <Popup
                    header="Download any missing videos"
                    on="hover"
                    trigger={<Button primary onClick={downloadVideos}>Download Videos</Button>}
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

function ChannelPlaceholder() {
    return (
        <Placeholder>
            <Placeholder.Line length='long'/>
            <Placeholder.Line length='short'/>
        </Placeholder>
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

        let table_header = (
            <Table.Header>
                <Table.Row>
                    <Table.HeaderCell width={8}>Name</Table.HeaderCell>
                    <Table.HeaderCell width={2}>Details</Table.HeaderCell>
                    <Table.HeaderCell width={2}/>
                    <Table.HeaderCell width={2}/>
                    <Table.HeaderCell width={2}/>
                </Table.Row>
            </Table.Header>
        );

        if (this.state.channels === null) {
            // Placeholders while fetching
            return (
                <>
                    {header}

                    <Table celled>
                        {table_header}

                        <Table.Body>
                            <Table.Row>
                                <Table.Cell><ChannelPlaceholder/></Table.Cell>
                                <Table.Cell/>
                                <Table.Cell/>
                                <Table.Cell/>
                            </Table.Row>
                        </Table.Body>
                    </Table>
                </>
            )
        } else if (this.state.channels.length === 0) {
            return (
                <>
                    {header}
                    <Message>
                        <Message.Header>No channels exist yet!</Message.Header>
                        <Message.Content><Link to='/videos/channel/new'>Create one.</Link></Message.Content>
                    </Message>
                </>
            )
        } else {
            return (
                <>
                    {header}
                    <Table striped basic size='large'>
                        {table_header}
                        <Table.Body>
                            {this.state.results.map((channel) => <ChannelRow channel={channel}/>)}
                        </Table.Body>
                    </Table>
                </>
            )
        }
    }
}
