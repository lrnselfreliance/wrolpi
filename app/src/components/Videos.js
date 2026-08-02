import React, {useEffect, useRef, useState} from 'react';
import {Link, Outlet, useParams} from "react-router";
import {useHotkeys} from "react-hotkeys-hook";
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
    HelpHeader,
    InfoHeader,
    isoDatetimeToAgoPopup,
    mimetypeColor,
    PageContainer,
    PreviewLink,
    scrollToTop,
    secondsToFullDuration,
    TabLinks,
    textEllipsis,
    useTitle,
    CookiesUnlockModal
} from "./Common"
import VideoPage from "./VideoPlayer";
import {
    ActionInput,
    Button,
    Card,
    Header,
    Icon,
    Loading,
    Modal,
    NumberInput,
    Panel,
    Placeholder,
    Statistic,
    StatisticGroup,
    Table,
    Textarea,
    TextInput,
    Tooltip,
} from "./ui";
import {useChannel, useSearchOrder, useSearchVideos, useVideo, useVideoStatistics} from "../hooks/customHooks";
import {DeepSearchHint, FileRowTagIcon, FilesView, SearchControlBar} from "./Files";
import {BulkTagModal} from "./BulkTagModal";
import {TaggedDeleteConfirmModal} from "./TaggedDeleteConfirmModal";
import {
    deleteFileGroups,
    deleteCookies,
    fetchSuggestedUserAgent,
    fetchVideoDownloaderConfig,
    getCookiesStatus,
    lockCookies,
    postVideoFileFormat,
    previewBatchReorganization,
    updateVideoDownloaderConfig,
    uploadCookies,
} from "../api";
import {QueryContext} from "../contexts/contexts";
import _ from "lodash";
import {defaultFileOrder, defaultSearchOrder} from "./Vars";
import {InputForm, ToggleForm, useForm} from "../hooks/useForm";
import {VideoFormatSelectorForm, VideoResolutionSelectorForm} from "./Download";
import {BatchReorganizeModal} from "./collections/BatchReorganizeModal";

export function VideoWrapper() {
    const {fileGroupId} = useParams();
    const {videoFile, prevFile, nextFile, fetchVideo} = useVideo(fileGroupId);

    // Scroll to the top when fileGroupId changes.
    useEffect(scrollToTop, [fileGroupId]);

    return <VideoPage videoFile={videoFile} prevFile={prevFile} nextFile={nextFile} fetchVideo={fetchVideo}
                      autoplay={true}/>
}

