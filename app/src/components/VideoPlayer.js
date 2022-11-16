import React, {useContext, useState} from 'react';
import {deleteVideos} from "../api";
import {Link, useNavigate, useParams} from "react-router-dom";
import _ from "lodash";
import {API_URI, humanFileSize, humanNumber, PageContainer, secondsToTimestamp, uploadDate, useTitle} from "./Common";
import {Confirm} from "semantic-ui-react";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import Container from "semantic-ui-react/dist/commonjs/elements/Container";
import {VideoPlaceholder} from "./Placeholder";
import {useChannel} from "../hooks/customHooks";
import {ThemeContext} from "../contexts/contexts";
import {Button, darkTheme, Header, Icon, Segment, Tab, TabPane} from "./Theme";
import {VideoCard} from "./Videos";

const MEDIA_PATH = '/media';


function VideoPage({videoFile, prevFile, nextFile, setFavorite, ...props}) {
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

    let videoUrl = `${MEDIA_PATH}/${encodeURIComponent(video.video_path)}`;

    let posterUrl = video.poster_path ? `${MEDIA_PATH}/${encodeURIComponent(video.poster_path)}` : null;
    let captionsUrl = video.caption_path ? `${MEDIA_PATH}/${encodeURIComponent(video.caption_path)}` : null;

    let description = 'No description available.';
    let viewCount = video.view_count;
    if (video.info_json) {
        description = video.info_json['description'];
        viewCount = viewCount || video.info_json['view_count'];
    }

    const favorite = video && video.favorite;
    let handleFavorite = async (e) => {
        e.preventDefault();
        if (video) {
            setFavorite(!favorite);
        }
    }
    const favorite_button = (<Button
        color='green'
        style={{'margin': '0.5em'}}
        onClick={handleFavorite}
    >
        <Icon name='heart'/>
        {favorite ? 'Unfavorite' : 'Favorite'}
    </Button>);

    let descriptionPane = {
        menuItem: 'Description', render: () => <TabPane>
            <pre className="wrap-text">
                {description ? chaptersInDescription(description, setVideoTime) : 'No description'}
            </pre>
        </TabPane>
    };

    let aboutPane = {
        menuItem: 'About', render: () => <TabPane>
            <h3>Size</h3>
            <p>{video.size ? humanFileSize(video.size) : '???'}</p>

            <h3>Source URL</h3>
            <p>{video.url ? <a href={video.url}>{video.url}</a> : 'N/A'}</p>

            <h3>View Count</h3>
            <p>{viewCount ? humanNumber(viewCount) : 'N/A'}</p>

            <h3>Censored</h3>
            <p>{video.censored ? 'Yes' : 'No'}</p>

            <h3>File Name</h3>
            <pre style={{backgroundColor: '#ccc', padding: '0.4em'}}>{video.video_path}</pre>

            <h3>File Modification Time</h3>
            <p>{video.modification_datetime ? secondsToTimestamp(video.modification_datetime) : null}</p>
        </TabPane>
    }

    let captionsPane = {
        menuItem: 'Captions', render: () => <TabPane>
            <pre>{video.caption}</pre>
        </TabPane>
    };

    let tabPanes = [descriptionPane, aboutPane, captionsPane];
    const tabMenu = theme === darkTheme ? {inverted: true, attached: true} : {attached: true};

    return (<>
        <Container>
            <Button
                style={{marginTop: '1em', marginBottom: '1em'}}
                onClick={() => navigate(-1)}
            >
                <Icon name='left arrow'/>
                Back
            </Button>
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
            <track kind="captions" label="English captions" src={captionsUrl} srcLang="en" default/>
        </video>

        <Container style={{marginTop: '1em'}}>
            <Segment>

                <Header as='h2'>{video.title || video.video_path}</Header>
                {video.upload_date && <h3>{uploadDate(video.upload_date)}</h3>}
                <h3>
                    {channel && <Link to={`/videos/channel/${channel.id}/video`}>
                        {channel.name}
                    </Link>}
                </h3>

                <p>
                    {favorite_button}
                    <a href={videoUrl}>
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
            </Segment>

            <Tab menu={tabMenu} panes={tabPanes}/>

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
        </Container>
    </>)
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
