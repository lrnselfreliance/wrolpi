import React from 'react';
import {Link, Route} from "react-router-dom";
import Paginator, {
    changePageHistory,
    DEFAULT_LIMIT,
    defaultSearchOrder,
    defaultVideoOrder,
    humanFileSize,
    Progresses,
    scrollToTop,
    searchOrders,
    secondsToString,
    VideoCards,
    videoOrders
} from "./Common"
import VideoPage from "./VideoPlayer";
import {download, getChannel, getStatistics, getVideo, refresh, searchVideos} from "../api";
import {
    Button,
    Dropdown,
    Form,
    Grid,
    Header,
    Icon,
    Input,
    Loader,
    Modal,
    Radio,
    Segment,
    Statistic,
    Tab
} from "semantic-ui-react";
import * as QueryString from 'query-string';
import Container from "semantic-ui-react/dist/commonjs/elements/Container";
import {Channels, EditChannel, NewChannel} from "./Channels";
import {VideoPlaceholder} from "./Placeholder";

class ManageVideos extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            streamUrl: null,
            mostRecentDownload: '',
        }
    }

    download = async (e) => {
        e.preventDefault();
        let response = await download();
        if (response.stream_url) {
            this.setState({streamUrl: response.stream_url});
        }
    }

    refresh = async (e) => {
        e.preventDefault();
        let response = await refresh();
        if (response.stream_url) {
            this.setState({streamUrl: response.stream_url});
        }
    }

    render() {
        return (
            <Container>
                <Header as="h1">Manage Videos</Header>

                <p>
                    <Button primary
                            onClick={this.download}
                    >
                        Download Videos
                    </Button>
                    <label>Download any missing videos</label>
                    <br/>
                </p>

                <p>
                    <Button secondary
                            onClick={this.refresh}
                    >
                        Refresh Video Files
                    </Button>
                    <label>Search for any videos in the media directory</label>
                </p>

                {this.state.streamUrl && <Progresses streamUrl={this.state.streamUrl}/>}
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
            no_channel: null,
        }
    }

    async componentDidMount() {
        await this.fetchVideo();
    }

    async fetchVideo() {
        // Get and display the Video specified in the Router match
        let [video, prev, next] = await getVideo(this.props.match.params.video_id);
        let channel_link = this.props.match.params.channel_link;
        let channel = channel_link ? await getChannel(channel_link) : null;
        let no_channel = false;
        if (!channel) {
            no_channel = true;
        }
        this.setState({video, prev, next, channel, no_channel}, scrollToTop);
    }

    async componentDidUpdate(prevProps, prevState) {
        if (prevProps.match.params.video_id !== this.props.match.params.video_id) {
            // Clear the current video so that it will change, even if the video is playing.
            this.setState({video: null, prev: null, next: null, channel: null});
            await this.fetchVideo();
        }
    }

    render() {
        if (this.state.video && (this.state.no_channel || this.state.channel)) {
            return <VideoPage {...this.state} history={this.props.history} autoplay={true}/>
        } else {
            return <VideoPlaceholder/>
        }
    }
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

    constructor(props) {
        super(props);
        this.title = 'Favorite Videos'
    }

    async fetchVideos() {
        let [videos] = await searchVideos(
            0, 3, null, null, true, '-favorite');
        this.setState({videos});
    }

}

export class ViewedVideosPreview extends VideosPreview {

    constructor(props) {
        super(props);
        this.title = 'Recently Viewed Videos'
    }

    async fetchVideos() {
        let [videos] = await searchVideos(
            0, 3, null, null, null, '-viewed');
        this.setState({videos});
    }

}

function VideoFilterModal(props) {
    const [favorite, setFavorite] = React.useState(false);
    const [censored, setCensored] = React.useState(false);

    let applyFilters = () => {
        let filters = [];
        if (favorite) {
            filters = filters.concat(['favorite']);
        }
        if (censored) {
            filters = filters.concat(['censored']);
        }
        props.applyFilters(filters);
        props.close();
    }

    return (
        <Modal open={props.open} onClose={props.close} onOpen={props.open}>
            <Modal.Header>Filter Videos</Modal.Header>
            <Modal.Content>
                <Modal.Description>
                    <Form>
                        <Form.Input>
                            <Radio
                                toggle
                                checked={favorite}
                                onChange={() => setFavorite(!favorite)}
                                label='Favorites'
                            />
                        </Form.Input>
                        <Form.Input>
                            <Radio
                                toggle
                                checked={censored}
                                onChange={() => setCensored(!censored)}
                                label='Censored'
                            />
                        </Form.Input>
                    </Form>
                </Modal.Description>
            </Modal.Content>
            <Modal.Actions>
                <Button color='blue' onClick={applyFilters}>Apply</Button>
                <Button color='black' onClick={props.close}>Close</Button>
            </Modal.Actions>
        </Modal>
    )
}