export function VideosPage() {

    const {channelId} = useParams();
    const {searchParams} = React.useContext(QueryContext);
    const [selectedVideos, setSelectedVideos] = useState([]);
    const [bulkTagOpen, setBulkTagOpen] = useState(false);
    const [taggedFileGroups, setTaggedFileGroups] = useState(null);
    const searchInputRef = React.useRef();

    useHotkeys('f', (e) => {
        e.preventDefault();
        if (searchInputRef.current) {
            searchInputRef.current.focus();
        }
    }, {enableOnFormTags: false});

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
        header = <div style={{marginBottom: '1em'}}><Placeholder lines={1}/></div>;
    }

    const onSelect = (path, checked) => {
        const newSelectedVideos = checked && path ? [...selectedVideos, path] : selectedVideos.filter(i => i !== path);
        console.debug(`Selected Videos: ${newSelectedVideos}`);
        setSelectedVideos(newSelectedVideos);
    }

    const onDelete = async (force = false) => {
        const fileGroupIds = videos.filter(i => selectedVideos.indexOf(i['primary_path']) >= 0).map(i => i['id']);
        const result = await deleteFileGroups(fileGroupIds, force);
        if (result && result.tagged) {
            setTaggedFileGroups(result.file_groups);
            return;
        }
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

    const onBulkTagComplete = async () => {
        await fetchVideos();
        setSelectedVideos([]);
    }

    const selectElm = <div style={{marginTop: '0.5em'}}>
        <Button
            role='primary'
            disabled={_.isEmpty(selectedVideos)}
            onClick={() => setBulkTagOpen(true)}
        >Tag</Button>
        <APIButton
            role='danger'
            disabled={_.isEmpty(selectedVideos)}
            confirmButton='Delete'
            confirmContent='Are you sure you want to delete these video files?  This cannot be undone.'
            onClick={() => onDelete(false)}
        >Delete</APIButton>
        <Button
            role='cancel'
            onClick={() => invertSelection()}
            disabled={_.isEmpty(videos)}
        >
            Invert
        </Button>
        <Button
            role='cancel'
            onClick={() => clearSelection()}
            disabled={_.isEmpty(videos) || _.isEmpty(selectedVideos)}
        >
            Clear
        </Button>
        <BulkTagModal
            open={bulkTagOpen}
            onClose={() => setBulkTagOpen(false)}
            paths={selectedVideos}
            onComplete={onBulkTagComplete}
        />
    </div>;

    const {body, paginator, viewButton} = FilesView(
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

    return <>
        {header}
        <SearchControlBar
            searchStr={searchStr}
            setSearchStr={setSearchStr}
            placeholder='Search Videos...'
            inputRef={searchInputRef}
            viewButton={viewButton}
            sorts={videoOrders}
            showCensored={true}
            showDeep={true}
        />
        {body}
        <DeepSearchHint searchStr={searchStr} files={videos}/>
        {paginator}
        <TaggedDeleteConfirmModal
            open={taggedFileGroups !== null}
            taggedFileGroups={taggedFileGroups}
            onCancel={() => setTaggedFileGroups(null)}
            onConfirm={async () => {
                setTaggedFileGroups(null);
                await onDelete(true);
            }}
        />
    </>
}

function VideoFileNameForm({form}) {
    const [message, setMessage] = React.useState(null);

    const debouncedOnChange = React.useCallback(
        _.debounce(async (value) => {
            const response = await postVideoFileFormat(value);
            const {error, preview} = await response.json();
            if (error) {
                setMessage({content: error, header: 'Invalid File Name', negative: true});
            } else {
                setMessage({content: preview, header: 'File Name Preview', positive: true});
            }
        }, 300),
        []
    );

    // Cleanup debounce on unmount
    React.useEffect(() => {
        return () => debouncedOnChange.cancel();
    }, [debouncedOnChange]);

    const onChange = debouncedOnChange;

    const label = <InfoHeader
        headerSize='h5'
        headerContent='Video File Format'
        popupContent={<>
            <p>Common yt-dlp variables:</p>
            <ul>
                <li><code>%(title)s</code> - Video title</li>
                <li><code>%(uploader)s</code> - Channel/uploader name</li>
                <li><code>%(upload_date)s</code> - Upload date (YYYYMMDD)</li>
                <li><code>%(upload_year)s</code> - Upload year (YYYY)</li>
                <li><code>%(upload_month)s</code> - Upload month (01-12)</li>
                <li><code>%(id)s</code> - Video ID</li>
                <li><code>%(channel)s</code> - Channel name</li>
                <li><code>%(duration)s</code> - Duration in seconds</li>
                <li><code>%(playlist_index)s</code> - Playlist index</li>
                <li><code>%(ext)s</code> - File extension (required, must be at end)</li>
            </ul>
            <p>See yt-dlp docs for all variables. Subdirectories supported.</p>
        </>}
    />;

    return <InputForm
        form={form}
        name='file_name_format'
        path='yt_dlp_options.file_name_format'
        label={label}
        onChange={onChange}
        message={message}
    />
}

const settingsGridStyle = {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
    gap: '1em',
    marginBottom: '1em',
};

export function VideosSettingsPage() {
    useTitle('Videos Settings');

    const [batchModalOpen, setBatchModalOpen] = useState(false);
    const [channelsNeedingReorg, setChannelsNeedingReorg] = useState(0);
    const [fetchingReorgCount, setFetchingReorgCount] = useState(true);

    // Check how many channels need reorganization on mount
    useEffect(() => {
        setFetchingReorgCount(true);
        previewBatchReorganization('channel')
            .then(data => {
                setChannelsNeedingReorg(data.total_collections || 0);
            })
            .catch(() => {
                setChannelsNeedingReorg(0);
            })
            .finally(() => {
                setFetchingReorgCount(false);
            });
    }, []);

    const emptyFormData = {
        video_resolutions: ['1080p', '720p', '480p', 'maximum'],
        yt_dlp_options: {
            continue_dl: true,
            file_name_format: '%(uploader)s_%(upload_date)s_%(id)s_%(title)s.%(ext)s',
            merge_output_format: 'mp4',
            nooverwrites: true,
            writeautomaticsub: true,
            writeinfojson: true,
            writesubtitles: true,
            writethumbnail: true,
        },
        yt_dlp_extra_args: '',
        download_missing_video_comments: false,
        user_agent: '',
        sleep_requests: 0.75,
    };

    const configSubmitter = async () => {
        return await updateVideoDownloaderConfig(configForm.formData);
    };

    const configForm = useForm({
        fetcher: fetchVideoDownloaderConfig,
        submitter: configSubmitter,
        emptyFormData,
    });

    const [suggestedUserAgent, setSuggestedUserAgent] = useState('');

    React.useEffect(() => {
        const fetchSuggested = async () => {
            const ua = await fetchSuggestedUserAgent();
            setSuggestedUserAgent(ua);
        };
        fetchSuggested();
    }, []);

    const downloadMissingVideoCommentsLabel = <InfoHeader
        headerSize='h5'
        headerContent='Download Missing Video Comments'
        popupContent='When enabled, WROLPi will automatically download comments for videos that are missing them.'
    />;

    return <>
        <Panel>
            <Header as='h3'>Video Downloader Config</Header>

            <form onSubmit={e => e.preventDefault()}>
                <div style={settingsGridStyle}>
                    <VideoResolutionSelectorForm
                        form={configForm}
                        name='video_resolutions'
                        path='video_resolutions'
                    />
                    <VideoFormatSelectorForm
                        form={configForm}
                        name='merge_output_format'
                        path='yt_dlp_options.merge_output_format'
                    />
                    <VideoFileNameForm form={configForm}/>
                </div>
                <div style={settingsGridStyle}>
                    <ToggleForm
                        form={configForm}
                        label='Do not overwrite existing files'
                        name='nooverwrites'
                        path='yt_dlp_options.nooverwrites'
                        icon='file video'
                    />
                    <ToggleForm
                        form={configForm}
                        label='Download automatic subtitles'
                        name='writeautomaticsub'
                        path='yt_dlp_options.writeautomaticsub'
                        icon='closed captioning'
                    />
                </div>
                <div style={settingsGridStyle}>
                    <ToggleForm
                        form={configForm}
                        label='Download subtitles'
                        name='writesubtitles'
                        path='yt_dlp_options.writesubtitles'
                        icon='closed captioning outline'
                    />
                    <ToggleForm
                        form={configForm}
                        label='Download thumbnail'
                        name='writethumbnail'
                        path='yt_dlp_options.writethumbnail'
                        icon='image'
                    />
                </div>
                <div style={settingsGridStyle}>
                    <ToggleForm
                        form={configForm}
                        label='Download info JSON'
                        name='writeinfojson'
                        path='yt_dlp_options.writeinfojson'
                        icon='file code'
                    />
                    <ToggleForm
                        form={configForm}
                        label='Continue partial downloads'
                        name='continue_dl'
                        path='yt_dlp_options.continue_dl'
                        icon='play'
                    />
                </div>
                <div style={settingsGridStyle}>
                    <ToggleForm
                        form={configForm}
                        label={downloadMissingVideoCommentsLabel}
                        name='download_missing_video_comments'
                        path='download_missing_video_comments'
                        icon='comments'
                    />
                </div>
                <div style={settingsGridStyle}>
                    <InputForm
                        form={configForm}
                        name='yt_dlp_extra_args'
                        path='yt_dlp_extra_args'
                        label='Extra yt-dlp Arguments'
                        placeholder='--prefer-free-formats'
                        icon='terminal'
                    />
                    <div>
                        <InfoHeader
                            headerSize='h5'
                            headerContent='Sleep Between Requests'
                            popupContent='Seconds to sleep between yt-dlp API requests. Helps avoid rate limiting and bot detection. Set to 0 to disable. Does not affect video download speed.'
                        />
                        <NumberInput
                            step={0.25}
                            min={0}
                            max={10}
                            value={configForm.formData.sleep_requests ?? 0.75}
                            onChange={(value) => configForm.setValue('sleep_requests', parseFloat(value) || 0)}
                            placeholder='0.75'
                            rightSection={<span style={{fontSize: 12, color: 'var(--muted)'}}>sec</span>}
                            rightSectionWidth={36}
                        />
                    </div>
                </div>
                <div style={settingsGridStyle}>
                    <div style={{gridColumn: '1 / -1'}}>
                        <InfoHeader
                            headerSize='h5'
                            headerContent='User Agent'
                            popupContent="Custom user-agent string for yt-dlp. Should match the browser used to export cookies. Click &quot;Use Current Browser&quot; to auto-fill with your browser's user-agent."
                        />
                        <ActionInput
                            value={configForm.formData.user_agent || ''}
                            onChange={(e) => configForm.setValue('user_agent', e.currentTarget.value)}
                            placeholder='Leave empty to use yt-dlp default'
                            action={<Button role='cancel'
                                            onClick={() => configForm.setValue('user_agent', suggestedUserAgent)}>
                                Use Current Browser
                            </Button>}
                        />
                    </div>
                </div>

                <div style={{textAlign: 'right'}}>
                    <APIButton
                        role='primary'
                        disabled={configForm.disabled || !configForm.ready}
                        type='submit'
                        style={{marginTop: '0.5em'}}
                        onClick={configForm.onSubmit}
                        id='video_settings_save_button'
                    >Save</APIButton>
                </div>
            </form>
        </Panel>

        <Panel>
            <Header as='h4'>File Organization</Header>
            <p>
                {fetchingReorgCount
                    ? 'Checking for channels that need reorganization...'
                    : <>
                        <strong>{channelsNeedingReorg}</strong> channel{channelsNeedingReorg !== 1 ? 's' : ''}
                        {channelsNeedingReorg > 0
                            ? ' have files that do not match the current file name format.'
                            : '. All channels are organized correctly.'}
                    </>
                }
            </p>
            <Button
                role='retry'
                icon='folder open outline'
                onClick={() => setBatchModalOpen(true)}
                id='reorganize_all_channels_button'
                disabled={fetchingReorgCount || channelsNeedingReorg === 0}
                loading={fetchingReorgCount}
            >
                Reorganize All Channels
            </Button>
        </Panel>

        <CookiesSettingsSection/>

        <BatchReorganizeModal
            open={batchModalOpen}
            onClose={() => setBatchModalOpen(false)}
            kind='channel'
            onComplete={() => {
                setBatchModalOpen(false);
                setChannelsNeedingReorg(0);
            }}
        />
    </>
}

function CookiesSettingsSection() {
    const [status, setStatus] = useState({cookies_exist: false, cookies_unlocked: false});
    const [loading, setLoading] = useState(true);
    const [uploadModalOpen, setUploadModalOpen] = useState(false);
    const [unlockModalOpen, setUnlockModalOpen] = useState(false);
    const [cookiesContent, setCookiesContent] = useState('');
    const [password, setPassword] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const cookiesContentRef = useRef(null);

    useEffect(() => {
        if (uploadModalOpen) {
            const timer = setTimeout(() => {
                if (cookiesContentRef.current) {
                    cookiesContentRef.current.focus();
                }
            }, 100);
            return () => clearTimeout(timer);
        }
    }, [uploadModalOpen]);

    const fetchStatus = async () => {
        setLoading(true);
        const result = await getCookiesStatus();
        if (result) {
            setStatus(result);
        }
        setLoading(false);
    };

    useEffect(() => {
        fetchStatus();
    }, []);

    const handleUpload = async () => {
        if (password.length < 8) {
            return;
        }
        setSubmitting(true);
        const result = await uploadCookies(cookiesContent, password);
        setSubmitting(false);
        if (result.success) {
            setUploadModalOpen(false);
            setCookiesContent('');
            setPassword('');
            fetchStatus();
        }
    };

    const handleLock = async () => {
        setSubmitting(true);
        await lockCookies();
        setSubmitting(false);
        fetchStatus();
    };

    const handleDelete = async () => {
        setSubmitting(true);
        await deleteCookies();
        setSubmitting(false);
        fetchStatus();
    };

    // The two states that mean something take roles; the two that are just "nothing to
    // report" stay --muted, which is dimmer than --neutral in night and amber and so keeps
    // the least important states at the bottom.
    const getStatusLabel = () => {
        if (loading) return <span style={{color: 'var(--muted)'}}>Loading...</span>;
        if (!status.cookies_exist) return <span style={{color: 'var(--muted)'}}>No cookies stored</span>;
        if (status.cookies_unlocked) return <span style={{color: 'var(--success)'}}>Unlocked</span>;
        // Locked is not an error the user made, but cookie-requiring downloads fail until
        // somebody enters the password after a reboot -- that is attention, not failure.
        return <span style={{color: 'var(--warning)'}}>Locked</span>;
    };

    return <Panel>
        <HelpHeader
            headerSize='h4'
            headerContent='Encrypted Cookies'
            helpPath='/modules/videos/cookies/'
        />

        <p>Use this feature at your own risk! You may be suspended or blocked if abused!
        </p>

        <div style={{marginBottom: '1em'}}>
            <strong>Status:</strong> {getStatusLabel()}
        </div>

        <div style={{display: 'flex', gap: '0.5em', flexWrap: 'wrap'}}>
            {!status.cookies_exist && (
                <Button
                    role='primary'
                    icon='upload'
                    onClick={() => setUploadModalOpen(true)}
                    disabled={loading}
                >
                    Upload Cookies
                </Button>
            )}

            {status.cookies_exist && !status.cookies_unlocked && (
                <Button
                    role='save'
                    icon='unlock'
                    onClick={() => setUnlockModalOpen(true)}
                    disabled={loading}
                >
                    Unlock Cookies
                </Button>
            )}

            {status.cookies_exist && status.cookies_unlocked && (
                <Button
                    role='retry'
                    icon='lock'
                    onClick={handleLock}
                    loading={submitting}
                    disabled={loading || submitting}
                >
                    Lock Cookies
                </Button>
            )}

            {status.cookies_exist && (
                <>
                    <Button
                        role='primary'
                        icon='refresh'
                        onClick={() => setUploadModalOpen(true)}
                        disabled={loading}
                    >
                        Replace
                    </Button>
                    <APIButton
                        role='danger'
                        icon='trash'
                        onClick={handleDelete}
                        confirmButton='Delete'
                        confirmContent='Are you sure you want to delete the stored cookies? This cannot be undone.'
                        disabled={loading || submitting}
                    >
                        Delete
                    </APIButton>
                </>
            )}
        </div>

        {/* Upload Modal */}
        <Modal
            open={uploadModalOpen}
            onClose={() => setUploadModalOpen(false)}
            size='small'
        >
            <Modal.Header>Upload Cookies</Modal.Header>
            <Modal.Content>
                <form onSubmit={e => e.preventDefault()}>
                    <Textarea
                        ref={cookiesContentRef}
                        label='Cookies Content'
                        placeholder='Paste your cookies.txt content here (Netscape/Mozilla format)'
                        value={cookiesContent}
                        onChange={(e) => setCookiesContent(e.currentTarget.value)}
                        minRows={10}
                    />
                    <div style={{marginTop: '1em'}}>
                        <TextInput
                            label='Encryption Password'
                            type='password'
                            placeholder='Minimum 8 characters'
                            value={password}
                            onChange={(e) => setPassword(e.currentTarget.value)}
                            error={password.length > 0 && password.length < 8
                                ? 'Password must be at least 8 characters' : null}
                        />
                    </div>
                    <p style={{color: 'var(--muted)', fontSize: '0.9em'}}>
                        Remember this password - you'll need it to unlock cookies after each restart.
                    </p>
                </form>
            </Modal.Content>
            <Modal.Actions>
                <Button role='cancel' onClick={() => setUploadModalOpen(false)}>Cancel</Button>
                <Button
                    role='save'
                    icon='lock'
                    onClick={handleUpload}
                    loading={submitting}
                    disabled={!cookiesContent || password.length < 8 || submitting}
                >
                    Encrypt & Save
                </Button>
            </Modal.Actions>
        </Modal>

        <CookiesUnlockModal
            open={unlockModalOpen}
            onClose={() => setUnlockModalOpen(false)}
            onSuccess={fetchStatus}
        />
    </Panel>;
}

export function VideosStatistics() {
    useTitle('Video Statistics');

    const {statistics} = useVideoStatistics();

    if (statistics === null) {
        // Request is pending.
        return <Loading/>
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

    const buildPanel = (title, names, stats) => {
        return <Panel>
            <Header as='h1' style={{textAlign: 'center'}}>{title}</Header>
            <StatisticGroup>
                {names.map(
                    ({key, label}) =>
                        <Statistic key={key} value={stats[key]} label={label}/>
                )}
            </StatisticGroup>
        </Panel>
    }

    return <>
        {buildPanel('Videos', videoNames, videos)}
        {buildPanel('Video Comments', commentsNames, videos)}
        {buildPanel('Historical Video', historicalNames, historical)}
        {buildPanel('Channels', channelNames, channels)}
    </>
}

export function VideosTabLayout() {
    const links = [
        {text: 'Videos', to: '/videos', key: 'videos', end: true},
        {text: 'Channels', to: '/videos/channel', key: 'channel'},
        {text: 'Settings', to: '/videos/settings', key: 'settings'},
        {text: 'Statistics', to: '/videos/statistics', key: 'statistics'},
    ];

    return <PageContainer>
        <TabLinks links={links}/>
        <Outlet/>
    </PageContainer>
}

export function VideoCard({file}) {
    const {video} = file;
    const {sort} = useSearchOrder();
    const sortField = sort ? sort.replace(/^-/, '') : null;

    // Default to video FilePreview for lone video files.
    let video_url = `/videos/${file.id}`;

    // A video may not have a channel.
    const channel = video.channel ? video.channel : null;
    let channel_url = null;
    if (channel) {
        channel_url = `/videos/channel/${channel.id}/video`;
    }

    /*
     * The duration goes through CardPoster's `overlay` rather than being pinned to a
     * wrapper around it: the wrapper is the full width of the card, and a vertical video's
     * poster is only about half that once the height cap applies, so the badge landed well
     * clear of the frame it belongs to.
     */
    const media = <CardPoster to={video_url} file={file}
                              overlay={<Duration totalSeconds={file.length}/>}/>;

    const title = file.title || file.name || video.stem || video.name;
    let titleElm = <Tooltip label={title}>
        <span className='card-title-ellipsis'>{title}</span>
    </Tooltip>;
    if (video_url) {
        // Link to Channel-Video page or Video page.
        titleElm = <Link to={video_url} className="no-link-underscore card-link">{titleElm}</Link>;
    } else {
        // Video is just a lone video file.
        titleElm = <PreviewLink file={file}>
            {titleElm}
        </PreviewLink>;
    }

    let detailLine;
    if (sortField === 'length') {
        detailLine = secondsToFullDuration(file.length || 0);
    } else if (sortField === 'size') {
        detailLine = humanFileSize(file.size);
    } else if (sortField === 'view_count') {
        detailLine = `${humanNumber(video.view_count || 0)} views`;
    } else if (sortField === 'viewed') {
        detailLine = isoDatetimeToAgoPopup(file.viewed, false);
    } else if (sortField === 'download_datetime') {
        detailLine = isoDatetimeToAgoPopup(file.download_datetime, false);
    } else {
        detailLine = isoDatetimeToAgoPopup(file.published_datetime, false);
    }

    const meta = <>
        {channel && <div>
            <Link to={channel_url} className="no-link-underscore card-link">
                <b>{channel.name}</b>
            </Link>
        </div>}
        <div>{detailLine}</div>
    </>;

    return <Card media={media} title={titleElm} meta={meta}
                 color={mimetypeColor(file.mimetype, file.primary_path)}/>
}

export function VideoRowCells({file}) {
    const {video} = file;
    let {sort} = useSearchOrder();
    sort = sort ? sort.replace(/^-+/, '') : null;

    let video_url = `/videos/${file.id}`;
    const poster_path = findPosterPath(file);
    const poster_url = poster_path ? `/media/${encodeMediaPath(poster_path)}` : null;

    let poster;
    if (poster_url) {
        poster = <CardLink to={video_url}>
            <img alt='' src={poster_url} style={{width: '50px', height: 'auto'}}/>
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
        <Table.Cell>
            <div style={{textAlign: 'center'}}>
                {poster}
            </div>
        </Table.Cell>
        <Table.Cell>
            <CardLink to={video_url}>
                <FileRowTagIcon file={file}/>
                {textEllipsis(file.title || video.stem || video.video_path)}
            </CardLink>
        </Table.Cell>
        <Table.Cell>{dataCell}</Table.Cell>
    </React.Fragment>
}
