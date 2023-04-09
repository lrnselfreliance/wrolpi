import React, {Fragment, useContext, useEffect, useState} from 'react';
import {Link, Route, Routes, useParams} from "react-router-dom";
import {
    CardLink,
    CardPoster,
    cardTitleWrapper,
    defaultSearchOrder,
    defaultVideoOrder,
    Duration,
    encodeMediaPath,
    FileIcon,
    findPosterPath,
    isoDatetimeToString,
    mimetypeColor,
    PageContainer,
    scrollToTop,
    SearchInput, SortButton,
    TabLinks,
    textEllipsis,
    useTitle
} from "./Common"
import VideoPage from "./VideoPlayer";
import {
    CardContent,
    CardDescription,
    CardHeader,
    Confirm,
    Container,
    Dropdown,
    Image,
    PlaceholderHeader,
    PlaceholderLine,
    StatisticLabel,
    StatisticValue,
    TableCell
} from "semantic-ui-react";
import {Channels, EditChannel, NewChannel} from "./Channels";
import {useChannel, useQuery, useSearchVideos, useVideo, useVideoStatistics} from "../hooks/customHooks";
import {FileRowTagIcon, FilesView} from "./Files";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import Icon from "semantic-ui-react/dist/commonjs/elements/Icon";
import {Button, Card, Header, Loader, Placeholder, Segment, Statistic, StatisticGroup} from "./Theme";
import {deleteVideos} from "../api";
import {Media, ThemeContext} from "../contexts/contexts";
import _ from "lodash";
import {SearchDomain} from "./Archive";

export function VideoWrapper() {
    const {videoId} = useParams();
    const {videoFile, prevFile, nextFile, fetchVideo} = useVideo(videoId);

    // Scroll to the top when videoId changes.
    useEffect(scrollToTop, [videoId]);

    return <VideoPage videoFile={videoFile} prevFile={prevFile} nextFile={nextFile} fetchVideo={fetchVideo}
                      autoplay={true}/>
}

