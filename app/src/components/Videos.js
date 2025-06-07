import React, {useContext, useEffect, useState} from 'react';
import {Link, Route, Routes, useParams} from "react-router-dom";
import {
    APIButton,
    CardLink,
    CardPoster,
    Duration,
    encodeMediaPath,
    ErrorMessage,
    FileIcon,
    findPosterPath,
    humanFileSize,
    humanNumber,
    InfoHeader,
    isoDatetimeToAgoPopup,
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
    Form,
    FormDropdown,
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
import {Button, Card, Header, Loader, Placeholder, Popup, Segment, Statistic, StatisticGroup} from "./Theme";
import {deleteVideos, fetchBrowserProfiles, fetchVideoDownloaderConfig, postVideoFileFormat, updateVideoDownloaderConfig} from "../api";
import {Media, QueryContext, ThemeContext} from "../contexts/contexts";
import _ from "lodash";
import {defaultFileOrder, defaultSearchOrder, HELP_VIEWER_URI} from "./Vars";
import {InputForm, ToggleForm, useForm} from "../hooks/useForm";
import {VideoResolutionSelectorForm} from "./Download";

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

    const {searchStr, setSearchStr, videos, activePage, setPage, totalPages, fetchVideos, loading} =
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
        {value: 'size_to_duration', text: 'Size to Duration', short: 'S/Duration'},
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
        {
            files: videos,
            activePage: activePage,
            totalPages: totalPages,
            selectElem: selectElm,
            selectedKeys: selectedVideos,
            onSelect: onSelect,
            setPage: setPage,
            headlines: !!searchStr,
            loading: loading,
        },
    );

    const [localSearchStr, setLocalSearchStr] = React.useState(searchStr || '');
    const searchInput = <SearchInput
        searchStr={localSearchStr}
        onChange={setLocalSearchStr}
        onClear={() => setLocalSearchStr(null)}
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

function VideoFileNameForm({form}) {
    const [message, setMessage] = React.useState(null);

    const onChange = async (value) => {
        const response = await postVideoFileFormat(value);
        const {error, preview} = await response.json();
        if (error) {
            setMessage({content: error, header: 'Invalid File Name', negative: true});
        } else {
            setMessage({content: preview, header: 'File Name Preview', positive: true});
        }
    }

    return <InputForm
        form={form}
        name='file_name_format'
        path='yt_dlp_options.file_name_format'
        label='Video File Format'
        onChange={onChange}
        message={message}
    />
}

