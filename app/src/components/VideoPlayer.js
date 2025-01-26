import React, {useContext} from 'react';
import {deleteVideos, downloadVideoMetadata, tagFileGroup, untagFileGroup} from "../api";
import {Link, useNavigate, useParams} from "react-router-dom";
import _ from "lodash";
import {
    APIButton,
    BackButton,
    encodeMediaPath,
    getParentDirectory,
    humanFileSize,
    humanNumber,
    isoDatetimeToAgoPopup,
    MultilineText,
    PageContainer,
    PreviewPath,
    useTitle
} from "./Common";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import Container from "semantic-ui-react/dist/commonjs/elements/Container";
import {VideoPlaceholder} from "./Placeholder";
import {useChannel, useVideoCaptions, useVideoExtras} from "../hooks/customHooks";
import {ThemeContext} from "../contexts/contexts";
import {Button, darkTheme, Header, Icon, Segment, Tab, TabPane} from "./Theme";
import {VideoCard} from "./Videos";
import {TagsSelector} from "../Tags";
import {Comment, CommentGroup, Label} from "semantic-ui-react";

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

export function CaptionTrack({src, ...props}) {
    if (src.endsWith('.de.vtt')) {
        return <track kind="captions" label="German" src={src} srcLang="de" {...props}/>
    } else if (src.endsWith('.es.vtt')) {
        return <track kind="captions" label="Spanish" src={src} srcLang="es" {...props}/>
    } else if (src.endsWith('.fr.vtt')) {
        return <track kind="captions" label="French" src={src} srcLang="fr" {...props}/>
    } else if (src.endsWith('.id.vtt')) {
        return <track kind="captions" label="Indonesian" src={src} srcLang="id" {...props}/>
    } else if (src.endsWith('.it.vtt')) {
        return <track kind="captions" label="Italian" src={src} srcLang="it" {...props}/>
    } else if (src.endsWith('.ja.vtt')) {
        return <track kind="captions" label="Japanese" src={src} srcLang="ja" {...props}/>
    } else if (src.endsWith('.pl.vtt')) {
        return <track kind="captions" label="Polish" src={src} srcLang="pl" {...props}/>
    } else if (src.endsWith('.pt.vtt')) {
        return <track kind="captions" label="Portuguese" src={src} srcLang="pt" {...props}/>
    } else if (src.endsWith('.ro.vtt')) {
        return <track kind="captions" label="Romanian" src={src} srcLang="ro" {...props}/>
    } else if (src.endsWith('.ru.vtt')) {
        return <track kind="captions" label="Russian" src={src} srcLang="ru" {...props}/>
    } else if (src.endsWith('.th.vtt')) {
        return <track kind="captions" label="Thai" src={src} srcLang="th" {...props}/>
    }
    return <track kind="captions" label="English" src={src} srcLang="en" default {...props}/>
}

const NoComments = ({video}) => {
    const videoUrl = video.url;

    const handleRefresh = async () => {
        const destination = getParentDirectory(video.primary_path);
        await downloadVideoMetadata(videoUrl, destination);
    };

    if (videoUrl) {
        return <React.Fragment>
            <p>No comments have been been downloaded. Refresh the video?</p>

            <APIButton
                color='blue'
                size='large'
                onClick={handleRefresh}
            >Refresh</APIButton>
        </React.Fragment>
    } else {
        return <React.Fragment>
            <p>No comment have been downloaded. WROLPi does not know the URL of this video, so it cannot download
                the comments.</p>

            <big>Try finding and downloading the video again.</big>
        </React.Fragment>
    }
}

const VideoComment = ({comment, children}) => {
    const {t} = React.useContext(ThemeContext);

    const {is_favorited, like_count, author, timestamp, text, author_is_uploader} = comment;

    // Author comments and favorited comments are important.
    let specialIcon = null;
    if (author_is_uploader) {
        specialIcon = <Icon name='star' color='green'/>;
    } else if (is_favorited) {
        specialIcon = <Icon name='heart' color='red'/>;
    }

    const dateElm = <div {...t}>{isoDatetimeToAgoPopup(timestamp * 1000)}</div>;
    const likesElm = like_count && <div {...t}>
        <Icon name='thumbs up'/>{humanNumber(comment['like_count'])}
    </div>;

    return <Comment>
        <Comment.Content>
            <Comment.Author as='a'>
                <span {...t}>{specialIcon}{author}</span>
            </Comment.Author>
            <Comment.Metadata>
                {dateElm}
                {likesElm}
            </Comment.Metadata>
            <Comment.Text {...t}>
                <MultilineText text={text} style={{marginLeft: '0.5em'}}/>
            </Comment.Text>
        </Comment.Content>
        {children && !_.isEmpty(children) &&
            <CommentGroup>
                {children.map((i, key) => <VideoComment key={key} comment={i}/>)}
            </CommentGroup>
        }
    </Comment>
}