class Videos extends React.Component {

    constructor(props) {
        super(props);
        const query = QueryString.parse(this.props.location.search);
        let activePage = query.page ? parseInt(query.page) : 1; // First page is 1 by default, of course.
        let searchStr = query.q || '';
        let searchOrder = query.o || defaultVideoOrder;

        let filters = this.props.filter !== undefined ? ['favorites'] : [];

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
            filtersOpen: false,
            filters,
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
        let {queryStr, searchOrder, filters} = this.state;
        let [videos, total] = await searchVideos(offset, this.state.limit, channel_link, queryStr, searchOrder, filters);

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
        let {activePage, queryStr, searchOrder} = this.state;
        changePageHistory(history, location, activePage, queryStr, searchOrder);
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

    applyFilters = (filters) => {
        this.setState({filters}, this.fetchVideos);
    }

    closeFilters = () => {
        this.setState({filtersOpen: false});
    }

    openFilters = () => {
        this.setState({filtersOpen: true});
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

        let filtersApplied = this.state.filters.length > 0;

        return (
            <Container textAlign='center'>
                <Grid columns={4} stackable>
                    <Grid.Column textAlign='left' width={6}>
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
                    <Grid.Column textAlign='right' width={5}>
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
                    <Grid.Column width={1}>
                        <Button icon onClick={this.openFilters} color={filtersApplied ? 'black' : null}>
                            <Icon name='filter'/>
                        </Button>
                        <VideoFilterModal
                            applyFilters={this.applyFilters}
                            open={this.state.filtersOpen}
                            close={this.closeFilters}
                        />
                    </Grid.Column>
                    <Grid.Column width={4}>
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

class ManageTabs extends React.Component {
    render() {
        const panes = [
            {menuItem: 'Manage', render: () => <Tab.Pane><ManageVideos/></Tab.Pane>},
            {menuItem: 'Statistics', render: () => <Tab.Pane><Statistics/></Tab.Pane>},
        ]
        return (
            <Container>
                <Tab panes={panes}/>
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
                    <Route path='/videos/manage' exact component={ManageTabs}/>
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
                    <Route path='/videos/statistics' exact component={Statistics}/>
                </Container>
            </>
        )
    }
}

class Statistics extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            videos: null,
            historical: null,
            channels: null,
        };
        this.videoNames = [
            {key: 'videos', label: 'Downloaded Videos'},
            {key: 'favorites', label: 'Favorite Videos'},
            {key: 'sum_size', label: 'Total Size'},
            {key: 'max_size', label: 'Largest Video'},
            {key: 'week', label: 'Downloads Past Week'},
            {key: 'month', label: 'Downloads Past Month'},
            {key: 'year', label: 'Downloads Past Year'},
            {key: 'sum_duration', label: 'Total Duration'},
        ];
        this.historicalNames = [
            {key: 'average_count', label: 'Average Monthly Downloads'},
            {key: 'average_size', label: 'Average Monthly Usage'},
        ];
        this.channelNames = [
            {key: 'channels', label: 'Channels'},
        ];
    }

    async componentDidMount() {
        await this.fetchStatistics();
    }

    async fetchStatistics() {
        let stats = await getStatistics();
        stats.videos.sum_duration = secondsToString(stats.videos.sum_duration);
        stats.videos.sum_size = humanFileSize(stats.videos.sum_size, true);
        stats.videos.max_size = humanFileSize(stats.videos.max_size, true);
        stats.historical.average_size = humanFileSize(stats.historical.average_size, true);
        this.setState({...stats});
    }

    buildSegment(title, names, stats) {
        return <Segment secondary>
            <Header textAlign='center' as='h1'>{title}</Header>
            <Statistic.Group>
                {names.map(
                    ({key, label}) =>
                        <Statistic key={key} style={{margin: '2em'}}>
                            <Statistic.Value>{stats[key]}</Statistic.Value>
                            <Statistic.Label>{label}</Statistic.Label>
                        </Statistic>
                )}
            </Statistic.Group>
        </Segment>
    }

    render() {
        if (this.state.videos) {
            return (
                <>
                    {this.buildSegment('Videos', this.videoNames, this.state.videos)}
                    {this.buildSegment('Historical Video', this.historicalNames, this.state.historical)}
                    {this.buildSegment('Channels', this.channelNames, this.state.channels)}
                </>
            )
        } else {
            return <Loader active inline='centered'/>
        }
    }
}
