import React from 'react';
import {Link, Route} from "react-router-dom";
import '../static/external/fontawesome-free/css/all.min.css';
import Paginator, {DEFAULT_LIMIT, VideoCards, VIDEOS_API} from "./Common"
import Video from "./VideoPlayer";
import {getChannel, getChannels, getConfig, getVideo, searchVideos, updateChannel, validateRegex} from "../api";
import {Button, Card, Checkbox, Form, Grid, Header, Icon, Input, Loader, Placeholder, Popup} from "semantic-ui-react";
import * as QueryString from 'query-string';
import Container from "semantic-ui-react/dist/commonjs/elements/Container";
import _ from 'lodash';

// function scrollToTop() {
//     window.scrollTo({
//         top: 0,
//         behavior: "auto"
//     });
// }

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
            channel: null,
            media_directory: null,
            disabled: false,
            dirty: false,
            inputs: ['name', 'directory', 'url', 'match_regex', 'generate_thumbnails', 'calculate_duration'],
            validRegex: true,

            // The properties to edit/submit
            name: null,
            directory: null,
            url: null,
            match_regex: null,
            generate_thumbnails: null,
            calculate_duration: null
        };

        this.handleInputChange = this.handleInputChange.bind(this);
        this.handleSubmit = this.handleSubmit.bind(this);
        this.isDirty = this.isDirty.bind(this);
        this.checkDirty = this.checkDirty.bind(this);
        this.checkRegex = this.checkRegex.bind(this);

        this.generateThumbnails = React.createRef();
        this.calculateDuration = React.createRef();
    }

    isDirty() {
        for (let i = 0; i < this.state.inputs.length; i++) {
            let name = this.state.inputs[i];
            if (this.state.channel[name] !== this.state[name]) {
                return true;
            }
        }
        return false;
    }

    checkDirty() {
        this.setState({dirty: this.isDirty()})
    }

    async componentDidMount() {
        let channel_link = this.props.match.params.channel_link;
        let global_config = await getConfig();
        let channel = await getChannel(channel_link);
        this.setState({
            channel: channel,
            media_directory: `${global_config.media_directory}/`,
            name: channel.name,
            directory: channel.directory,
            url: channel.url,
            match_regex: channel.match_regex,
            generate_thumbnails: channel.generate_thumbnails,
            calculate_duration: channel.calculate_duration,
        });
    }

    async handleInputChange(event, {name, value}) {
        this.setState({[name]: value}, this.checkDirty);
    }

    async handleCheckbox(checkbox) {
        let checked = checkbox.current.state.checked;
        let name = checkbox.current.props.name;
        this.setState({[name]: !checked}, this.checkDirty);
    }

    async checkRegex(event, {name, value}) {
        event.persist();
        await this.handleInputChange(event, {name, value});
        let valid = await validateRegex(value);
        this.setState({validRegex: valid});
    }

    async handleSubmit(e) {
        e.preventDefault();
        let channel = {
            name: this.state.name,
            directory: this.state.directory,
            url: this.state.url,
            match_regex: this.state.match_regex,
            generate_thumbnails: this.state.generate_thumbnails,
            calculate_duration: this.state.calculate_duration,
        };
        try {
            this.setState({disabled: true});
            await updateChannel(this.state.channel.link, channel);
        } finally {
            this.setState({disabled: false});
        }
    }

    render() {
        if (this.state.channel) {
            return (
                <Container>
                    <Header as="h1">{this.props.header}</Header>
                    <Form id="editChannel" onSubmit={this.handleSubmit}>
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
                                    Directory
                                    <span style={{color: '#db2828'}}> *</span>
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
                                />
                            </Form.Field>
                        </Form.Group>
                        <Form.Field>
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

                        <Button
                            color="blue"
                            type="submit"
                            disabled={this.state.disabled || !this.state.dirty}
                        >
                            {this.state.disabled ? <Loader active inline/> : 'Save'}
                        </Button>
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

function EditChannel(props) {
    return (
        <ChannelPage header="Edit Channel" {...props}/>
    )
}

class ManageVideos extends React.Component {

    download = async (e) => {
        e.preventDefault();
        await fetch(`${VIDEOS_API}:download`, {method: 'POST'});
    }

    refresh = async (e) => {
        e.preventDefault();
        await fetch(`${VIDEOS_API}:refresh`, {method: 'POST'});
    }

    render() {
        return (
            <Container>
                <Header as="h1">Manage Videos</Header>

                <p>
                    <Button primary onClick={this.download}>Download Videos</Button>
                    <label>Download any missing videos</label>
                </p>

                <p>
                    <Button secondary onClick={this.refresh}>Refresh Video Files</Button>
                    <label>Search for any videos in the media directory</label>
                </p>
            </Container>
        )
    }
}

function VideoWrapper(props) {

    return (
        <Video video={props.video} prev={props.prev} next={props.next} autoplay={false}/>
    )
}

function ChannelCard(props) {
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
        <Card fluid={true}>
            <Card.Content>
                <Card.Header>
                    <Link to={videosTo}>
                        {props.channel.name}
                    </Link>
                </Card.Header>
                <Card.Description>
                    Videos: {props.channel.video_count}
                </Card.Description>
            </Card.Content>
            <Card.Content extra>
                <div className="ui buttons four">
                    <Popup
                        header="Download any missing videos"
                        on="hover"
                        trigger={<Button primary onClick={downloadVideos}>Download Videos</Button>}
                    />
                    <Popup
                        header="Search for any local videos"
                        on="hover"
                        trigger={<Button secondary onClick={refreshVideos}>Refresh Files</Button>}
                    />
                    <Link className="ui button primary inverted" to={editTo}>Edit</Link>
                </div>
            </Card.Content>
        </Card>
    )
}

function VideoPlaceholder() {
    return (
        <Card.Group doubling stackable>
            <Card>
                <Placeholder>
                    <Placeholder.Image rectangular/>
                </Placeholder>
                <Card.Content>
                    <Placeholder>
                        <Placeholder.Line/>
                        <Placeholder.Line/>
                        <Placeholder.Line/>
                    </Placeholder>
                </Card.Content>
            </Card>
        </Card.Group>
    )
}

function ChannelPlaceholder() {
    return (
        <Placeholder>
            <Placeholder.Header image>
                <Placeholder.Line/>
                <Placeholder.Line/>
            </Placeholder.Header>
            <Placeholder.Paragraph>
                <Placeholder.Line length='short'/>
            </Placeholder.Paragraph>
        </Placeholder>
    )
}

function ChannelsHeader() {

    return (
        <Header as='h1'>Channels</Header>
    )
}

class Channels extends React.Component {

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
                    <ChannelsHeader/>
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
            </Grid>
        );

        if (this.state.channels === null) {
            // Placeholders while fetching
            return (
                <>
                    {header}
                    <Grid columns={2} doubling>
                        {[1, 1, 1, 1, 1, 1].map(() => {
                            return (
                                <Grid.Column>
                                    <ChannelPlaceholder/>
                                </Grid.Column>
                            )
                        })}
                    </Grid>
                </>
            )
        } else if (this.state.channels === []) {
            return (
                <>
                    {header}
                    Not channels exist yet!
                    <Button secondary>Create Channel</Button>
                </>
            )
        } else {
            return (
                <>
                    {header}
                    <Grid columns={2} doubling>
                        {this.state.results.map((channel) => {
                            return (
                                <Grid.Column>
                                    <ChannelCard channel={channel}/>
                                </Grid.Column>
                            )
                        })}
                    </Grid>
                </>
            )
        }
    }
}