const Comments = ({comments, video}) => {
    if (!comments || _.isEmpty(comments)) {
        return <NoComments video={video}/>
    }

    comments.sort((a, b) => {
        // Treat undefined like_count as 0
        const likeA = a.like_count ?? 0;
        const likeB = b.like_count ?? 0;

        // For descending order
        return likeB - likeA;
    });

    const rootComments = comments.filter(i => i['parent'] === 'root');

    // Comments are in an array, convert it to a dict, grouped by their parent.
    const groupedByParent = {};
    comments.forEach(obj => {
        if (!groupedByParent[obj.parent]) {
            groupedByParent[obj.parent] = [];
        }
        groupedByParent[obj.parent].push(obj);
    })
    // Sort replies to each parent by the time they were created.
    comments.forEach(obj => {
        const children = groupedByParent[obj.parent];
        groupedByParent[obj.parent] = _.sortBy(children, ['timestamp']);
    })

    return <CommentGroup>
        {rootComments.map((i, key) => <VideoComment key={key} comment={i} children={groupedByParent[i.id]}/>)}
    </CommentGroup>
}

function VideoPage({videoFile, prevFile, nextFile, fetchVideo, ...props}) {
    const {theme} = useContext(ThemeContext);

    const navigate = useNavigate();
    const videoRef = React.useRef();

    useTitle(videoFile ? videoFile.title ? videoFile.title : videoFile.name : null);
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
    const {comments, captions} = useVideoExtras(videoFile?.video?.id);

    if (videoFile === null) {
        return <VideoPlaceholder/>;
    }
    if (videoFile === undefined) {
        return <PageContainer><Header as='h4'>Could not find video</Header></PageContainer>;
    }

    const handleDeleteVideo = async (video_id) => {
        await deleteVideos([video_id])
        navigate(-1);
    }

    const handleRefresh = async () => {
        const destination = getParentDirectory(videoFile.primary_path);
        await downloadVideoMetadata(videoFile.url, destination);
    };

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
        description = formatVideoDescription(description, setVideoTime)
    }

    const descriptionPane = {
        menuItem: 'Description', render: () => <TabPane>
            <pre className="wrap-text">
                {description}
            </pre>
        </TabPane>
    };

    const captionsPane = {
        menuItem: 'Captions', render: () => <TabPane>
            <pre>{captions || 'No captions available.'}</pre>
        </TabPane>
    };

    const {poster_file, info_json_file} = video;
    const filesPane = {
        menuItem: 'Files', render: () => <TabPane>
            <h3>Video File</h3>
            {videoFileLink(video['video_path'])}

            <h4>Info JSON File</h4>
            {info_json_file &&
                <PreviewPath path={info_json_file['path']} mimetype={info_json_file['mimetype']} taggable={false}>
                    {info_json_file['path']}
                </PreviewPath>
            }

            <h4>Caption Files</h4>
            {caption_files &&
                caption_files.map(i => <p key={i['path']}><PreviewPath {...i} taggable={false}>
                    {i['path']}
                </PreviewPath></p>)
            }

            <h4>Poster File</h4>
            {poster_file &&
                <PreviewPath path={poster_file['path']} mimetype={poster_file['mimetype']} taggable={false}>
                    {poster_file['path']}
                </PreviewPath>
            }

            <h4>Directory</h4>
            {videoFileLink(videoFile['directory'], true)}
        </TabPane>
    }

    const commentsPane = {
        menuItem: 'Comments', render: () => <TabPane>
            <Header as='h3'>Top Comments</Header>
            <Comments comments={comments} video={videoFile}/>
        </TabPane>,
    };

    const tabPanes = [commentsPane, descriptionPane, filesPane, captionsPane];
    const tabMenu = theme === darkTheme ? {inverted: true, attached: true} : {attached: true};

    const aboutSegment = <Segment>
        <Header as='h2'>About Video</Header>

        <Grid columns={2}>
            <Grid.Row>
                <Grid.Column>
                    <h3>Size</h3>
                    <p>{videoFile.size ? humanFileSize(videoFile.size) : 'Unknown'}</p>
                </Grid.Column>
                <Grid.Column>
                    <h3>View Count</h3>
                    <p>{video.view_count ? humanNumber(video.view_count) : 'N/A'}</p>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row>
                <Grid.Column>
                    <h3>Codec Names</h3>
                    <>{video.codec_names ? video.codec_names.map(i => <Label key={i}>{i}</Label>) : 'N/A'}</>
                </Grid.Column>
                <Grid.Column>
                    <h3>Censored</h3>
                    <p>{videoFile.censored ? 'Yes' : 'No'}</p>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={1}>
                <Grid.Column>
                    <h3>Source URL</h3>
                    <p>{videoFile.url ? <a href={videoFile.url}>{videoFile.url}</a> : 'N/A'}</p>
                </Grid.Column>
            </Grid.Row>
        </Grid>
    </Segment>;

    const localAddTag = async (name) => {
        await tagFileGroup(videoFile, name);
        await fetchVideo();
    }

    const localRemoveTag = async (name) => {
        await untagFileGroup(videoFile, name);
        await fetchVideo();
    }

    let videoSource = <source src={videoUrl}/>;

    let prevNextVideosSegment = <Segment><p>No related videos found.</p></Segment>;
    if (prevFile || nextFile) {
        prevNextVideosSegment = <Segment>
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
    }

    let title = video.video_path;
    if (videoFile.title) {
        title = hashtagLinks(videoFile.title);
    } else if (videoFile.stem) {
        title = videoFile.stem;
    }

    return <>
        <Container style={{margin: '1em'}}>
            <BackButton/>
        </Container>

        <video controls
               className='video-player'
               autoPlay={props.autoplay !== undefined ? props.autoplay : true}
               poster={posterUrl}
               id="player"
               playsInline={true}
               style={{maxWidth: '100%'}}
               ref={videoRef}
        >
            {videoSource}
            {/* Only WebVTT captions can be displayed. */}
            {captionUrls.map(i => <CaptionTrack key={i} src={i}/>)}
        </video>

        <Container style={{marginTop: '1em'}}>
            <Segment>

                <Header as='h2'>{title}</Header>
                {videoFile.published_datetime && <h3>{isoDatetimeToAgoPopup(videoFile.published_datetime)}</h3>}
                <h3>
                    {channel && <Link to={`/videos/channel/${channel.id}/video`}>
                        {channel.name}
                    </Link>}
                </h3>

                <p>
                    <Button as='a' href={downloadUrl}>
                        <Icon name='download'/>
                        Download
                    </Button>
                    <APIButton
                        color='red'
                        confirmContent='Are you sure you want to delete this video?  All files related to this video will be deleted. It will not be downloaded again!'
                        confirmButton='Delete'
                        onClick={async () => await handleDeleteVideo(video.id)}
                        obeyWROLMode={true}
                    >Delete</APIButton>
                    <APIButton
                        color='blue'
                        onClick={handleRefresh}
                        obeyWROLMode={true}
                        disabled={!videoFile.url}
                    >Refresh</APIButton>
                </p>
            </Segment>

            <Segment>
                <TagsSelector selectedTagNames={videoFile['tags']} onAdd={localAddTag} onRemove={localRemoveTag}/>
            </Segment>

            {aboutSegment}

            <Tab menu={tabMenu} panes={tabPanes}/>

            {prevNextVideosSegment}
        </Container>
    </>
}

