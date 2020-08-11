import React from 'react';
import {Link, Route} from "react-router-dom";
import Paginator, {
    DEFAULT_LIMIT,
    defaultSearchOrder,
    defaultVideoOrder,
    searchOrders,
    VideoCards,
    videoOrders,
    VIDEOS_API
} from "./Common"
import VideoPage from "./VideoPlayer";
import {getChannel, getVideo, searchVideos} from "../api";
import {Button, Dropdown, Form, Grid, Header, Icon, Input} from "semantic-ui-react";
import * as QueryString from 'query-string';
import Container from "semantic-ui-react/dist/commonjs/elements/Container";
import {Channels, EditChannel, NewChannel} from "./Channels";
import {VideoPlaceholder} from "./Placeholder";

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

export class VideoWrapper extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            video: null,
            prev: null,
            next: null,
            channel: null,
        }
    }

    async componentDidMount() {
        await this.fetchVideo();
    }

    async fetchVideo() {
        // Get and display the Video specified in the Router match
        let [video, prev, next] = await getVideo(this.props.match.params.video_id);
        let channel = await getChannel(this.props.match.params.channel_link);
        this.setState({video, prev, next, channel}, scrollToTop);
    }

    async componentDidUpdate(prevProps, prevState) {
        if (prevProps.match.params.video_id !== this.props.match.params.video_id) {
            await this.fetchVideo();
        }
    }

    render() {
        if (this.state.video && this.state.channel) {
            return <VideoPage {...this.state} history={this.props.history} autoplay={false}/>
        } else {
            return <VideoPlaceholder/>
        }
    }
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

