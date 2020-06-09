import React from 'react';
import Button from "react-bootstrap/Button";
import Icon from "semantic-ui-react/dist/commonjs/elements/Icon";
import {favoriteVideo} from "../api";

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
                <Button color='ui red' style={{'margin': '0.5em'}}
                        onClick={(e) => favoriteVideo(e, video.id, !!!video.favorite)}>
                    <Icon name='heart'/>
                    Favorite
                </Button>
            </p>

            <h4>Description</h4>
            <pre className="wrap-text">
                {description}
            </pre>
        </>
    )
}

export default Video;
