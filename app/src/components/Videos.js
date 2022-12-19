import React, {Fragment, useContext, useEffect, useState} from 'react';
import {Link, Route, Routes, useParams} from "react-router-dom";
import {
    CardLink,
    CardPosterLink, cardTitleWrapper,
    defaultSearchOrder,
    defaultVideoOrder,
    Duration,
    epochToDateString,
    FileIcon,
    isEmpty,
    mimetypeColor,
    PageContainer,
    scrollToTop,
    SearchInput,
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
import {FilesView} from "./Files";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import Icon from "semantic-ui-react/dist/commonjs/elements/Icon";
import {Button, Card, CardIcon, Header, Loader, Placeholder, Segment, Statistic, StatisticGroup} from "./Theme";
import {deleteVideos} from "../api";
import {ThemeContext} from "../contexts/contexts";

export function VideoWrapper() {
    const {videoId} = useParams();
    const {videoFile, prevFile, nextFile, setFavorite} = useVideo(videoId);

    // Scroll to the top when videoId changes.
    useEffect(scrollToTop, [videoId]);

    return <VideoPage videoFile={videoFile} prevFile={prevFile} nextFile={nextFile}
                      setFavorite={setFavorite} autoplay={true}/>
}

function VideosPage({filter}) {

    const {channelId} = useParams();
    const {searchParams, updateQuery} = useQuery();
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

    let filtersEnabled = searchParams.getAll('filter');
    filtersEnabled = filter ? [...filtersEnabled, filter] : filtersEnabled;

    const {searchStr, setSearchStr, videos, activePage, setPage, limit, setLimit, totalPages, setOrderBy, fetchVideos} =
        useSearchVideos(null, channelId, searchOrder, filtersEnabled);
    const setView = (value) => updateQuery({view: value});
    const view = searchParams.get('view');

    const {channel} = useChannel(channelId);

    let title = 'Videos';
    if (filter && filter.indexOf('favorite') >= 0) {
        title = 'Favorite Videos';
    }
    if (channel && channel.name) {
        title = `${channel.name} Videos`;
    }
    useTitle(title);

    const filterOptions = [
        {text: 'Favorites', key: 'favorite', value: 'favorite'},
        {text: 'Censored', key: 'censored', value: 'censored'},
    ];
    const setFilters = (value) => updateQuery({filter: value});

    let videoOrders = [
        {key: '-upload_date', value: '-upload_date', text: 'Newest'},
        {key: 'upload_date', value: 'upload_date', text: 'Oldest'},
        {key: '-duration', value: '-duration', text: 'Longest'},
        {key: 'duration', value: 'duration', text: 'Shortest'},
        {key: '-viewed', value: '-viewed', text: 'Recently viewed'},
        {key: '-size', value: '-size', text: 'Largest'},
        {key: 'size', value: 'size', text: 'Smallest'},
        {key: '-view_count', value: '-view_count', text: 'Most Views'},
        {key: 'view_count', value: 'view_count', text: 'Least Views'},
        {key: '-modification_datetime', value: '-modification_datetime', text: 'Newest File'},
        {key: 'modification_datetime', value: 'modification_datetime', text: 'Oldest File'},
    ];

    if (searchStr) {
        videoOrders = [{key: 'rank', value: 'rank', text: 'Search Rank'}, ...videoOrders];
    }

    const menuColumns = <Fragment>
        <Grid.Column mobile={8} computer={5}>
            <SearchInput clearable searchStr={searchStr} onSubmit={setSearchStr} actionIcon='search'/>
        </Grid.Column>
        <Grid.Column mobile={6} computer={5}>
            <Dropdown selection fluid
                      size='large'
                      placeholder='Sort by...'
                      value={searchOrder}
                      options={videoOrders}
                      onChange={(e, {value}) => setOrderBy(value)}
            />
        </Grid.Column>
    </Fragment>;

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
            disabled={isEmpty(selectedVideos)}
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
            disabled={isEmpty(videos)}
        >
            Invert
        </Button>
        <Button
            color='yellow'
            onClick={() => clearSelection()}
            disabled={isEmpty(videos) || isEmpty(selectedVideos)}
        >
            Clear
        </Button>
    </div>;

    return <>
        {header}
        <FilesView
            files={videos}
            view={view}
            limit={limit}
            activePage={activePage}
            totalPages={totalPages}
            showView={true}
            showLimit={true}
            showSelect={true}
            onSelect={onSelect}
            selectedKeys={selectedVideos}
            selectElem={selectElm}
            setView={setView}
            setLimit={setLimit}
            setPage={setPage}
            filterOptions={filterOptions}
            activeFilters={filtersEnabled}
            setFilters={setFilters}
            multipleFilters={true}
            menuColumnsCount={3}
            menuColumns={menuColumns}
        >
        </FilesView>
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
        {key: 'favorites', label: 'Favorite Videos'},
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

    return (
        <>
            {buildSegment('Videos', videoNames, videos)}
            {buildSegment('Historical Video', historicalNames, historical)}
            {buildSegment('Channels', channelNames, channels)}
        </>
    )
}

export function VideosRoute(props) {
    const links = [
        {text: 'Videos', to: '/videos', key: 'videos', end: true},
        {text: 'Favorites', to: '/videos/favorites', key: 'favorites'},
        {text: 'Channels', to: '/videos/channel', key: 'channel'},
        {text: 'Statistics', to: '/videos/statistics', key: 'statistics'},
    ];

    return (
        <PageContainer>
            <TabLinks links={links}/>
            <Routes>
                <Route path='/' exact element={<VideosPage/>}/>
                <Route path='favorites' exact element={<VideosPage filter='favorite' header='Favorite Videos'/>}/>
                <Route path='channel' exact element={<Channels/>}/>
                <Route path='statistics' exact element={<Statistics/>}/>
                <Route path='channel/new' exact element={<NewChannel/>}/>
                <Route path='channel/:channelId/edit' exact element={<EditChannel/>}/>
                <Route path='channel/:channelId/video' exact element={<VideosPage/>}/>
            </Routes>
        </PageContainer>
    )
}

export function VideoCard({file}) {
    const {video} = file;
    const {s} = useContext(ThemeContext);

    let video_url = `/videos/video/${video.id}`;
    const upload_date = epochToDateString(video.upload_date);
    // A video may not have a channel.
    const channel = video.channel ? video.channel : null;
    let channel_url = null;
    if (channel) {
        channel_url = `/videos/channel/${channel.id}/video`;
        video_url = `/videos/channel/${channel.id}/video/${video.id}`;
    }
    const poster_url = video.poster_path ? `/media/${encodeURIComponent(video.poster_path)}` : null;

    let imageLabel = null;
    if (video.favorite) {
        imageLabel = {corner: 'left', icon: 'heart', color: 'green'};
    }
    let poster = <Link to={video_url}><CardIcon><FileIcon file={file}/></CardIcon></Link>;
    if (poster_url) {
        poster = <CardPosterLink to={video_url} poster_url={poster_url} imageLabel={imageLabel}/>;
    }

    const color = mimetypeColor(file.mimetype);
    return <Card color={color}>
        {poster}
        <Duration video={video}/>
        <CardContent {...s}>
            <CardHeader>
                <Container textAlign='left'>
                    <Link to={video_url} className="no-link-underscore card-link">
                        <p {...s}>{cardTitleWrapper(video.title || video.stem || video.video_path)}</p>
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
    const poster_url = video.poster_path ? `/media/${encodeURIComponent(video.poster_path)}` : null;

    let poster;
    let imageLabel = video.favorite ? {corner: 'left', icon: 'heart', color: 'green'} : null;
    if (poster_url) {
        poster = <CardLink to={video_url}>
            <Image wrapped
                   src={poster_url}
                   label={imageLabel}
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
                {textEllipsis(video.title || video.stem || video.video_path)}
            </CardLink>
        </TableCell>
    </React.Fragment>
}