function VideosPage() {

    const {channelId} = useParams();
    const {searchParams} = useQuery();
    const [selectedVideos, setSelectedVideos] = useState([]);
    const [deleteOpen, setDeleteOpen] = useState(false);

    let searchOrder = defaultVideoOrder;
    if (searchParams.get('order')) {
        // Use whatever order the user specified.
        searchOrder = searchParams.get('order');
    } else if (searchParams.get('q')) {
        // User used a search_str
        searchOrder = defaultSearchOrder;
    }

    const {searchStr, setSearchStr, videos, activePage, setPage, totalPages, fetchVideos} =
        useSearchVideos(null, channelId, searchOrder);

    const {channel} = useChannel(channelId);

    let title = 'Videos';
    if (channel && channel.name) {
        title = `${channel.name} Videos`;
    }
    useTitle(title);

    let videoOrders = [
        {value: 'upload_date', text: 'Date'},
        {value: 'duration', text: 'Duration'},
        {value: 'size', text: 'Size'},
        {value: 'view_count', text: 'Views'},
    ]

    if (searchStr) {
        videoOrders = [{value: 'rank', text: 'Search'}, ...videoOrders];
    }

    let header;
    if (channel && channel.name) {
        const editLink = `/videos/channel/${channelId}/edit`;
        header = <>
            <Header as='h1'>
                {channel.name}
                <Link to={editLink}>
                    <Icon name='edit' style={{marginLeft: '0.5em'}}/>
                </Link>
            </Header>
        </>;
    } else if (channelId) {
        header = <Placeholder style={{marginBottom: '1em'}}>
            <PlaceholderHeader>
                <PlaceholderLine/>
            </PlaceholderHeader>
        </Placeholder>;
    }

    const onSelect = (path, checked) => {
        if (checked && path) {
            setSelectedVideos([...selectedVideos, path]);
        } else if (path) {
            setSelectedVideos(selectedVideos.filter(i => i !== path));
        }
    }

    const onDelete = async (e) => {
        e.preventDefault();
        setDeleteOpen(false);
        const videoIds = videos.filter(i => selectedVideos.indexOf(i['path']) >= 0).map(i => i['video']['id']);
        await deleteVideos(videoIds);
        await fetchVideos();
        setSelectedVideos([]);
    }

    const invertSelection = async () => {
        const newSelectedVideos = videos.map(video => video['key']).filter(i => selectedVideos.indexOf(i) < 0);
        setSelectedVideos(newSelectedVideos);
    }

    const clearSelection = async (e) => {
        if (e) e.preventDefault();
        setSelectedVideos([]);
    }

    const selectElm = <div style={{marginTop: '0.5em'}}>
        <Button
            color='red'
            disabled={_.isEmpty(selectedVideos)}
            onClick={() => setDeleteOpen(true)}
        >Delete</Button>
        <Confirm
            open={deleteOpen}
            content='Are you sure you want to delete these video files?  This cannot be undone.'
            confirmButton='Delete'
            onCancel={() => setDeleteOpen(false)}
            onConfirm={onDelete}
        />
        <Button
            color='grey'
            onClick={() => invertSelection()}
            disabled={_.isEmpty(videos)}
        >
            Invert
        </Button>
        <Button
            color='yellow'
            onClick={() => clearSelection()}
            disabled={_.isEmpty(videos) || _.isEmpty(selectedVideos)}
        >
            Clear
        </Button>
    </div>;

    const {body, paginator, selectButton, viewButton, limitDropdown, tagQuerySelector} = FilesView(
        videos,
        activePage,
        totalPages,
        selectElm,
        selectedVideos,
        onSelect,
        setPage,
    );

    const searchInput = <SearchInput clearable searchStr={searchStr} onSubmit={setSearchStr} actionIcon='search'/>;

    return <>
        {header}
        <Media at='mobile'>
            <Grid>
                <Grid.Row>
                    <Grid.Column width={2}>{selectButton}</Grid.Column>
                    <Grid.Column width={2}>{viewButton}</Grid.Column>
                    <Grid.Column width={4}>{limitDropdown}</Grid.Column>
                    <Grid.Column width={2}>{tagQuerySelector}</Grid.Column>
                    <Grid.Column width={6}><SortButton sorts={videoOrders}/></Grid.Column>
                </Grid.Row>
                <Grid.Row>
                    <Grid.Column width={10}>{searchInput}</Grid.Column>
                </Grid.Row>
            </Grid>
        </Media>
        <Media greaterThanOrEqual='tablet'>
            <Grid>
                <Grid.Row>
                    <Grid.Column width={1}>{selectButton}</Grid.Column>
                    <Grid.Column width={1}>{viewButton}</Grid.Column>
                    <Grid.Column width={2}>{limitDropdown}</Grid.Column>
                    <Grid.Column width={1}>{tagQuerySelector}</Grid.Column>
                    <Grid.Column width={5}><SortButton sorts={videoOrders}/></Grid.Column>
                </Grid.Row>
                <Grid.Row>
                    <Grid.Column width={8}>{searchInput}</Grid.Column>
                </Grid.Row>
            </Grid>
        </Media>
        {body}
        {paginator}
    </>
}

