import React, {useEffect, useState} from "react";
import {
    Card,
    Checkbox,
    Container,
    Form,
    Header,
    Icon,
    Image,
    Input,
    Menu,
    Pagination,
    Popup,
    Responsive
} from 'semantic-ui-react';
import {Link, NavLink} from "react-router-dom";
import Button from "semantic-ui-react/dist/commonjs/elements/Button";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import {getSettings} from "../api";
import {useDownloaders, useHotspot, useThrottle} from "../hooks/customHooks";

export const API_URI = `http://${window.location.host}/api`;
export const VIDEOS_API = `${API_URI}/videos`;
export const ARCHIVES_API = `${API_URI}/archive`;
export const OTP_API = `${API_URI}/otp`;
export const DEFAULT_LIMIT = 20;

export default class OldPaginator extends React.Component {
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

export function Paginator({activePage, onPageChange, totalPages, showFirstAndLast}) {
    const handlePageChange = (e, {activePage}) => {
        onPageChange(activePage);
    }

    return (
        <Pagination
            activePage={activePage}
            boundaryRange={1}
            onPageChange={handlePageChange}
            size='mini'
            siblingRange={2}
            totalPages={totalPages}
            firstItem={showFirstAndLast ? undefined : null}
            lastItem={showFirstAndLast ? undefined : null}
        />
    )
}

export function secondsToDuration(video) {
    let duration = video.duration;
    let hours = Math.floor(duration / 3600);
    duration -= hours * 3600;
    let minutes = Math.floor(duration / 60);
    let seconds = duration - (minutes * 60);

    hours = String('00' + hours).slice(-2);
    minutes = String('00' + minutes).slice(-2);
    seconds = String('00' + seconds).slice(-2);

    return [hours, minutes, seconds];
}

export function Duration({video}) {
    let [hours, minutes, seconds] = secondsToDuration(video);

    if (hours > 0) {
        return <div className="duration-overlay">{hours}:{minutes}:{seconds}</div>
    } else if (video.duration) {
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

export function secondsToDateTime(seconds) {
    var t = new Date(1970, 0, 1); // Epoch
    t.setSeconds(seconds);
    return t;
}

export function VideoCard({video}) {
    let video_url = `/videos/video/${video.id}`;
    let upload_date = uploadDate(video.upload_date);
    // A video may not have a channel.
    let channel = video.channel ? video.channel : null;
    let channel_url = null;
    if (channel) {
        channel_url = `/videos/channel/${channel.id}/video`;
        video_url = `/videos/channel/${channel.id}/video/${video.id}`;
    }
    let poster_url = video.poster_path ? `/media/${encodeURIComponent(video.poster_path)}` : null;

    let imageLabel = null;
    if (video.favorite) {
        imageLabel = {corner: 'left', icon: 'heart', color: 'green'};
    }

    return (
        <Card>
            <Link to={video_url}>
                <Image wrapped
                       src={poster_url}
                       label={imageLabel}
                       style={{position: 'relative', width: '100%'}}
                />
            </Link>
            <Duration video={video}/>
            <Card.Content>
                <Card.Header>
                    <Container textAlign='left'>
                        <Link to={video_url} className="no-link-underscore card-link">
                            <p>{textEllipsis(video.title || video.stem || video.video_path, 100)}</p>
                        </Link>
                    </Container>
                </Card.Header>
                <Card.Description>
                    <Container textAlign='left'>
                        {channel &&
                            <Link to={channel_url} className="no-link-underscore card-link">
                                <b>{channel.name}</b>
                            </Link>}
                        <p>{upload_date}</p>
                    </Container>
                </Card.Description>
            </Card.Content>
        </Card>
    )
}

export function VideoCards({videos}) {
    return (
        <CardGroupCentered>
            {videos.map((v) => {
                return <VideoCard key={v['id']} video={v}/>
            })}
        </CardGroupCentered>
    )
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
    {key: '-view_count', value: '-view_count', text: 'Most Views', title: 'Most Views'},
    {key: 'view_count', value: 'view_count', text: 'Least Views', title: 'Least Views'},
    {key: '-modification_datetime', value: '-modification_datetime', text: 'Newest File', title: 'Newest File'},
    {key: 'modification_datetime', value: 'modification_datetime', text: 'Oldest File', title: 'Oldest File'},
]

export let searchOrders = [
    {key: 'rank', value: 'rank', text: 'Search Rank', title: 'Search Results'},
];

export const frequencyOptions = [
    {key: 'daily', text: 'Daily', value: 86400},
    {key: 'weekly', text: 'Weekly', value: 604800},
    {key: 'biweekly', text: 'Biweekly', value: 1209600},
    {key: '30days', text: '30 Days', value: 2592000},
    {key: '90days', text: '90 Days', value: 7776000},
];

export function secondsToFrequency(seconds) {
    for (let i = 0; i < Object.keys(frequencyOptions).length; i++) {
        let d = frequencyOptions[i];
        if (d.value === seconds) {
            return d.text;
        }
    }
    return null;
}

const secondsToYears = 31536000;
const secondsToDays = 86400;
const secondsToHours = 3600;
const secondsToMinutes = 60;

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

export function secondsToDate(seconds) {
    let date = new Date(seconds * 1000);
    return `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`;
}

export function secondsToTimestamp(seconds) {
    let d = new Date(seconds * 1000);
    return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()} ${d.getHours()}:${d.getMinutes()}:${d.getSeconds()}`;
}

export function humanFileSize(bytes, si = false, dp = 1) {
    const thresh = 1024;

    if (Math.abs(bytes) < thresh) {
        return bytes + ' B';
    }

    const units = ['kB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
    let u = -1;
    const r = 10 ** dp;

    do {
        bytes /= thresh;
        ++u;
    } while (Math.round(Math.abs(bytes) * r) / r >= thresh && u < units.length - 1);


    return bytes.toFixed(dp) + ' ' + units[u];
}

export function humanNumber(num, dp = 1) {
    // Convert large numbers to a more human readable format.
    // >> humanNumber(1000)
    // 1.0k
    // >> humanNumber(1500000)
    // 1.5m
    const divisor = 1000;
    if (Math.abs(num) < divisor) {
        return num;
    }
    const units = ['k', 'm', 'b'];
    let i = -1;
    const r = 10 ** dp;
    do {
        num /= divisor;
        ++i;
    } while (Math.round(Math.abs(num) * r) / r >= divisor && i < units.length - 1);

    return num.toFixed(dp) + units[i];
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

    setError = (header, content, errorName) => {
        let errors = {...this.state.errors};
        if (errorName) {
            errors[errorName] = true;
        }
        this.setState({
            error: true,
            errors: errors,
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
        let errors = {};
        let inputKeys = Object.keys(this.state.inputs);
        for (let i = 0; i < inputKeys.length; i++) {
            let key = inputKeys[i];
            inputs[key] = original[key] || '';
            errors[key] = false;
        }

        this.setState({original: {...original}, inputs: inputs, errors: errors});
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

    getEmptyErrors = () => {
        let errors = {};
        let inputKeys = Object.keys(this.state.inputs);
        for (let i = 0; i < inputKeys.length; i++) {
            let key = inputKeys[i];
            errors[key] = false;
        }
        return errors;
    }

    setLoading = () => {
        this.setState({
            disabled: true,
            error: false,
            errors: this.getEmptyErrors(),
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

export function replaceNullValues(obj, newValue) {
    newValue = newValue === undefined ? '' : newValue;
    let keys = Object.keys(obj);
    for (let i = 0; i < keys.length; i++) {
        let key = keys[i];
        obj[key] = obj[key] === null ? newValue : obj[key];
    }
}

export function enumerate(array) {
    let newArray = [];
    for (let i = 0; i < array.length; i++) {
        newArray = newArray.concat([[i, array[i]]]);
    }
    return newArray;
}

export function arraysEqual(a, b) {
    if (a === b) return true;
    if (a == null || b == null) return false;
    if (a.length !== b.length) return false;

    for (var i = 0; i < a.length; ++i) {
        if (a[i] !== b[i]) return false;
    }
    return true;
}

export function scrollToTop() {
    window.scrollTo({
        top: 0,
        behavior: "auto"
    });
}

export function changePageHistory(history, location, activePage, searchStr, searchOrder, filters) {
    let search = `?page=${activePage}`;
    if (searchStr) {
        search = `${search}&q=${searchStr}`;
    }
    if (searchOrder) {
        search = `${search}&o=${searchOrder}`;
    }
    if (filters.length > 0) {
        filters = filters.join(',');
        search = `${search}&f=${filters}`;
    }
    history.push({
        pathname: location.pathname,
        search: search,
    });
    scrollToTop();
}

export function ClearButton({onClick, style, label, icon = 'close'}) {
    return <Button icon
                   labelPosition='right'
                   onClick={onClick}
                   style={style}
    >
        {label}
        <Icon name={icon}/>
    </Button>
}

export function SearchInput({initValue, onSubmit, size, placeholder = 'Search...'}) {
    let [value, setValue] = useState(initValue || '');
    size = size || 'small';

    const buttonClick = () => {
        // Clear the input when the "clear" button is clicked, search again.
        setValue('');
        onSubmit('');
    }

    // Button is "search" when input is dirty, otherwise it is "clear".
    let button = (
        <Button icon onClick={buttonClick} style={{marginLeft: '0.5em'}} type='reset' size={size}>
            <Icon name='close'/>
        </Button>
    );
    if (!initValue || initValue !== value) {
        button = (
            <Button icon style={{marginLeft: '0.5em'}} type='submit' disabled={value === ''} size={size}>
                <Icon name='search'/>
            </Button>
        );
    }

    const localOnSubmit = (e) => {
        // Send the value up when submitting.
        e.preventDefault();
        onSubmit(value);
    }

    return (
        <Form onSubmit={localOnSubmit}>
            <Form.Group inline style={{marginBottom: '1em'}}>
                <Input
                    type='text'
                    placeholder={placeholder}
                    onChange={(e) => setValue(e.target.value)}
                    value={value}
                    size={size}
                />
                {button}
            </Form.Group>
        </Form>
    )
}

export function ExternalLink(props) {
    return (
        <Link to={props.to} target='_blank' className={props.className} rel='noopener noreferrer'>
            {props.children}
        </Link>
    )
}

export function MoreButton(props) {
    return (
        <Grid columns={1} textAlign='center'>
            <Grid.Row>
                <Grid.Column>
                    <Button
                        onClick={props.onClick}
                        size='big'
                        style={{marginTop: '1em'}}
                        disabled={props.disabled}
                    >
                        {props.children}
                        More
                    </Button>
                </Grid.Column>
            </Grid.Row>
        </Grid>
    )
}

export const useWROLMode = () => {
    const [enabled, setEnabled] = useState(false);

    const fetchStatus = async () => {
        try {
            const settings = await getSettings();
            if (settings) {
                setEnabled(settings.wrol_mode);
            }
        } catch (e) {
            console.error(e);
        }
    }

    useEffect(() => {
        fetchStatus();
    }, []);

    return enabled;
}

export function WROLModeMessage({content}) {
    let enabled = useWROLMode();
    if (enabled) {
        return <Message icon='lock' header='WROL Mode Enabled' content={content}/>
    }
    return null;
}

// Thanks https://www.npmjs.com/package/text-ellipsis
export function textEllipsis(str, maxLength, {side = "end", ellipsis = "..."} = {}) {
    if (str.length > maxLength) {
        switch (side) {
            case "start":
                return ellipsis + str.slice(-(maxLength - ellipsis.length));
            case "end":
            default:
                return str.slice(0, maxLength - ellipsis.length) + ellipsis;
        }
    }
    return str;
}

export function TabLinks({links}) {
    return (
        <Menu tabular>
            {links.map((link) =>
                <NavLink
                    to={link.to}
                    className={'item'}
                    exact={link.exact || false}
                    style={{padding: '1em'}}
                    key={link.key}
                >
                    {link.text}
                </NavLink>
            )}
        </Menu>
    )
}

export function PageContainer(props) {
    return (
        <>
            <Responsive minWidth={770}>
                <Container fluid style={{marginTop: '1em', padding: '1em'}}>
                    {props.children}
                </Container>
            </Responsive>
            <Responsive maxWidth={769}>
                <Container style={{marginTop: '1em', padding: 0}}>
                    {props.children}
                </Container>
            </Responsive>
        </>
    )
}

export function CardGroupCentered(props) {
    return (
        <>
            <Responsive minWidth={770}>
                <Card.Group>
                    {props.children}
                </Card.Group>
            </Responsive>
            <Responsive maxWidth={769}>
                <Card.Group centered>
                    {props.children}
                </Card.Group>
            </Responsive>
        </>
    )
}

export function HelpPopup({icon, size, content, position}) {
    return <Popup
        content={content}
        size={size || null}
        position={position || 'left center'}
        trigger={
            <Icon circular link name={icon || 'question'} size='small'
                  style={{marginLeft: '0.25em', marginRight: '0.25em'}}
            />}
    />
}

export function HelpHeader({icon, headerSize, iconSize, headerContent, popupContent}) {
    return (
        <div className='inline-header'>
            <Header as={headerSize || 'h2'}>{headerContent}</Header>
            <span>
                <HelpPopup content={popupContent} size={iconSize} icon={icon}/>
            </span>
        </div>
    )
}

export function HotspotToggle(props) {
    let {on, setHotspot} = useHotspot();
    const disabled = on === null;
    return (
        <>
            <Checkbox toggle {...props}
                      label='WiFi Hotspot'
                      disabled={disabled}
                      checked={on === true}
                      onChange={(e, data) => setHotspot(data.checked)}
            />
            {disabled && <HelpPopup content='Hotspot is not supported on this server'/>}
        </>
    );
}

export function ThrottleToggle(props) {
    let {on, setThrottle} = useThrottle();
    const disabled = on === null;
    return (
        <>
            <Checkbox toggle {...props}
                      label='CPU Power-save'
                      disabled={disabled}
                      checked={on === true}
                      onChange={(e, data) => setThrottle(data.checked)}
            />
            {disabled && <HelpPopup content='CPU Power-save is not supported on this server'/>}
        </>
    );
}

export function DisableDownloadsToggle() {
    let {on, setDownloads} = useDownloaders();
    return <Checkbox toggle
                     label={on ? 'Downloading Enabled' : 'Downloading Disabled'}
                     disabled={on === null}
                     checked={on === true}
                     onChange={(e, data) => setDownloads(data.checked)}
    />;
}

export function emptyToNull(obj) {
    const keys = Object.keys(obj);
    for (let i = 0; i < keys.length; i++) {
        const key = keys[i];
        if (obj[key] === '') {
            obj[key] = null;
        }
    }
    return obj;
}

export function minutesToTimestamp(minutes) {
    minutes = Math.round(minutes);
    const hours = String(Math.floor(minutes / 60)).padStart(1, '0');
    minutes = minutes - (hours * 60);
    minutes = String(minutes).padStart(2, '0');
    return `${hours}:${minutes}`
}