function VideosSettings() {
    useTitle('Videos Settings');

    const emptyFormData = {
        video_resolutions: ['1080p', '720p', '480p', 'maximum'],
        yt_dlp_options: {
            file_name_format: '%(uploader)s_%(upload_date)s_%(id)s_%(title)s.%(ext)s',
            nooverwrites: true,
            writeautomaticsub: true,
            writesubtitles: true,
            writethumbnail: true,
        },
        always_use_browser_profile: false,
        yt_dlp_extra_args: '',
        browser_profile: '',
    };

    const configSubmitter = async () => {
        return await updateVideoDownloaderConfig(configForm.formData);
    };

    const configForm = useForm({
        fetcher: fetchVideoDownloaderConfig,
        submitter: configSubmitter,
        emptyFormData,
    });

    const emptyProfilesOptions = [{key: null, text: 'No profiles found'}];
    const loadingProfilesOptions = [{key: null, text: 'Loading profiles, please wait...'}];
    const [browserProfilesOptions, setBrowserProfilesOptions] = useState(loadingProfilesOptions);

    const localFetchBrowserProfiles = async () => {
        let tempProfiles = [];
        let localBrowserProfiles = await fetchBrowserProfiles();

        const chromiumProfiles = localBrowserProfiles['chromium_profiles'];
        for (const value of Object.values(chromiumProfiles)) {
            tempProfiles.push({value: value, text: value});
        }
        const firefoxProfiles = localBrowserProfiles['firefox_profiles'];
        for (const value of Object.values(firefoxProfiles)) {
            tempProfiles.push({value: value, text: value});
        }

        if (_.isEmpty(tempProfiles)) {
            tempProfiles = emptyProfilesOptions;
        }
        console.debug('VideosSettings: Got browser profiles:', tempProfiles);
        setBrowserProfilesOptions(tempProfiles);
    };

    React.useEffect(() => {
        localFetchBrowserProfiles();
    }, []);

    const alwaysUseBrowserProfileLabel = <InfoHeader
        headerSize='h5'
        headerContent='Always Use Browser Profile'
        popupContent='Always download videos with the selected browser profile. This is risky, and therefore discouraged.'
    />;

    return <Segment>
        <Header as='h3'>Video Downloader Config</Header>

        <Form>
            <Grid>
                <Grid.Row columns={2}>
                    <Grid.Column mobile={16} computer={8}>
                        <VideoResolutionSelectorForm
                            form={configForm}
                            name='video_resolutions'
                            path='video_resolutions'
                        />
                    </Grid.Column>
                    <Grid.Column mobile={16} computer={8}>
                        <VideoFileNameForm form={configForm}/>
                    </Grid.Column>
                </Grid.Row>
                <Grid.Row columns={2}>
                    <Grid.Column mobile={16} computer={8}>
                        <ToggleForm
                            form={configForm}
                            label='Do not overwrite existing files'
                            name='nooverwrites'
                            path='yt_dlp_options.nooverwrites'
                            icon='file video'
                        />
                    </Grid.Column>
                    <Grid.Column mobile={16} computer={8}>
                        <ToggleForm
                            form={configForm}
                            label='Download automatic subtitles'
                            name='writeautomaticsub'
                            path='yt_dlp_options.writeautomaticsub'
                            icon='closed captioning'
                        />
                    </Grid.Column>
                </Grid.Row>
                <Grid.Row>
                    <Grid.Column mobile={16} computer={8}>
                        <ToggleForm
                            form={configForm}
                            label='Download subtitles'
                            name='writesubtitles'
                            path='yt_dlp_options.writesubtitles'
                            icon='closed captioning outline'
                        />
                    </Grid.Column>
                    <Grid.Column mobile={16} computer={8}>
                        <ToggleForm
                            form={configForm}
                            label='Download thumbnail'
                            name='writethumbnail'
                            path='yt_dlp_options.writethumbnail'
                            icon='image'
                        />
                    </Grid.Column>
                </Grid.Row>
                <Grid.Row>
                    <Grid.Column mobile={16} computer={8}>
                        <InputForm
                            form={configForm}
                            name='yt_dlp_extra_args'
                            path='yt_dlp_extra_args'
                            label='Extra yt-dlp Arguments'
                            placeholder='--prefer-free-formats'
                            icon='terminal'
                        />
                    </Grid.Column>
                    <Grid.Column mobile={16} computer={8}>
                        <VideoBrowserCookiesSelector form={configForm} options={browserProfilesOptions}/>
                    </Grid.Column>
                </Grid.Row>
                <Grid.Row>
                    <Grid.Column mobile={16} computer={8}/>
                    <Grid.Column mobile={16} computer={8}>
                        <ToggleForm
                            form={configForm}
                            label={alwaysUseBrowserProfileLabel}
                            name='always_use_browser_profile'
                            path='always_use_browser_profile'
                            disabled={!configForm.formData.browser_profile}
                        />
                    </Grid.Column>
                </Grid.Row>

                <Grid.Row columns={1}>
                    <Grid.Column textAlign='right'>
                        <APIButton
                            disabled={configForm.disabled || !configForm.ready}
                            type='submit'
                            style={{marginTop: '0.5em'}}
                            onClick={configForm.onSubmit}
                            id='video_settings_save_button'
                        >Save</APIButton>
                    </Grid.Column>
                </Grid.Row>
            </Grid>
        </Form>
    </Segment>
}


