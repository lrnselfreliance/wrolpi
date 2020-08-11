import React from "react";
import {Card, Container, Image, Pagination} from 'semantic-ui-react';
import {Link} from "react-router-dom";

export const API_URI = process.env.REACT_APP_API ? process.env.REACT_APP_API : '127.0.0.1:8080';
export const VIDEOS_API = `http://${API_URI}/api/videos`;
export const DEFAULT_LIMIT = 20;

export default class Paginator extends React.Component {
    state = {
        boundaryRange: 1,
        siblingRange: 2,
        showEllipsis: true,
        showFirstAndLastNav: false,
        showPreviousAndNextNav: true,
    }

    handlePaginationChange = (e, {activePage}) => {
        this.props.changePage(activePage);
    }

    render() {
        const {
            boundaryRange,
            siblingRange,
            showEllipsis,
            showFirstAndLastNav,
            showPreviousAndNextNav,
        } = this.state;

        return (
            <Pagination
                activePage={this.props.activePage}
                boundaryRange={boundaryRange}
                onPageChange={this.handlePaginationChange}
                size='mini'
                siblingRange={siblingRange}
                totalPages={this.props.totalPages}
                // Heads up! All items are powered by shorthands, if you want to hide one of them, just pass `null` as value
                ellipsisItem={showEllipsis ? undefined : null}
                firstItem={showFirstAndLastNav ? undefined : null}
                lastItem={showFirstAndLastNav ? undefined : null}
                prevItem={showPreviousAndNextNav ? undefined : null}
                nextItem={showPreviousAndNextNav ? undefined : null}
            />

        )
    }
}

export function Duration({video}) {
    let duration = video.duration;
    let hours = Math.floor(duration / 3600);
    duration -= hours * 3600;
    let minutes = Math.floor(duration / 60);
    let seconds = duration - (minutes * 60);

    hours = String('00' + hours).slice(-2);
    minutes = String('00' + minutes).slice(-2);
    seconds = String('00' + seconds).slice(-2);

    if (hours > 0) {
        return <div className="duration-overlay">{hours}:{minutes}:{seconds}</div>
    } else if (duration) {
        return <div className="duration-overlay">{minutes}:{seconds}</div>
    } else {
        return <></>
    }
}

export function uploadDate(d) {
    // Convert a date integer to a human readable date format.
    let upload_date = <></>;
    if (d) {
        upload_date = new Date(d * 1000);
        upload_date = `${upload_date.getFullYear()}-${upload_date.getMonth() + 1}-${upload_date.getDate()}`;
    }
    return upload_date;
}

export function VideoCard({video}) {
    let channel = video.channel;
    let channel_url = `/videos/channel/${channel.link}/video`;

    let upload_date = uploadDate(video.upload_date);
    let video_url = `/videos/channel/${channel.link}/video/${video.id}`;
    let poster_url = video.poster_path ? `/media/${channel.directory}/${encodeURIComponent(video.poster_path)}` : null;

    return (
        <Card style={{'width': '18em', 'margin': '1em'}}>
            <Link to={video_url}>
                <Image src={poster_url} wrapped style={{position: 'relative', width: '100%'}}/>
            </Link>
            <Duration video={video}/>
            <Card.Content>
                <Card.Header>
                    <Container textAlign='left'>
                        <Link to={video_url} className="no-link-underscore video-card-link">
                            <p>{video.title || video.video_path}</p>
                        </Link>
                    </Container>
                </Card.Header>
                <Card.Description>
                    <Container textAlign='left'>
                        <Link to={channel_url} className="no-link-underscore video-card-link">
                            <b>{channel.name}</b>
                        </Link>
                        <p>{upload_date}</p>
                    </Container>
                </Card.Description>
            </Card.Content>
        </Card>
    )
}

export class VideoCards extends React.Component {

    render() {
        return (
            <Card.Group>
                {this.props.videos.map((v) => {
                    return <VideoCard key={v['id']} video={v}/>
                })}
            </Card.Group>
        )
    }
}

export function RequiredAsterisk() {
    return <span style={{color: '#db2828'}}> *</span>
}

export let defaultSearchOrder = '-upload_date';
export let searchSearchOrder = 'rank';

export let videoOrders = [
    {key: '-upload_date', value: '-upload_date', text: 'Newest'},
    {key: 'upload_date', value: 'upload_date', text: 'Oldest'},
    {key: '-duration', value: '-duration', text: 'Longest'},
    {key: 'duration', value: 'duration', text: 'Shortest'},
    {key: '-viewed', value: '-viewed', text: 'Recently viewed'},
    {key: '-size', value: '-size', text: 'Largest'},
    {key: 'size', value: 'size', text: 'Smallest'},
];

export let searchOrders = [
    {key: 'rank', value: 'rank', text: 'Search Rank'},
];

const secondsToYears = 31536000;
const secondsToDays = 86400;
const secondsToHours = 3600;
const secondsToMinutes = 60;


export function secondsToString(seconds) {
    let s = '';

    let numYears = Math.floor(seconds / secondsToYears);
    if (numYears) {
        s = `${numYears} years`;
        seconds -= numYears * secondsToYears;
    }
    let numDays = Math.floor(seconds / secondsToDays);
    if (numDays) {
        s = `${s} ${numDays} days`;
        seconds -= numDays * secondsToDays;
    }
    let numHours = Math.floor(seconds / secondsToHours);
    if (numHours) {
        s = `${s} ${numHours} hours`;
        seconds -= numHours * secondsToHours;
    }
    let numMinutes = Math.floor(seconds / secondsToMinutes);
    if (numMinutes) {
        s = `${s} ${numMinutes} minutes`;
    }
    return s;
}

export function humanFileSize(bytes, si = false, dp = 1) {
    const thresh = si ? 1000 : 1024;

    if (Math.abs(bytes) < thresh) {
        return bytes + ' B';
    }

    const units = si
        ? ['kB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
        : ['KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB'];
    let u = -1;
    const r = 10 ** dp;

    do {
        bytes /= thresh;
        ++u;
    } while (Math.round(Math.abs(bytes) * r) / r >= thresh && u < units.length - 1);


    return bytes.toFixed(dp) + ' ' + units[u];
}
