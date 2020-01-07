import React from 'react';
import Button from "react-bootstrap/Button";
import {VIDEOS_API} from "./Common";

const MEDIA_PATH = '/media';

function Video(props) {
    let video_hash = props.video.video_path_hash;

    let poster_url = MEDIA_PATH + props.video.poster_path;
    let video_url = VIDEOS_API + '/static/video/' + video_hash;
    let captions_url = VIDEOS_API + '/static/caption/' + video_hash;

    let video_download_url = video_url + '?download=true';

    let description = 'No description available.';
    if (props.video.info_json) {
        let info_json = JSON.parse(props.video.info_json);
        description = info_json['description'];
    }

    return (
        <>
            <video poster={poster_url} id="player" playsInline={true} controls style={{'maxWidth': '100%'}}>
                <source src={video_url} type="video/mp4"/>
                <track kind="captions" label="English captions" src={captions_url} srcLang="en" default/>
            </video>

            <p>
                <a href={video_download_url}>
                    <Button>Download</Button>
                </a>
            </p>

            <h4>Description</h4>
            <pre>
                {description}
            </pre>
        </>
    )
}

export default Video;