export function VideoBrowserCookiesSelector({
                                                form,
                                                options,
                                                name = 'browser_profile',
                                                path = 'browser_profile',
                                            }) {
    const [inputProps, inputAttrs] = form.getSelectionProps({name, path});

    const popupContent = <div>
        Select a browser profile to use for cookies. This is useful for sites that require login to download videos.
        <br/>
        <br/>
        <p><a href={HELP_VIEWER_URI + '/modules/videos/#how-to-use-browser-profiles'}>Help page</a></p>
    </div>;

    return <>
        <InfoHeader
            headerSize='h5'
            headerContent='Browser Profile'
            popupContent={popupContent}
        />
        <FormDropdown
            selection
            placeholder='Select Browser Profile'
            options={options}
            name={name}
            id='browser_profile_dropdown'
            {...inputProps}
        />
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
        {key: 'censored_videos', label: 'Censored Videos'},
    ];
    const commentsNames = [
        {key: 'have_comments', label: 'Have Comments'},
        {key: 'missing_comments', label: 'Missing Comments'},
        {key: 'failed_comments', label: 'Failed Comments'},
    ];
    const historicalNames = [
        {key: 'average_count', label: 'Average Monthly Downloads'},
        {key: 'average_size', label: 'Average Monthly Usage'},
    ];
    const channelNames = [
        {key: 'channels', label: 'Channels'},
        {key: 'tagged_channels', label: 'Tagged Channels'},
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
        {text: 'Settings', to: '/videos/settings', key: 'settings'},
        {text: 'Statistics', to: '/videos/statistics', key: 'statistics'},
    ];

    return <PageContainer>
        <TabLinks links={links}/>
        <Routes>
            <Route path='/' exact element={<VideosPage/>}/>
            <Route path='channel' exact element={<ChannelsPage/>}/>
            <Route path='settings' exact element={<VideosSettings/>}/>
            <Route path='statistics' exact element={<VideosStatistics/>}/>
            <Route path='channel/new' exact element={<ChannelNewPage/>}/>
            <Route path='channel/:channelId/edit' exact element={<ChannelEditPage/>}/>
            <Route path='channel/:channelId/video' exact element={<VideosPage/>}/>
            <Route path='/video/:videoSlug' exact element={<VideosPage/>}/>
        </Routes>
    </PageContainer>
}

export function VideoCard({file}) {
    const {video} = file;
    const {s} = useContext(ThemeContext);

    // Default to video FilePreview for lone video files.
    let video_url;

    // A video may not have a channel.
    const channel = video.channel ? video.channel : null;
    let channel_url = null;
    if (channel) {
        // Link to Video in the Channel if possible.
        channel_url = `/videos/channel/${channel.id}/video`;
        video_url = `/videos/channel/${channel.id}/video/${video.id}`;
    } else if (file.files.length > 1) {
        // No Channel, but the video has multiple files (subtitles, etc.).  Use the full VideoPage.
        video_url = `/videos/video/${video.id}`;
    }
    if (file.slug) {
        video_url = `/videos/video/${file.slug}`;
    }

    let poster = <CardPoster to={video_url} file={file}/>;

    const title = file.title || file.name || video.stem || video.name;
    let header = <span {...s} className='card-title-ellipsis'>{title}</span>;
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
                    <Popup on='hover'
                           trigger={header}
                           content={title}/>
                </Container>
            </CardHeader>
            <CardDescription>
                <Container textAlign='left'>
                    {channel && <Link to={channel_url} className="no-link-underscore card-link">
                        <b {...s}>{channel.name}</b>
                    </Link>}
                    <p {...s}>{isoDatetimeToAgoPopup(file.published_datetime, false)}</p>
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

    let dataCell = file.published_datetime ? isoDatetimeToAgoPopup(file.published_datetime) : '';
    if (sort === 'length') {
        dataCell = secondsToFullDuration(file.length || 0);
    } else if (sort === 'size') {
        dataCell = humanFileSize(file.size);
    } else if (sort === 'view_count') {
        dataCell = humanNumber(video.view_count || 0);
    } else if (sort === 'viewed') {
        dataCell = isoDatetimeToAgoPopup(file.viewed);
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
