import React, {useContext, useState} from 'react';
import {addTag, deleteVideos, removeTag} from "../api";
import {Link, useNavigate, useParams} from "react-router-dom";
import _ from "lodash";
import {
    BackButton,
    encodeMediaPath,
    humanFileSize,
    humanNumber,
    isoDatetimeToString,
    PageContainer,
    PreviewPath,
    useTitle
} from "./Common";
import {Confirm} from "semantic-ui-react";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import Container from "semantic-ui-react/dist/commonjs/elements/Container";
import {VideoPlaceholder} from "./Placeholder";
import {useChannel} from "../hooks/customHooks";
import {ThemeContext} from "../contexts/contexts";
import {Button, darkTheme, Header, Icon, Segment, Tab, TabPane} from "./Theme";
import {VideoCard} from "./Videos";
import {TagsProvider, TagsSelector} from "../Tags";

const MEDIA_PATH = '/media';


function videoFileLink(path, directory = false) {
    if (path) {
        const href = directory ?
            // Add / to end of directory.
            `${MEDIA_PATH}/${encodeMediaPath(path)}/` :
            `${MEDIA_PATH}/${encodeMediaPath(path)}`;
        return <a href={href} target='_blank' rel='noopener noreferrer'>
            <pre>{path}</pre>
        </a>
    } else {
        return 'Unknown'
    }
}

function VideoPage({videoFile, prevFile, nextFile, fetchVideo, ...props}) {
    const {theme} = useContext(ThemeContext);

    const navigate = useNavigate();
    const videoRef = React.useRef();
    let [deleteOpen, setDeleteOpen] = useState(false);

    useTitle(videoFile === null || videoFile === undefined ? null : videoFile.video.title);
    let video;
    if (videoFile) {
        video = videoFile.video;
    }

    // Seeks to the `seconds` on video player.
    const setVideoTime = (seconds) => {
        videoRef.current.currentTime = seconds;
    }

    // Get the Video's channel, fallback to the URL's channel id.
    const {channelId} = useParams();
    const {channel} = useChannel(video && video.channel_id ? video.channel_id : channelId);

    if (videoFile === null) {
        return <VideoPlaceholder/>;
    }
    if (videoFile === undefined) {
        return <PageContainer><Header as='h4'>Could not find video</Header></PageContainer>;
    }

    const handleDeleteVideo = async (video_id) => {
        try {
            await deleteVideos([video_id])
            setDeleteOpen(false);
        } catch (e) {
            setDeleteOpen(false);
            throw e;
        }
        navigate(-1);
    }

    let videoUrl = `${MEDIA_PATH}/${encodeMediaPath(video.video_path)}`;
    let downloadUrl = `/download/${encodeMediaPath(video.video_path)}`;

    let posterUrl = video.poster_path ? `${MEDIA_PATH}/${encodeMediaPath(video.poster_path)}` : null;
    const {caption_files} = video;
    const captionUrls = caption_files && caption_files.length > 0 ?
        caption_files.filter(i => i['mimetype'] === 'text/vtt').map(i => `${MEDIA_PATH}/${encodeMediaPath(i['path'])}`)
        : [];

    let description = 'No description available.';
    if (video && video['description']) {
        // Only replace empty description if there is one available.
        description = video['description'];
        description = chaptersInDescription(description, setVideoTime)
    }

    let descriptionPane = {
        menuItem: 'Description', render: () => <TabPane>
            <pre className="wrap-text">
                {description}
            </pre>
        </TabPane>
    };

    let aboutPane = {
        menuItem: 'About', render: () => <TabPane>
            <h3>Size</h3>
            <p>{videoFile.size ? humanFileSize(videoFile.size) : 'Unknown'}</p>

            <h3>Source URL</h3>
            <p>{video.url ? <a href={video.url}>{video.url}</a> : 'N/A'}</p>

            <h3>View Count</h3>
            <p>{video.view_count ? humanNumber(video.view_count) : 'N/A'}</p>

            <h3>Censored</h3>
            <p>{video.censored ? 'Yes' : 'No'}</p>
        </TabPane>
    }

    let captionsPane = {
        menuItem: 'Captions', render: () => <TabPane>
            <pre>{video.caption || 'No captions available.'}</pre>
        </TabPane>
    };

    const {poster_file, info_json_file} = video;
    let filesPane = {
        menuItem: 'Files', render: () => <TabPane>
            <h3>Video File</h3>
            {videoFileLink(video['video_path'])}

            <h4>Info JSON File</h4>
            {info_json_file &&
                <PreviewPath
                    path={info_json_file['path']}
                    mimetype={info_json_file['mimetype']}>{info_json_file['path']}</PreviewPath>
            }

            <h4>Caption Files</h4>
            {caption_files &&
                caption_files.map(i => <PreviewPath key={i['path']} {...i}>{i['path']}</PreviewPath>)
            }

            <h4>Poster File</h4>
            {poster_file &&
                <PreviewPath
                    path={poster_file['path']}
                    mimetype={poster_file['mimetype']}>{poster_file['path']}</PreviewPath>
            }

            <h4>Directory</h4>
            {videoFileLink(videoFile['directory'], true)}
        </TabPane>
    }

    let tabPanes = [descriptionPane, aboutPane, filesPane, captionsPane];
    const tabMenu = theme === darkTheme ? {inverted: true, attached: true} : {attached: true};

    const localAddTag = async (name) => {
        await addTag(videoFile, name);
        await fetchVideo();
    }

    const localRemoveTag = async (name) => {
        await removeTag(videoFile, name);
        await fetchVideo();
    }

    return <>
        <Container style={{margin: '1em'}}>
            <BackButton/>
        </Container>

        <video controls
               autoPlay={props.autoplay !== undefined ? props.autoplay : true}
               poster={posterUrl}
               id="player"
               playsInline={true}
               style={{maxWidth: '100%'}}
               ref={videoRef}
        >
            <source src={videoUrl} type="video/mp4"/>
            {/* Only WebVTT captions can be displayed. */}
            {captionUrls.map(i => <track kind="captions" label="English" src={i} srcLang="en" default/>)}
        </video>

        <Container style={{marginTop: '1em'}}>
            <Segment>

                <Header as='h2'>{videoFile.title || videoFile.stem || video.video_path}</Header>
                {video.upload_date && <h3>{isoDatetimeToString(video.upload_date)}</h3>}
                <h3>
                    {channel && <Link to={`/videos/channel/${channel.id}/video`}>
                        {channel.name}
                    </Link>}
                </h3>

                <p>
                    <a href={downloadUrl} target='_blank' rel='noopener noreferrer'>
                        <Button style={{margin: '0.5em'}}>
                            <Icon name='download'/>
                            Download
                        </Button>
                    </a>
                    <Button
                        color='red'
                        onClick={() => setDeleteOpen(true)}
                        style={{margin: '0.5em'}}
                    >Delete</Button>
                    <Confirm
                        open={deleteOpen}
                        content='Are you sure you want to delete this video?  All files related to this video will be deleted. It will not be downloaded again!'
                        confirmButton='Delete'
                        onCancel={() => setDeleteOpen(false)}
                        onConfirm={() => handleDeleteVideo(video.id)}
                    />
                </p>
                <br/>
            </Segment>

            <Segment>
                <TagsProvider>
                    <TagsSelector selectedTagNames={videoFile['tags']} onAdd={localAddTag} onRemove={localRemoveTag}/>
                </TagsProvider>
            </Segment>

            <Tab menu={tabMenu} panes={tabPanes}/>

            <Segment>
                <Grid columns={2} stackable>
                    <Grid.Row>
                        <Grid.Column textAlign='left'>
                            {prevFile && <><Header as='h3'>Older</Header><VideoCard file={prevFile}/></>}
                        </Grid.Column>
                        <Grid.Column textAlign='left'>
                            {nextFile && <><Header as='h3'>Newer</Header><VideoCard file={nextFile}/></>}
                        </Grid.Column>
                    </Grid.Row>
                </Grid>
            </Segment>
        </Container>
    </>
}

