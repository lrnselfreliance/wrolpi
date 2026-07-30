import {Grid, Panel, Placeholder} from "./ui";
import React from "react";
import {encodeMediaPath, FileIcon, findPosterPath, PreviewLink} from "./Common";
import {Link} from "react-router";
import _ from "lodash";
import {FileRowTagIcon} from "./Files";

export const HeadlineText = ({headline, openTag = '<u>', closeTag = '</u>'}) => {
    if (headline) {
        headline = headline.replaceAll('<b>', openTag);
        headline = headline.replaceAll('</b>', closeTag);
        headline = headline.replaceAll('\n', '<br/>');
        // FTS headlines use <b>...</b> tags which we will restyle.
        return <span dangerouslySetInnerHTML={{__html: headline}}></span>
    }
}

const FileHeadline = ({file, to}) => {
    const {title, name, title_headline, b_headline, c_headline, d_headline} = file;

    let poster;
    const posterPath = findPosterPath(file);
    if (posterPath) {
        const posterUrl = posterPath ? `/media/${encodeMediaPath(posterPath)}` : null;
        poster = <img alt='poster' src={posterUrl} style={{maxWidth: '80px', maxHeight: '80px'}}/>;
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

    return <Panel>
        <Grid>
            <Grid.Col span={{base: 4, sm: 2}}>{poster}</Grid.Col>
            <Grid.Col span={{base: 12, sm: 10}}>
                <big>
                    <FileRowTagIcon file={file}/>
                    {header}
                </big>
            </Grid.Col>
        </Grid>
        <br/>
        {body}
    </Panel>
}

export const Headlines = ({results}) => {
    if (results === null || results === undefined) {
        return <Placeholder lines={3}/>
    } else if (results && results.length === 0) {
        return <Panel>No results!</Panel>
    }

    let headlines = [];
    for (let i = 0; i < results.length; i++) {
        const result = results[i];
        const {model, data, video} = result;

        if (model === 'video' && !_.isEmpty(video)) {
            const video_url = `/videos/${result.id}`;
            headlines = [...headlines, <FileHeadline key={result['key']} file={result} to={video_url}/>];
        } else if (model === 'archive' && !_.isEmpty(data)) {
            headlines = [...headlines, <FileHeadline key={result['key']} file={result} to={`/archives/${result.id}`}/>];
        } else {
            headlines = [...headlines, <FileHeadline key={result['key']} file={result}/>];
        }
    }
    return <>
        {headlines}
    </>
}