class VideosPreview extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            videos: null,
        };
    }

    async componentDidMount() {
        await this.fetchVideos();
    }

    render() {
        let header = <h2>{this.title}</h2>;
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

export class FavoriteVideosPreview extends VideosPreview {

    constructor() {
        super();
        this.title = 'Favorite Videos'
    }

    async fetchVideos() {
        let [videos] = await searchVideos(
            0, 3, null, null, true, '-favorite');
        this.setState({videos});
    }

}

export class ViewedVideosPreview extends VideosPreview {

    constructor() {
        super();
        this.title = 'Recently Viewed Videos'
    }

    async fetchVideos() {
        let [videos] = await searchVideos(
            0, 3, null, null, null, '-viewed');
        this.setState({videos});
    }

}


class Videos extends React.Component {

    constructor(props) {
        super(props);
        const query = QueryString.parse(this.props.location.search);
        let activePage = query.page ? parseInt(query.page) : 1; // First page is 1 by default, of course.
        let searchStr = query.q || '';
        let searchOrder = query.o || defaultVideoOrder;

        this.state = {
            channel: null,
            videos: null,
            queryStr: searchStr,
            searchStr: '',
            limit: DEFAULT_LIMIT,
            activePage: activePage,
            totalPages: null,
            prev: null,
            next: null,
            videoOrders: searchStr === '' ? videoOrders : searchOrders,
            searchOrder: searchOrder,
            title: '',
        };
    }

    async componentDidMount() {
        if (this.props.match.params.channel_link) {
            await this.fetchChannel();
        } else {
            await this.fetchVideos();
        }
        this.setTitle();
    }

    async componentDidUpdate(prevProps, prevState, snapshot) {
        let params = this.props.match.params;

        let channelChanged = params.channel_link !== prevProps.match.params.channel_link;
        let pageChanged = (
            prevState.activePage !== this.state.activePage ||
            prevState.searchOrder !== this.state.searchOrder ||
            prevState.queryStr !== this.state.queryStr
        );

        if (channelChanged) {
            await this.fetchChannel();
        } else if (pageChanged) {
            this.applyStateToHistory();
            await this.fetchVideos();
        }
    }

    setTitle() {
        let title = '';
        if (this.props.filter === 'favorites') {
            title = 'Favorite Videos';
        } else if (this.state.channel) {
            title = this.state.channel.name;
        } else {
            // Find the matching title from the search orders.
            for (let i = 0; i < this.state.videoOrders.length; i++) {
                let item = this.state.videoOrders[i];
                if (item.value === this.state.searchOrder) {
                    title = item.title;
                }
            }
        }
        this.setState({title: title});
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
                title: channel ? channel.title : '',
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
            offset, this.state.limit, channel_link, this.state.queryStr, favorites, this.state.searchOrder);

        let totalPages = Math.round(total / this.state.limit) || 1;
        this.setState({videos, totalPages});
    }

    changePage = async (activePage) => {
        this.setState({activePage});
    }

    clearSearch = async () => {
        this.setState({searchStr: '', queryStr: '', searchOrder: defaultVideoOrder, activePage: 1});
    }

    applyStateToHistory = () => {
        let {history, location} = this.props;
        let {activePage, searchStr, searchOrder} = this.state;
        changePageHistory(history, location, activePage, searchStr, searchOrder);
    }

    handleSearch = async (e) => {
        e && e.preventDefault();
        this.setState({activePage: 1, searchOrder: defaultSearchOrder, queryStr: this.state.searchStr},
            this.applyStateToHistory);
    }

    handleInputChange = (event, {name, value}) => {
        this.setState({[name]: value});
    }

    changeSearchOrder = (event, {value}) => {
        this.setState({searchOrder: value, activePage: 1}, this.applyStateToHistory);
    }

    render() {
        let {
            activePage,
            channel,
            queryStr,
            searchOrder,
            searchStr,
            title,
            totalPages,
            videoOrders,
            videos,
        } = this.state;

        let body = <VideoPlaceholder/>;

        if (videos && videos.length === 0) {
            // API didn't send back any videos, tell the user what to do.
            if (this.props.filter === 'favorites') {
                body = <p>You haven't tagged any videos as favorite.</p>;
            } else {
                // default empty body.
                body = <p>No videos retrieved. Have you downloaded videos yet?</p>;
            }
        } else if (videos) {
            body = <VideoCards videos={videos}/>;
        }

        let pagination = null;
        if (totalPages) {
            pagination = (
                <div style={{marginTop: '3em', textAlign: 'center'}}>
                    <Paginator
                        activePage={activePage}
                        changePage={this.changePage}
                        totalPages={totalPages}
                    />
                </div>
            );
        }

        let clearSearchButton = (
            <Button icon labelPosition='right' onClick={this.clearSearch}>
                Search: {queryStr}
                <Icon name='close'/>
            </Button>
        );

        return (
            <Container textAlign='center'>
                <Grid columns={3} stackable>
                    <Grid.Column textAlign='left'>
                        <h1>
                            {title}
                            {
                                channel &&
                                <>
                                    &nbsp;
                                    &nbsp;
                                    <Link to={`/videos/channel/${channel.link}/edit`}>
                                        <Icon name="edit"/>
                                    </Link>
                                </>
                            }
                        </h1>
                        {queryStr && clearSearchButton}
                    </Grid.Column>
                    <Grid.Column textAlign='right'>
                        <Form onSubmit={this.handleSearch}>
                            <Input
                                fluid
                                icon='search'
                                placeholder='Search...'
                                name="searchStr"
                                value={searchStr}
                                onChange={this.handleInputChange}/>
                        </Form>
                    </Grid.Column>
                    <Grid.Column>
                        <Dropdown
                            size='large'
                            placeholder='Sort by...'
                            selection
                            fluid
                            name='searchOrder'
                            onChange={this.changeSearchOrder}
                            value={searchOrder}
                            options={videoOrders}
                            disabled={searchOrder === defaultSearchOrder}
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
            <>
                <Container fluid={true} style={{margin: '2em', padding: '0.5em'}}>
                    <Route path='/videos' exact
                           component={(i) =>
                               <Videos
                                   match={i.match}
                                   history={i.history}
                                   location={i.location}
                               />}
                    />
                    <Route path='/videos/favorites' exact
                           component={(i) =>
                               <Videos
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
                </Container>
            </>
        )
    }
}