function changePageHistory(history, location, activePage, searchStr) {
    let search = `?page=${activePage}`;
    if (searchStr) {
        search = `${search}&q=${searchStr}`;
    }
    history.push({
        pathname: location.pathname,
        search: search,
    });
}

class Videos extends React.Component {

    constructor(props) {
        super(props);
        const query = QueryString.parse(this.props.location.search);
        let activePage = query.page ? parseInt(query.page) : 1; // First page is 1 by default, of course.
        let searchStr = query.q || null;

        this.state = {
            channel: null,
            videos: null,
            video: null,
            searchStr: searchStr,
            show: false,
            limit: DEFAULT_LIMIT,
            activePage: activePage,
            total: null,
            totalPages: null,
            prev: null,
            next: null,
        };
    }

    async componentDidMount() {
        if (this.props.match.params.video_id) {
            await this.fetchVideo();
        } else if (this.props.match.params.channel_link) {
            await this.fetchChannel();
        } else {
            await this.fetchVideos();
        }
    }

    async componentDidUpdate(prevProps, prevState, snapshot) {
        let params = this.props.match.params;

        let channelChanged = params.channel_link !== prevProps.match.params.channel_link;
        let videoChanged = params.video_id !== prevProps.match.params.video_id;
        let pageChanged = prevState.activePage !== this.state.activePage;

        if (channelChanged) {
            await this.fetchChannel();
        } else if (videoChanged) {
            await this.fetchVideo();
        } else if (pageChanged) {
            changePageHistory(this.props.history, this.props.location, this.state.activePage, this.state.searchStr);
            await this.fetchVideos();
        }
    }

