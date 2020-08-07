import React, {useState} from 'react';
import Icon from "semantic-ui-react/dist/commonjs/elements/Icon";
import {deleteVideo, favoriteVideo} from "../api";
import Button from "semantic-ui-react/dist/commonjs/elements/Button";
import {Link} from "react-router-dom";
import {uploadDate, VideoCard} from "./Common";
import {Confirm, Container, Segment} from "semantic-ui-react";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";

const MEDIA_PATH = '/media';


function Video(props) {
    let video = props.video;
    let channel = video.channel;
    let [deleteOpen, setDeleteOpen] = useState(false);

    async function handleDeleteVideo(video_id) {
        await deleteVideo(video_id)
        props.history.goBack();
    }

    let videoUrl = `${MEDIA_PATH}/${channel.directory}/${encodeURIComponent(video.video_path)}`;

    let posterUrl = null;
    if (video.poster_path) {
        posterUrl = `${MEDIA_PATH}/${channel.directory}/${encodeURIComponent(video.poster_path)}`;
    }
    let captionsUrl = null;
    if (video.caption_path) {
        captionsUrl = `${MEDIA_PATH}/${channel.directory}/${encodeURIComponent(video.caption_path)}`;
    }

    let description = 'No description available.';
    if (video.info_json) {
        description = video.info_json['description'];
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

    return (
        <Container textAlign='left' style={{marginTop: '2em'}}>
            <Button
                style={{marginTop: '1em', marginBottom: '1em'}}
                onClick={() => props.history.goBack()}
            >
                <Icon name='left arrow'/>
                Back
            </Button>
            <Segment>
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

                <h2>{video.title}</h2>
                {video.upload_date && <h3>{uploadDate(video.upload_date)}</h3>}
                <h3>
                    <Link to={`/videos/channel/${channel.link}/video`}>
                        {channel.name}
                    </Link>
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

            <Segment secondary>
                <h3>Description</h3>
                <pre className="wrap-text">
                {description}
            </pre>
            </Segment>

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
    )
}

export default Video;
