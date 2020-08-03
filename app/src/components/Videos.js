import React from 'react';
import {Link, Route} from "react-router-dom";
import '../static/external/fontawesome-free/css/all.min.css';
import Paginator, {DEFAULT_LIMIT, searchOrders, VideoCards, videoOrders, VIDEOS_API} from "./Common"
import Video from "./VideoPlayer";
import {getChannel, getVideo, searchVideos} from "../api";
import {Button, Card, Dropdown, Form, Grid, Header, Icon, Input, Placeholder} from "semantic-ui-react";
import * as QueryString from 'query-string';
import Container from "semantic-ui-react/dist/commonjs/elements/Container";
import {Channels, EditChannel, NewChannel} from "./Channels";

function scrollToTop() {
    window.scrollTo({
        top: 0,
        behavior: "auto"
    });
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

function changePageHistory(history, location, activePage, searchStr, searchOrder) {
    let search = `?page=${activePage}`;
    if (searchStr) {
        search = `${search}&q=${searchStr}`;
    }
    if (searchOrder) {
        search = `${search}&o=${searchOrder}`;
    }
    history.push({
        pathname: location.pathname,
        search: search,
    });
    scrollToTop();
}

export class NewestVideosPreview extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            videos: null,
        };
    }

    async componentDidMount() {
        await this.fetchVideos();
    }

    async fetchVideos() {
        let [videos, _] = await searchVideos(0, 4);
        this.setState({videos});
    }

    render() {
        let header = <h2>Newest Videos</h2>;
        let body = <VideoPlaceholder/>
        if (this.state.videos && this.state.videos.length === 0) {
            body = <p>No videos available.</p>
        } else if (this.state.videos && this.state.videos.length > 0) {
            body = <VideoCards videos={this.state.videos}/>
        }
        return <>
            {header}
            {body}
        </>
    }

}

export class ViewedVideosPreview extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            videos: null,
        };
    }

    async componentDidMount() {
        await this.fetchVideos();
    }

    async fetchVideos() {
        let [videos, _] = await searchVideos(
            0, 4, null, null, null, 'viewed');
        this.setState({videos});
    }

    render() {
        let header = <h2>Recently Viewed Videos</h2>;
        let body = <VideoPlaceholder/>
        if (this.state.videos && this.state.videos.length === 0) {
            body = <p>No videos available.</p>
        } else if (this.state.videos && this.state.videos.length > 0) {
            body = <VideoCards videos={this.state.videos}/>
        }
        return <>
            {header}
            {body}
        </>
    }

}


class Videos extends React.Component {

    constructor(props) {
        super(props);
        const query = QueryString.parse(this.props.location.search);
        let activePage = query.page ? parseInt(query.page) : 1; // First page is 1 by default, of course.
        let searchStr = query.q || '';
        let searchOrder = query.o || '-upload_date';

        this.state = {
            channel: null,
            videos: null,
            video: null,
            queryStr: searchStr,
            searchStr: searchStr,
            show: false,
            limit: DEFAULT_LIMIT,
            activePage: activePage,
            total: null,
            totalPages: null,
            prev: null,
            next: null,
            videoOrders: searchStr ? searchOrders : videoOrders,
            searchOrder: searchOrder,
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
            this.applyStateToHistory();
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
        let favorites = this.props.filter !== undefined ? this.props.filter === 'favorites' : null;
        let [videos, total] = await searchVideos(
            offset, this.state.limit, channel_link, this.state.searchStr, favorites, this.state.searchOrder);

        let totalPages = Math.round(total / this.state.limit) || 1;
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

    clearSearch = async () => {
        this.setState({searchStr: '', searchOrder: 'upload_date'}, this.handleSearch);
    }

    applyStateToHistory = () => {
        let {history, location} = this.props;
        let {activePage, searchStr, searchOrder} = this.state;
        changePageHistory(history, location, activePage, searchStr, searchOrder);
    }

    handleSearch = async (e) => {
        e && e.preventDefault();
        this.setState({activePage: 1, searchOrder: 'rank'}, this.applyStateToHistory);
    }

    handleInputChange = (event, {name, value}) => {
        this.setState({[name]: value});
    }

    changeSearchOrder = (event, {value}) => {
        this.setState({searchOrder: value, activePage: 1}, this.applyStateToHistory);
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
                <div style={{marginTop: '3em', textAlign: 'center'}}>
                    <Paginator
                        activePage={this.state.activePage}
                        changePage={this.changePage}
                        totalPages={this.state.totalPages}
                    />
                </div>
            );
        }

        let clearSearchButton = null;
        if (this.state.queryStr) {
            clearSearchButton = (
                <Button icon labelPosition='right' onClick={this.clearSearch}>
                    Search: {this.state.queryStr}
                    <Icon name='close'/>
                </Button>
            )
        }

        return (
            <Container textAlign='center'>
                <Grid columns={3}>
                    <Grid.Column textAlign='left'>
                        <h1>
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
                        </h1>
                        {clearSearchButton}
                    </Grid.Column>
                    <Grid.Column textAlign='right'>
                        <Form onSubmit={this.handleSearch}>
                            <Input
                                icon='search'
                                placeholder='Search...'
                                name="searchStr"
                                value={this.state.searchStr}
                                onChange={this.handleInputChange}/>
                        </Form>
                    </Grid.Column>
                    <Grid.Column>
                        <Dropdown
                            size='large'
                            placeholder='Sort by...'
                            selection
                            name='searchOrder'
                            onChange={this.changeSearchOrder}
                            value={this.state.searchOrder}
                            options={this.state.videoOrders}
                            disabled={this.state.searchQuery === ''}
                        />
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

export class VideosRoute extends React.Component {

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
                <Route path='/videos/channel/new' exact component={NewChannel}/>
                <Route path='/videos/channel/:channel_link/edit' exact
                       component={(i) =>
                           <EditChannel
                               match={i.match}
                               history={i.history}
                           />
                       }
                />
                <Route path='/videos/channel/:channel_link/video' exact component={Videos}/>
                <Route path='/videos/channel/:channel_link/video/:video_id' exact component={Videos}/>
            </Container>
        )
    }
}
