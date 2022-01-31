import React, {useState} from 'react';
import Icon from "semantic-ui-react/dist/commonjs/elements/Icon";
import {deleteVideo, favoriteVideo} from "../api";
import Button from "semantic-ui-react/dist/commonjs/elements/Button";
import {Link} from "react-router-dom";
import {humanFileSize, humanNumber, secondsToTimestamp, uploadDate, VideoCard} from "./Common";
import {Confirm, Segment, Tab} from "semantic-ui-react";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import Container from "semantic-ui-react/dist/commonjs/elements/Container";

const MEDIA_PATH = '/media';


function VideoPage(props) {
    let {video, channel} = props;
    let [deleteOpen, setDeleteOpen] = useState(false);

    async function handleDeleteVideo(video_id) {
        try {
            await deleteVideo(video_id)
        } catch (e) {
            setDeleteOpen(false);
            throw e;
        }
        props.history.goBack();
    }

    let videoUrl = `${MEDIA_PATH}/${encodeURIComponent(video.video_path)}`;

    let posterUrl = null;
    if (video.poster_path) {
        posterUrl = `${MEDIA_PATH}/${encodeURIComponent(video.poster_path)}`;
    }
    let captionsUrl = null;
    if (video.caption_path) {
        captionsUrl = `${MEDIA_PATH}/${encodeURIComponent(video.caption_path)}`;
    }

    let description = 'No description available.';
    let viewCount = video.view_count;
    if (video.info_json) {
        description = video.info_json['description'];
        viewCount = viewCount || video.info_json['view_count'];
    }

    let [favorite, setFavorite] = React.useState(video.favorite);
    let handleFavorite = async (e) => {
        e.preventDefault();
        let new_favorite = await favoriteVideo(video.id, !!!favorite);
        setFavorite(new_favorite);
    }
    let favorite_button;
    if (favorite) {
        favorite_button = (
            <Button color='green' style={{'margin': '0.5em'}}
                    onClick={handleFavorite}>
                <Icon name='heart'/>
                Unfavorite
            </Button>
        );
    } else {
        favorite_button = (
            <Button basic color='green' style={{'margin': '0.5em'}}
                    onClick={handleFavorite}>
                <Icon name='heart'/>
                Favorite
            </Button>
        );
    }

    let descriptionPane = {
        menuItem: 'Description', render: () => <Tab.Pane>
            <pre className="wrap-text">
                {description || 'No description'}
            </pre>
        </Tab.Pane>
    };

    let statisticsPane = {
        menuItem: 'Statistics', render: () => <Tab.Pane>
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
        </Tab.Pane>
    }

    let captionsPane = {
        menuItem: 'Captions', render: () => <Tab.Pane>
            <pre>{video.caption}</pre>
        </Tab.Pane>
    };

    let tabPanes = [descriptionPane, statisticsPane, captionsPane];

    return (
        <>
            <Container>
                <Button
                    style={{marginTop: '1em', marginBottom: '1em'}}
                    onClick={() => props.history.goBack()}
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
            >
                <source src={videoUrl} type="video/mp4"/>
                <track kind="captions" label="English captions" src={captionsUrl} srcLang="en" default/>
            </video>

            <Container style={{marginTop: '1em'}}>
                <Segment>

                    <h2>{video.title || video.video_path}</h2>
                    {video.upload_date && <h3>{uploadDate(video.upload_date)}</h3>}
                    <h3>
                        {channel && <Link to={`/videos/channel/${channel.link}/video`}>
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

                <Tab panes={tabPanes}/>

                <Grid columns={2} stackable>
                    <Grid.Row>
                        <Grid.Column textAlign='left'>
                            {props.prev && <><h3>Older</h3><VideoCard video={props.prev}/></>}
                        </Grid.Column>
                        <Grid.Column textAlign='left'>
                            {props.next && <><h3>Newer</h3><VideoCard video={props.next}/></>}
                        </Grid.Column>
                    </Grid.Row>
                </Grid>
            </Container>
        </>
    )
}

export default VideoPage;