function Statistics() {
    useTitle('Video Statistics');

    const {statistics} = useVideoStatistics();
    const {videos, historical, channels} = statistics;

    if (!videos) {
        return <Loader active inline='centered'/>
    }

    const videoNames = [
        {key: 'videos', label: 'Videos'},
        {key: 'sum_size', label: 'Total Size'},
        {key: 'max_size', label: 'Largest Video'},
        {key: 'week', label: 'Downloads Past Week'},
        {key: 'month', label: 'Downloads Past Month'},
        {key: 'year', label: 'Downloads Past Year'},
        {key: 'sum_duration', label: 'Total Duration'},
    ];
    const historicalNames = [
        {key: 'average_count', label: 'Average Monthly Downloads'},
        {key: 'average_size', label: 'Average Monthly Usage'},
    ];
    const channelNames = [
        {key: 'channels', label: 'Channels'},
    ];

    const buildSegment = (title, names, stats) => {
        return <Segment>
            <Header textAlign='center' as='h1'>{title}</Header>
            <StatisticGroup>
                {names.map(
                    ({key, label}) =>
                        <Statistic key={key} style={{margin: '2em'}}>
                            <StatisticValue>{stats[key]}</StatisticValue>
                            <StatisticLabel>{label}</StatisticLabel>
                        </Statistic>
                )}
            </StatisticGroup>
        </Segment>
    }

    return <>
        {buildSegment('Videos', videoNames, videos)}
        {buildSegment('Historical Video', historicalNames, historical)}
        {buildSegment('Channels', channelNames, channels)}
    </>
}

export function VideosRoute(props) {
    const links = [
        {text: 'Videos', to: '/videos', key: 'videos', end: true},
        {text: 'Channels', to: '/videos/channel', key: 'channel'},
        {text: 'Statistics', to: '/videos/statistics', key: 'statistics'},
    ];

    return <PageContainer>
        <TabLinks links={links}/>
        <Routes>
            <Route path='/' exact element={<VideosPage/>}/>
            <Route path='channel' exact element={<Channels/>}/>
            <Route path='statistics' exact element={<Statistics/>}/>
            <Route path='channel/new' exact element={<NewChannel/>}/>
            <Route path='channel/:channelId/edit' exact element={<EditChannel/>}/>
            <Route path='channel/:channelId/video' exact element={<VideosPage/>}/>
        </Routes>
    </PageContainer>
}

export function VideoCard({file}) {
    const {video} = file;
    const {s} = useContext(ThemeContext);

    let video_url = `/videos/video/${video.id}`;
    const upload_date = isoDatetimeToString(video.upload_date);
    // A video may not have a channel.
    const channel = video.channel ? video.channel : null;
    let channel_url = null;
    if (channel) {
        channel_url = `/videos/channel/${channel.id}/video`;
        video_url = `/videos/channel/${channel.id}/video/${video.id}`;
    }

    let poster = <CardPoster to={video_url} file={file}/>;

    const color = mimetypeColor(file.mimetype);
    return <Card color={color}>
        {poster}
        <Duration video={video}/>
        <CardContent {...s}>
            <CardHeader>
                <Container textAlign='left'>
                    <Link to={video_url} className="no-link-underscore card-link">
                        <p {...s}>{cardTitleWrapper(file.title || file.name || video.stem || video.video_path)}</p>
                    </Link>
                </Container>
            </CardHeader>
            <CardDescription>
                <Container textAlign='left'>
                    {channel && <Link to={channel_url} className="no-link-underscore card-link">
                        <b {...s}>{channel.name}</b>
                    </Link>}
                    <p {...s}>{upload_date}</p>
                </Container>
            </CardDescription>
        </CardContent>
    </Card>
}

export function VideoRowCells({file}) {
    const {video} = file;

    let video_url = `/videos/video/${video.id}`;
    const poster_path = findPosterPath(file);
    const poster_url = poster_path ? `/media/${encodeMediaPath(poster_path)}` : null;

    let poster;
    if (poster_url) {
        poster = <CardLink to={video_url}>
            <Image wrapped
                   src={poster_url}
                   width='50px'
            />
        </CardLink>
    } else {
        poster = <FileIcon file={file} size='large'/>;
    }

    // Fragment for SelectableRow
    return <React.Fragment>
        <TableCell>
            <center>
                {poster}
            </center>
        </TableCell>
        <TableCell>
            <CardLink to={video_url}>
                <FileRowTagIcon file={file}/>
                {textEllipsis(video.title || video.stem || video.video_path)}
            </CardLink>
        </TableCell>
    </React.Fragment>
}
