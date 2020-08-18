import React from "react";
import {Card, Container, Image, Pagination} from 'semantic-ui-react';
import {Link} from "react-router-dom";
import LazyLoad from 'react-lazy-load';

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
            <Link to={video_url} offset={250}>
                <LazyLoad>
                    <Image src={poster_url} wrapped style={{position: 'relative', width: '100%'}}/>
                </LazyLoad>
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

export let defaultVideoOrder = '-upload_date';
export let defaultSearchOrder = 'rank';

export let videoOrders = [
    {key: '-upload_date', value: '-upload_date', text: 'Newest', title: 'Newest Videos'},
    {key: 'upload_date', value: 'upload_date', text: 'Oldest', title: 'Oldest Videos'},
    {key: '-duration', value: '-duration', text: 'Longest', title: 'Longest Videos'},
    {key: 'duration', value: 'duration', text: 'Shortest', title: 'Shortest Videos'},
    {key: '-viewed', value: '-viewed', text: 'Recently viewed', title: 'Recently Viewed Videos'},
    {key: '-size', value: '-size', text: 'Largest', title: 'Largest Videos'},
    {key: 'size', value: 'size', text: 'Smallest', title: 'Smallest Videos'},
];

export let searchOrders = [
    {key: 'rank', value: 'rank', text: 'Search Rank', title: 'Search Results'},
];

const secondsToYears = 31536000;
const secondsToDays = 86400;
const secondsToHours = 3600;
const secondsToMinutes = 60;

export const frequencyOptions = [
    {key: 'daily', text: 'Daily', value: 86400},
    {key: 'weekly', text: 'Weekly', value: 604800},
    {key: 'monthly', text: 'Monthly', value: 2592000},
    {key: 'yearly', text: 'Yearly', value: 31536000},
];

export function secondsToFrequency(seconds) {
    for (let i=0; i < Object.keys(frequencyOptions).length; i++) {
        let d = frequencyOptions[i];
        if (d.value === seconds) {
            return d.text;
        }
    }
    return null;
}

export function secondsToString(seconds) {
    let s = '';

    let numYears = Math.floor(seconds / secondsToYears);
    if (numYears) {
        s = `${numYears}Y`;
        seconds -= numYears * secondsToYears;
    }
    let numDays = Math.floor(seconds / secondsToDays);
    if (numDays) {
        s = `${s} ${numDays}D`;
        seconds -= numDays * secondsToDays;
    }
    let numHours = Math.floor(seconds / secondsToHours);
    if (numHours) {
        seconds -= numHours * secondsToHours;
    }
    let numMinutes = Math.floor(seconds / secondsToMinutes);
    s = `${s} ${numHours}:${numMinutes}H`;
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

export class APIForm extends React.Component {

    constructor(props) {
        super(props);

        this.state = {
            dirty: false,
            disabled: false,
            error: false,
            loading: false,
            message_content: '',
            message_header: '',
            success: false,
        }
    }

    setError = (header, content) => {
        this.setState({
            error: true,
            message_content: content,
            message_header: header,
            success: false,
        });
    }

    setSuccess = (header, content) => {
        this.setState({
            error: false,
            message_content: content,
            message_header: header,
            success: true,
        });
    }

    initFormValues = (original) => {
        // Set the "original" values in state to the provided values.  This will be used to compare against any form
        // changes.
        let inputs = {};
        let inputKeys = Object.keys(this.state.inputs);
        for (let i = 0; i < inputKeys.length; i++) {
            let key = inputKeys[i];
            inputs[key] = original[key];
        }

        this.setState({original: {...original}, inputs: inputs});
    }

    isDirty = () => {
        // Compare dictionaries "inputs" and "original".  "original" should never change once it is set.
        let inputKeys = Object.keys(this.state.inputs);
        for (let i = 0; i < inputKeys.length; i++) {
            let name = inputKeys[i];
            if (!this.state.original && this.state.inputs[name]) {
                // Form has changed from it's empty value.
                return true;
            } else if (this.state.original && this.state.original[name] !== this.state.inputs[name]) {
                // Form has changed from it's initial value.
                return true;
            }
        }
        return false;
    }

    checkDirty = () => {
        this.setState({dirty: this.isDirty()})
    }

    setLoading = () => {
        this.setState({
            disabled: true,
            error: false,
            loading: true,
            success: false,
        })
    }

    clearLoading = () => {
        this.setState({
            disabled: false,
            loading: false,
        })
    }

    handleInputChange = async (event, {name, value}) => {
        let inputs = this.state.inputs;
        inputs[name] = value;
        this.setState({inputs: inputs}, this.checkDirty);
    }

    handleCheckbox = async (checkbox) => {
        let checked = checkbox.current.state.checked;
        let name = checkbox.current.props.name;

        let inputs = this.state.inputs;
        inputs[name] = !checked;

        this.setState({inputs: inputs}, this.checkDirty);
    }

}