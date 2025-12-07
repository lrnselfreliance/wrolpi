import {Placeholder, Segment} from "./Theme";
import {Image, PlaceholderLine} from "semantic-ui-react";
import React from "react";
import {ThemeContext} from "../contexts/contexts";
import {encodeMediaPath, FileIcon, findPosterPath, PreviewLink} from "./Common";
import {Link} from "react-router";
import _ from "lodash";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {FileRowTagIcon} from "./Files";

export const HeadlineText = ({headline, openTag = '<u>', closeTag = '</u>'}) => {
    const {s} = React.useContext(ThemeContext);
    if (headline) {
        headline = headline.replaceAll('<b>', openTag);
        headline = headline.replaceAll('</b>', closeTag);
        headline = headline.replaceAll('\n', '<br/>');
        // Postgres inserts <b>...</b> tags which we will use.
        return <span {...s} dangerouslySetInnerHTML={{__html: headline}}></span>
    }
}

const FileHeadline = ({file, to}) => {
    const {title, name, title_headline, b_headline, c_headline, d_headline} = file;

    let poster;
    const posterPath = findPosterPath(file);
    if (posterPath) {
        const posterUrl = posterPath ? `/media/${encodeMediaPath(posterPath)}` : null;
        poster = <Image src={posterUrl} size='tiny'/>;
    } else {
        poster = <FileIcon file={file}/>;
    }

    let header = title || name;
    if (title_headline) {
        header = <PreviewLink file={file}><HeadlineText headline={title_headline}/></PreviewLink>;
    }
    if (to) {
        header = <Link to={to}><HeadlineText headline={title_headline}/></Link>
    }

    let body = <p><small>No highlights available.</small></p>;
    if (b_headline || c_headline || d_headline) {
        body = <>
            <HeadlineText headline={b_headline}/>
            <HeadlineText headline={c_headline}/>
            <HeadlineText headline={d_headline}/>
        </>;
    }

    return <Segment>
        <Grid>
            <Grid.Row>
                <Grid.Column mobile={4} computer={2}>{poster}</Grid.Column>
                <Grid.Column mobile={12} computer={12}>
                    <big>
                        <FileRowTagIcon file={file}/>
                        {header}
                    </big>
                </Grid.Column>
            </Grid.Row>
        </Grid>
        <br/>
        {body}
    </Segment>
}

export const Headlines = ({results}) => {
    if (results === null || results === undefined) {
        return <Placeholder>
            <PlaceholderLine/>
            <PlaceholderLine/>
            <PlaceholderLine/>
        </Placeholder>
    } else if (results && results.length === 0) {
        return <Segment>No results!</Segment>
    }

    let headlines = [];
    for (let i = 0; i < results.length; i++) {
        const result = results[i];
        const {model, data, video} = result;

        if (model === 'video' && !_.isEmpty(video)) {
            const {channel} = video;
            const video_url = channel
                ? `/videos/channel/${channel.id}/video/${video.id}`
                : `/videos/video/${video.id}`;
            headlines = [...headlines, <FileHeadline key={result['key']} file={result} to={video_url}/>];
        } else if (model === 'archive' && !_.isEmpty(data)) {
            headlines = [...headlines, <FileHeadline key={result['key']} file={result} to={`/archive/${data.id}`}/>];
        } else {
            headlines = [...headlines, <FileHeadline key={result['key']} file={result}/>];
        }
    }
    return <>
        {headlines}
    </>
}