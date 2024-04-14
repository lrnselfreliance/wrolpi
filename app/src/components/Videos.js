import React, {useContext, useEffect, useState} from 'react';
import {Link, Route, Routes, useParams} from "react-router-dom";
import {
    APIButton,
    CardLink,
    CardPoster,
    defaultFileOrder,
    defaultSearchOrder,
    Duration,
    encodeMediaPath,
    ErrorMessage,
    FileIcon,
    findPosterPath,
    humanFileSize,
    humanNumber,
    isoDatetimeToString,
    mimetypeColor,
    PageContainer,
    PreviewLink,
    scrollToTop,
    SearchInput,
    secondsToFullDuration,
    SortButton,
    TabLinks,
    textEllipsis,
    useTitle
} from "./Common"
import VideoPage from "./VideoPlayer";
import {
    CardContent,
    CardDescription,
    CardHeader,
    Container,
    Image,
    PlaceholderHeader,
    PlaceholderLine,
    StatisticLabel,
    StatisticValue,
    TableCell
} from "semantic-ui-react";
import {ChannelEditPage, ChannelNewPage, ChannelsPage} from "./Channels";
import {useChannel, useSearchOrder, useSearchVideos, useVideo, useVideoStatistics} from "../hooks/customHooks";
import {FileRowTagIcon, FilesView} from "./Files";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import Icon from "semantic-ui-react/dist/commonjs/elements/Icon";
import {Button, Card, Header, Loader, Placeholder, Segment, Statistic, StatisticGroup} from "./Theme";
import {deleteVideos} from "../api";
import {Media, QueryContext, ThemeContext} from "../contexts/contexts";
import _ from "lodash";

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
    const {searchParams} = React.useContext(QueryContext);
    const [selectedVideos, setSelectedVideos] = useState([]);

    let searchOrder = defaultFileOrder;
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
        {value: 'published_datetime', text: 'Published Date', short: 'P.Date'},
        {value: 'length', text: 'Length'},
        {value: 'size', text: 'Size'},
        {value: 'view_count', text: 'Views'},
        {value: 'viewed', text: 'Recently Viewed', short: 'R.Viewed'},
        {value: 'download_datetime', text: 'Download Date', short: 'D.Date'},
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
        const newSelectedVideos = checked && path ? [...selectedVideos, path] : selectedVideos.filter(i => i !== path);
        console.debug(`Selected Videos: ${newSelectedVideos}`);
        setSelectedVideos(newSelectedVideos);
    }

    const onDelete = async () => {
        const videoIds = videos.filter(i => selectedVideos.indexOf(i['primary_path']) >= 0).map(i => i['video']['id']);
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
        <APIButton
            color='red'
            disabled={_.isEmpty(selectedVideos)}
            confirmButton='Delete'
            confirmContent='Are you sure you want to delete these video files?  This cannot be undone.'
            onClick={onDelete}
        >Delete</APIButton>
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
        !!searchStr,
    );

    const [localSearchStr, setLocalSearchStr] = React.useState(searchStr || '');
    const searchInput = <SearchInput
        searchStr={localSearchStr}
        onChange={setLocalSearchStr}
        onSubmit={setSearchStr}
        placeholder='Search Videos...'
    />;

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
                    <Grid.Column width={16}>{searchInput}</Grid.Column>
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
                    <Grid.Column width={4}><SortButton sorts={videoOrders}/></Grid.Column>
                    <Grid.Column width={7}>{searchInput}</Grid.Column>
                </Grid.Row>
            </Grid>
        </Media>
        {body}
        {paginator}
    </>
}

function VideosStatistics() {
    useTitle('Video Statistics');

    const {statistics} = useVideoStatistics();

    if (statistics === null) {
        // Request is pending.
        return <Loader active inline='centered'/>
    } else if (statistics === undefined) {
        return <ErrorMessage>Unable to fetch Video Statistics</ErrorMessage>
    }

    const {videos, historical, channels} = statistics;

    const videoNames = [
        {key: 'videos', label: 'Videos'},
        {key: 'sum_size', label: 'Total Size'},
        {key: 'max_size', label: 'Largest Video'},
        {key: 'week', label: 'Downloads Past Week'},
        {key: 'month', label: 'Downloads Past Month'},
        {key: 'year', label: 'Downloads Past Year'},
        {key: 'sum_duration', label: 'Total Duration'},
    ];
    const commentsNames = [
        {key: 'have_comments', label: 'Have Comments'},
        {key: 'no_comments', label: 'Missing Comments'},
        {key: 'failed_comments', label: 'Failed Comments'},
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
        {buildSegment('Video Comments', commentsNames, videos)}
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
            <Route path='channel' exact element={<ChannelsPage/>}/>
            <Route path='statistics' exact element={<VideosStatistics/>}/>
            <Route path='channel/new' exact element={<ChannelNewPage/>}/>
            <Route path='channel/:channelId/edit' exact element={<ChannelEditPage/>}/>
            <Route path='channel/:channelId/video' exact element={<VideosPage/>}/>
        </Routes>
    </PageContainer>
}

export function VideoCard({file}) {
    const {video} = file;
    const {s} = useContext(ThemeContext);

    // Default to video FilePreview for lone video files.
    let video_url;

    const published_datetime = isoDatetimeToString(file.published_datetime);
    // A video may not have a channel.
    const channel = video.channel ? video.channel : null;
    let channel_url = null;
    if (channel) {
        // Link to Video in the Channel if possible.
        channel_url = `/videos/channel/${channel.id}/video`;
        video_url = `/videos/channel/${channel.id}/video/${video.id}`;
    } else if (file.files.length > 1) {
        // No Channel, but the video has multiple files (subtitles, etc.).  Use the full VideoPage.
        video_url = `/videos/video/${video.id}`
    }

    let poster = <CardPoster to={video_url} file={file}/>;

    let header = <span {...s}
                       className='card-title-ellipsis'>{file.title || file.name || video.stem || video.name}</span>;
    if (video_url) {
        // Link to Channel-Video page or Video page.
        header = <Link to={video_url} className="no-link-underscore card-link">{header}</Link>;
    } else {
        // Video is just a lone video file.
        header = <PreviewLink file={file}>
            {header}
        </PreviewLink>;
    }

    const color = mimetypeColor(file.mimetype);
    return <Card color={color}>
        {poster}
        <Duration totalSeconds={file.length}/>
        <CardContent {...s}>
            <CardHeader>
                <Container textAlign='left'>
                    {header}
                </Container>
            </CardHeader>
            <CardDescription>
                <Container textAlign='left'>
                    {channel && <Link to={channel_url} className="no-link-underscore card-link">
                        <b {...s}>{channel.name}</b>
                    </Link>}
                    <p {...s}>{published_datetime}</p>
                </Container>
            </CardDescription>
        </CardContent>
    </Card>
}

export function VideoRowCells({file}) {
    const {video} = file;
    let {sort} = useSearchOrder();
    sort = sort ? sort.replace(/^-+/, '') : null;

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

    let dataCell = file.published_datetime ? isoDatetimeToString(file.published_datetime) : '';
    if (sort === 'length') {
        dataCell = secondsToFullDuration(file.length || 0);
    } else if (sort === 'size') {
        dataCell = humanFileSize(file.size);
    } else if (sort === 'view_count') {
        dataCell = humanNumber(video.view_count || 0);
    } else if (sort === 'viewed') {
        dataCell = isoDatetimeToString(file.viewed);
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
                {textEllipsis(file.title || video.stem || video.video_path)}
            </CardLink>
        </TableCell>
        <TableCell>{dataCell}</TableCell>
    </React.Fragment>
}