export default VideoPage;

const chapterRegex = new RegExp('^(\\(?(?:((\\d?\\d):)?(?:(\\d?\\d):(\\d\\d)))\\)?)\.?\\s+(.*)$', 'i');

function formatVideoDescription(description, setVideoTime) {
    // Convert timestamps to links which change the video's playback location.  Change hashtags to search links.
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
                    newLines = [...newLines, link || hashtagLinks(line)];
                } else if (line !== undefined) {
                    // Line does not start with a timestamp.
                    newLines = [...newLines, hashtagLinks(line)];
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

const hashtagRegex = /(#+[_a-zA-Z0-9]+)/ig;


function hashtagLinks(text) {
    // Converts a string into a div which has hashtags converted to search links.
    // Example: Some text <a href="/search?q=#hashtag">#hashtag</a> the rest of the text
    if (text && text.length > 0) {
        const parts = text.split(hashtagRegex);
        let newParts = '';
        for (let i = 0; i < parts.length; i++) {
            let part = parts[i];
            part = part.startsWith('#') ?
                // Part is a hashtag.
                <a key={i} href={`/search?q=${encodeURIComponent(part)}`} target="_self">{part}</a>
                // Part is not a hashtag.
                : <span key={i}>{part}</span>;
            newParts = [...newParts, part];
        }
        return <React.Fragment>{newParts}</React.Fragment>;
    }
    return text;
}
