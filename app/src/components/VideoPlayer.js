import React from 'react';
import Button from "react-bootstrap/Button";

const MEDIA_PATH = '/media';

function Video(props) {
    let poster_url = `${MEDIA_PATH}/${props.channel.directory}/${encodeURIComponent(props.video.poster_path)}`;
    let video_url = `${MEDIA_PATH}/${props.channel.directory}/${encodeURIComponent(props.video.video_path)}`;
    let captions_url = `${MEDIA_PATH}/${props.channel.directory}/${encodeURIComponent(props.video.caption_path)}`;

    let description = 'No description available.';
    if (props.video.info_json) {
        description = props.video.info_json['description'];
    }

    return (
        <>
            <video poster={poster_url} id="player" playsInline={true} controls style={{'maxWidth': '100%'}}>
                <source src={video_url} type="video/mp4"/>
                <track kind="captions" label="English captions" src={captions_url} srcLang="en" default/>
            </video>

            <p>
                <a href={video_url}>
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