export default VideoPage;

const chapterRegex = new RegExp('^(\\(?(?:((\\d?\\d):)?(?:(\\d?\\d):(\\d\\d)))\\)?)\\s+(.*)$', 'i');

function chaptersInDescription(description, setVideoTime) {
    if (description && description.length > 0) {
        try {
            const lines = _.split(description, '\n');
            let newLines = [];
            for (let i = 0; i <= lines.length; i++) {
                const line = lines[i];
                const match = line ? line.match(chapterRegex) : null;
                let link;
                if (match) {
                    // This line in the description starts with a chapter timestamp, parse it and create a link.
                    try {
                        const timestamp = match[1];
                        const title = match[6];
                        // Assume 0 if no part of timestamp could be found.
                        const [hour, minute, second] = match.slice(3, 6).map(i => parseInt(i) || 0);
                        // Convert timestamp to seconds.
                        const seconds = (((hour * 60) + minute) * 60) + second;
                        link = <>
                            <a href='#' onClick={() => setVideoTime(seconds)}>{timestamp}</a>
                            &nbsp;{title}
                        </>;
                    } catch (e) {
                        // Report an error while creating timestamp link.
                        console.error(e);
                    }

                    // Use the link if we could create it, otherwise fallback to the original `line`.
                    newLines = [...newLines, link || line];
                } else if (line !== undefined) {
                    // Line does not start with a timestamp.
                    newLines = [...newLines, line];
                }
            }
            // Map all lines and links with a break between.
            return <>
                {newLines.map((i, idx) => <div key={idx}>{i}<br/></div>)}
            </>;
        } catch (e) {
            // Some error happened while parsing description.  Report it but don't fail.
            console.error(e);
        }
    }
    // Error occurred, or no description, don't fail.
    return description;
}