    async fetchChannel() {
        // Get and display the channel specified in the Router match
        let channel_link = this.props.match.params.channel_link;
        let channel = null;
        if (channel_link) {
            channel = await getChannel(channel_link);
        }
        this.setState({
                channel,
                offset: 0,
                total: null,
                videos: null,
                video: null,
            },
            this.fetchVideos);
    }

    async fetchVideos() {
        let offset = this.state.limit * this.state.activePage - this.state.limit;
        let channel_link = this.state.channel ? this.state.channel.link : null;
        let favorites = this.props.filter === 'favorites';
        let order_by = this.state.searchStr ? 'rank' : '-upload_date';
        let [videos, total] = await searchVideos(
            offset, this.state.limit, channel_link, this.state.searchStr, favorites, order_by);

        let totalPages = Math.round(total / this.state.limit) + 1;
        this.setState({videos, total, totalPages});
    }

    async fetchVideo() {
        // Get and display the Video specified in the Router match
        let video_id = this.props.match.params.video_id;
        if (video_id) {
            let [video, prev, next] = await getVideo(video_id);
            this.setState({video, prev, next});
        }
    }

    changePage = async (activePage) => {
        this.setState({activePage});
    }

    handleSearch = async (e) => {
        e.preventDefault();
        await this.fetchVideos();
        changePageHistory(this.props.history, this.props.location, this.state.activePage, this.state.searchStr);
    }

    handleInputChange = (event, {name, value}) => {
        this.setState({[name]: value});
    }

    render() {
        let video = this.state.video;
        let videos = this.state.videos;
        let prev = this.state.prev;
        let next = this.state.next;
        let body = <VideoPlaceholder/>;
        let pagination = null;

        if (video) {
            body = <VideoWrapper video={video} prev={prev} next={next} channel={video.channel}/>
        } else if (videos && videos.length === 0 && this.props.filter !== 'favorites') {
            body = <p>No videos retrieved. Have you downloaded videos yet?</p>;
        } else if (videos && videos.length === 0 && this.props.filter === 'favorites') {
            body = <p>You haven't tagged any videos as favorite.</p>;
        } else if (videos) {
            body = <VideoCards videos={videos}/>;
        }

        let channelName = this.props.title;
        if (!this.props.title && this.state.channel) {
            // No title specified, but a channel is selected, use it's name for the title.
            channelName = this.state.channel.name;
        }

        if (this.state.totalPages) {
            pagination = (
                <div style={{'marginTop': '3em', 'textAlign': 'center'}}>
                    <Paginator
                        activePage={this.state.activePage}
                        changePage={this.changePage}
                        totalPages={this.state.totalPages}
                    />
                </div>
            );
        }

        return (
            <Container textAlign='center' fluid>
                <Grid columns={2}>
                    <Grid.Column>
                        <Header as='h1'>
                            {channelName}
                            {
                                this.state.channel &&
                                <>
                                    &nbsp;
                                    &nbsp;
                                    <Link to={`/videos/channel/${this.state.channel.link}/edit`}>
                                        <Icon name="edit"/>
                                    </Link>
                                </>
                            }
                        </Header>
                    </Grid.Column>
                    <Grid.Column textAlign='right'>
                        <Form onSubmit={this.handleSearch}>
                            <Input
                                icon='search'
                                placeholder='Search...'
                                size="large"
                                name="searchStr"
                                value={this.state.searchStr}
                                onChange={this.handleInputChange}/>
                        </Form>
                    </Grid.Column>
                </Grid>
                <Container textAlign='center'>
                    {body}
                </Container>
                {pagination}
            </Container>
        )
    }
}

class VideosRoute extends React.Component {

    render() {
        return (
            <Container fluid={true} style={{margin: '2em', padding: '0.5em'}}>
                <Route path='/videos' exact
                       component={(i) =>
                           <Videos
                               title="Newest Videos"
                               match={i.match}
                               history={i.history}
                               location={i.location}
                           />}
                />
                <Route path='/videos/favorites' exact
                       component={(i) =>
                           <Videos
                               title="Favorite Videos"
                               match={i.match}
                               history={i.history}
                               location={i.location}
                               filter='favorites'
                           />
                       }/>
                <Route path='/videos/channel' exact component={Channels}/>
                <Route path='/videos/manage' exact component={ManageVideos}/>
                <Route path='/videos/channel/:channel_link/edit' exact component={EditChannel}/>
                <Route path='/videos/channel/:channel_link/video' exact component={Videos}/>
                <Route path='/videos/channel/:channel_link/video/:video_id' exact component={Videos}/>
            </Container>
        )
    }
}

export default VideosRoute;
