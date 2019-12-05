import React from 'react';
import {Link} from "react-router-dom";
import {Button} from "react-bootstrap";

function Video(props) {
    let params = props.match.params;

    return (
        <>
            <p>
                <Link to={'/videos/' + params.channel_link}>
                    <Button className="btn-primary">
                        <span className="fas fa-chevron-left"></span>
                        Back
                    </Button>
                </Link>
            </p>
        </>
    )
}

export default Video;
