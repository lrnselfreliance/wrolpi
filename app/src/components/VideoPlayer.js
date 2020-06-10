import React from 'react';
import Icon from "semantic-ui-react/dist/commonjs/elements/Icon";
import {favoriteVideo} from "../api";
import Button from "semantic-ui-react/dist/commonjs/elements/Button";

const MEDIA_PATH = '/media';


function Video(props) {
    let video = props.video;
    let channel = video.channel;

    let poster_url = `${MEDIA_PATH}/${channel.directory}/${encodeURIComponent(video.poster_path)}`;
    let video_url = `${MEDIA_PATH}/${channel.directory}/${encodeURIComponent(video.video_path)}`;
    let captions_url = `${MEDIA_PATH}/${channel.directory}/${encodeURIComponent(video.caption_path)}`;

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
            <Button color='ui red' style={{'margin': '0.5em'}}
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
        <>
            <video controls
                   autoPlay={props.autoplay !== undefined ? props.autoplay : true}
                   poster={poster_url}
                   id="player"
                   playsInline={true}
                   style={{'maxWidth': '100%'}}
            >
                <source src={video_url} type="video/mp4"/>
                <track kind="captions" label="English captions" src={captions_url} srcLang="en" default/>
            </video>

            <p>
                <a href={video_url}>
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
        </>
    )
}

export default Video;
