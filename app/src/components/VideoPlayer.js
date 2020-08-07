import React from 'react';
import Icon from "semantic-ui-react/dist/commonjs/elements/Icon";
import {favoriteVideo} from "../api";
import Button from "semantic-ui-react/dist/commonjs/elements/Button";
import {Link} from "react-router-dom";
import {uploadDate, VideoCard} from "./Common";
import {Container} from "semantic-ui-react";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";

const MEDIA_PATH = '/media';


function Video(props) {
    let video = props.video;
    let channel = video.channel;

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
            <Button color='red' style={{'margin': '0.5em'}}
                    onClick={handleFavorite}>
                <Icon name='heart'/>
                Unfavorite
            </Button>
        );
    } else {
        favorite_button = (
            <Button style={{'margin': '0.5em'}}
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
                <a href={videoUrl}>
                    <Button>
                        <Icon name='download'/>
                        Download
                    </Button>
                </a>
                {favorite_button}
            </p>

            <h4>Description</h4>
            <pre className="wrap-text">
                {description}
            </pre>

            <Grid columns={2}>
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
