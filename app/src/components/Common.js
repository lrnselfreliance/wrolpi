import React, {useContext, useEffect, useState} from "react";
import {Card, Container, IconGroup, Image, Input, Modal, Pagination, Responsive} from 'semantic-ui-react';
import {Link, NavLink, useNavigate} from "react-router-dom";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import {useDirectories, useDownloaders, useHotspot, useSettings, useThrottle} from "../hooks/customHooks";
import {StatusContext, ThemeContext} from "../contexts/contexts";
import {Button, darkTheme, Form, Header, Icon, lightTheme, Menu, Popup, Statistic} from "./Theme";

export const API_URI = `http://${window.location.host}/api`;
export const VIDEOS_API = `${API_URI}/videos`;
export const ARCHIVES_API = `${API_URI}/archive`;
export const OTP_API = `${API_URI}/otp`;
export const DEFAULT_LIMIT = 20;
export const NAME = process.env && process.env.REACT_APP_NAME ? process.env.REACT_APP_NAME : null;

export function Paginator({activePage, onPageChange, totalPages, showFirstAndLast, size = 'mini'}) {
    const handlePageChange = (e, {activePage}) => {
        onPageChange(activePage);
    }

    return (<Pagination
        activePage={activePage}
        boundaryRange={1}
        onPageChange={handlePageChange}
        size={size}
        siblingRange={2}
        totalPages={totalPages}
        firstItem={showFirstAndLast ? undefined : null}
        lastItem={showFirstAndLast ? undefined : null}
    />)
}

export function divmod(x, y) {
    return [Math.floor(x / y), x % y];
}

export function secondsElapsed(seconds) {
    // Convert the provided seconds into a human-readable string of the time elapsed between the provided timestamp
    // and now.
    if (!seconds || seconds < 0) {
        return null;
    }

    let years;
    let days;
    let hours;
    let minutes;

    seconds = Math.abs((new Date().getTime() / 1000) - seconds);
    [years, seconds] = divmod(seconds, secondsToYears);
    [days, seconds] = divmod(seconds, secondsToDays);
    [hours, seconds] = divmod(seconds, secondsToHours);
    [minutes, seconds] = divmod(seconds, secondsToMinutes);
    seconds = Math.floor(seconds);

    if (years > 0 && days > 30) {
        return `${years}y${days}d`;
    } else if (years > 0) {
        return `${years}y`;
    } else if (days > 0) {
        return `${days}d`;
    } else if (hours > 0) {
        return `${hours}h`;
    } else if (minutes > 0) {
        return `${minutes}m`;
    }
    return `${seconds}s`
}

export function secondsToElapsedPopup(seconds) {
    // Return a Popup which allows the user see a more detailed timestamp when hovering.
    const elapsed = secondsElapsed(seconds);
    if (!elapsed) {
        return <></>;
    }
    return <Popup
        content={secondsToTimestamp(seconds)}
        on='hover'
        trigger={<span>{elapsed}</span>}
    />
}

export function isoDatetimeToElapsedPopup(dt) {
    const d = new Date(`${dt}+00:00`);
    return secondsToElapsedPopup(d.getTime() / 1000);
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

export function isoDatetimeToString(dt) {
    // Convert a datetime to a human-readable date format.
    let d = <></>;
    if (dt) {
        d = new Date(`${dt}+00:00`);
        d = `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
    }
    return d;
}

export function CardLink({to, newTab = false, ...props}) {
    const {t} = useContext(ThemeContext);
    props = {...props, ...t};

    props = newTab === true ? {...props, target: '_blank', rel: 'noopener noreferrer'} : props;
    return <Link to={to} className="no-link-underscore card-link" {...props}>
        {props.children}
    </Link>
}

export function ExternalCardLink({to, ...props}) {
    const {t} = useContext(ThemeContext);
    return <a href={to} target='_blank' rel='noopener noreferrer' className='no-link-underscore card-link' {...t}>
        {props.children}
    </a>
}

export function RequiredAsterisk() {
    return <span style={{color: '#db2828'}}> *</span>
}

export let defaultVideoOrder = '-upload_date';
export let defaultSearchOrder = 'rank';

export const frequencyOptions = [{key: 'daily', text: 'Daily', value: 86400}, {
    key: 'weekly', text: 'Weekly', value: 604800
}, {key: 'biweekly', text: 'Biweekly', value: 1209600}, {
    key: '30days', text: '30 Days', value: 2592000
}, {key: '90days', text: '90 Days', value: 7776000},];

export const rssFrequencyOptions = [{key: 'once', text: 'Once', value: 0}, {
    key: 'hourly', text: 'Hourly', value: 3600
}, {key: '3hours', text: '3 hours', value: 10800}, {key: '12hours', text: '12 hours', value: 43200}, {
    key: 'daily', text: 'Daily', value: 86400
}, {key: 'weekly', text: 'Weekly', value: 604800}, {key: 'biweekly', text: 'Biweekly', value: 1209600}, {
    key: '30days', text: '30 Days', value: 2592000
}, {key: '90days', text: '90 Days', value: 7776000},];

export function secondsToFrequency(seconds) {
    for (let i = 0; i < Object.keys(rssFrequencyOptions).length; i++) {
        let d = rssFrequencyOptions[i];
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

export function secondsToFullDuration(seconds) {
    let s = '';

    let years, days, hours, minutes;
    [years, seconds] = divmod(seconds, secondsToYears);
    [days, seconds] = divmod(seconds, secondsToDays);
    [hours, seconds] = divmod(seconds, secondsToHours);
    [minutes] = divmod(seconds, secondsToMinutes);
    if (years > 0) {
        s = `${years}Y`;
    }
    if (days > 0) {
        s = `${s} ${days}D`;
    }
    if (hours > 0 || minutes > 0) {
        hours = String(hours).padStart(2, '0');
        minutes = String(minutes).padStart(2, '0');
        s = `${s} ${hours}:${minutes}`;
    }
    return s;
}

export function secondsToDate(seconds) {
    let date = new Date(seconds * 1000);
    return `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`;
}

export function secondsToTimestamp(seconds) {
    let d = new Date(seconds * 1000);
    const day = String(d.getDate()).padStart(2, '0');
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    const sec = String(d.getSeconds()).padStart(2, '0');
    return `${d.getFullYear()}-${d.getMonth() + 1}-${day} ${hours}:${minutes}:${sec}`;
}

export function humanFileSize(bytes, dp = 1) {
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

export function humanBandwidth(bytes) {
    // Convert bytes to MBps and return a string.
    const thresh = 1024;

    if (Math.abs(bytes) < thresh) {
        return bytes + ' Bps';
    }

    const units = ['KBps', 'MBps', 'GBps', 'TBps', 'PBps', 'EBps', 'ZBps', 'YBps'];
    let u = -1;
    const r = 10;

    do {
        bytes /= thresh;
        ++u;
    } while (Math.round(Math.abs(bytes) * r) / r >= thresh && u < units.length - 1);

    return bytes.toFixed(0) + ' ' + units[u];
}

export function humanNumber(num, dp = 1) {
    // Convert large numbers to a more human-readable format.
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

export function isEmpty(i) {
    const str = Object.prototype.toString.call(i);
    if (str === '[object Object]') {
        return Object.keys(i).length === 0;
    } else if (str === '[object Array]') {
        return i.length === 0;
    }
    return !i;
}

export function scrollToTop() {
    window.scrollTo({
        top: 0, behavior: "auto"
    });
}

export function SearchInput({
                                searchStr,
                                onSubmit,
                                size = 'small',
                                placeholder,
                                action,
                                actionIcon,
                                clearable,
                                ...props
                            }) {
    let [value, setValue] = useState(searchStr || '');

    const handleClearSearch = (e) => {
        e.preventDefault();
        // Clear the input when the "clear" button is clicked, search again.
        setValue('');
        onSubmit('');
    }

    const localOnSubmit = (e) => {
        // Send the value up when submitting.
        e.preventDefault();
        onSubmit(value);
    }

    if ((action || actionIcon) && searchStr && searchStr === value && clearable) {
        action = <Button icon='close' size={size} onClick={handleClearSearch}/>;
    } else if (actionIcon) {
        action = <Button icon={actionIcon} size={size}/>;
    } else if (action) {
        action = <Button size={size}>{action}</Button>;
    }

    return <Form onSubmit={localOnSubmit} {...props}>
        <Input fluid
               placeholder={placeholder}
               type='text'
               onChange={(e) => setValue(e.target.value)}
               value={value}
               size={size}
               action={action}
        />
    </Form>
}

export function WROLModeMessage({content}) {
    const {status} = useContext(StatusContext);
    const wrol_mode = status ? status.wrol_mode : null;

    if (wrol_mode) {
        return <Message icon='lock' header='WROL Mode Enabled' content={content}/>
    }
    return null;
}

// Thanks https://www.npmjs.com/package/text-ellipsis
export function textEllipsis(str, maxLength = 100, {side = "end", ellipsis = "..."} = {}) {
    if (str && str.length > maxLength) {
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
    return (<Menu tabular>
        {links.map((link) => <NavLink
            to={link.to}
            className='item'
            style={{padding: '1em'}}
            key={link.to}
            end={link.end === true ? true : null}
        >
            {link.text}
        </NavLink>)}
    </Menu>)
}

export function PageContainer(props) {
    return (<>
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
    </>)
}

export function CardGroupCentered(props) {
    return (<div style={{marginTop: '1em'}}>
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
    </div>)
}

export function CardPosterLink({to, poster_url, imageLabel, external = false}) {
    const {s} = useContext(ThemeContext);
    const style = {display: 'flex', justifyContent: 'center', ...s['style']};
    const image = <Image fluid
                         src={poster_url}
                         label={imageLabel}
                         style={{maxHeight: '163px', width: 'auto'}}
    />;
    if (external === true) {
        return <a href={to} target='_blank' style={style}>
            {image}
        </a>
    } else {
        // Link using React Router.
        return <Link to={to} style={style}>
            {image}
        </Link>
    }
}

export function HelpPopup({icon, size, content, position}) {
    return <Popup
        content={content}
        size={size || null}
        position={position || 'left center'}
        trigger={<Icon circular link name={icon || 'question'} size='small'
                       style={{marginLeft: '0.25em', marginRight: '0.25em'}}
        />}
    />
}

export function HelpHeader({icon, headerSize, iconSize, headerContent, popupContent}) {
    return (<div className='inline-header'>
        <Header as={headerSize || 'h2'}>{headerContent}</Header>
        <span>
                <HelpPopup content={popupContent} size={iconSize} icon={icon}/>
            </span>
    </div>)
}

export function HotspotToggle() {
    let {on, setHotspot} = useHotspot();
    const disabled = on === null;
    return (<div style={{margin: '0.5em'}}>
        <Toggle
            label='WiFi Hotspot'
            disabled={disabled}
            checked={on === true}
            onChange={checked => setHotspot(checked)}
        />
        {disabled && <HelpPopup content='Hotspot is not supported on this server'/>}
    </div>);
}

export function ThrottleToggle() {
    let {on, setThrottle} = useThrottle();
    const disabled = on === null;
    return (<div style={{margin: '0.5em'}}>
        <Toggle
            label='CPU Power-save'
            disabled={disabled}
            checked={on === true}
            onChange={checked => setThrottle(checked)}
        />
        {disabled && <HelpPopup content='CPU Power-save is not supported on this server'/>}
    </div>);
}

export function Toggle({label, checked, disabled, onChange, icon}) {
    // Custom toggle because Semantic UI does not handle inverted labels correctly.
    const {t, inverted} = useContext(ThemeContext);

    let style = {marginLeft: '1em'};
    if (t && t.style) {
        style = {...t.style, ...style};
    }

    disabled = disabled === true ? 'disabled' : '';

    let inputClassName = `${disabled} ${inverted}`;
    let sliderClassName = `${disabled} ${inverted} slider`;
    if (inverted) {
        style['color'] = '#dddddd';
    }
    if (disabled && inverted) {
        style['color'] = '#888888';
    }

    let onMouseUp;
    if (onChange) {
        onMouseUp = (e) => {
            if (disabled) {
                return;
            }
            e.preventDefault();
            if (onChange) {
                onChange(!checked);
            }
        }
    }

    if (icon) {
        icon = <Icon name={icon}/>
    }

    return <>
        <div className='toggle' onMouseUp={onMouseUp}>
            <input type="checkbox" className={inputClassName} checked={checked} onChange={onMouseUp}/>
            <span className={sliderClassName}></span>
        </div>
        <span style={style}>
            {icon}
            {label}
        </span>
    </>
}

export function DisableDownloadsToggle() {
    let {on, setDownloads} = useDownloaders();
    return <Form>
        <Toggle toggle
                label={on ? 'Downloading Enabled' : 'Downloading Disabled'}
                disabled={on === null}
                checked={on === true}
                onChange={setDownloads}
        />
    </Form>;
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

export function mimetypeColor(mimetype) {
    try {
        if (mimetype === 'application/pdf') {
            return 'red'
        } else if (mimetype && mimetype.startsWith('video/')) {
            return 'blue'
        } else if (mimetype && mimetype.startsWith('image/')) {
            return 'pink'
        } else if (mimetype && mimetype.startsWith('text/html')) {
            return 'green'
        } else if (mimetype && mimetype.startsWith('application/zip')) {
            return 'purple'
        } else if (mimetype && (
            mimetype.startsWith('application/epub') || mimetype.startsWith('application/x-mobipocket-ebook'))) {
            return 'yellow'
        }
    } catch (e) {
        console.error(e);
        console.error('Unable to choose mimetype color');
    }
    return 'grey'
}

export function FileIcon({file, disabled = true, size = 'huge', ...props}) {
    // Default to a grey file icon.
    const {mimetype} = file;
    props['name'] = 'file';
    props['color'] = mimetypeColor(mimetype);
    if (mimetype) {
        if (mimetype.startsWith('text/html') || mimetype.startsWith('application/json')) {
            props['name'] = 'file code';
        } else if (mimetype.startsWith('application/pdf')) {
            props['name'] = 'file pdf';
        } else if (mimetype.startsWith('text/plain')) {
            props['name'] = 'file text';
        } else if (mimetype.startsWith('image/')) {
            props['name'] = 'image';
        } else if (mimetype.startsWith('video/')) {
            props['name'] = 'film';
        } else if (mimetype.startsWith('application/zip')) {
            props['name'] = 'file archive';
        } else if (mimetype.startsWith('application/x-iso9660-image')) {
            props['name'] = 'dot circle';
        } else if (mimetype.startsWith('application/epub') || mimetype.startsWith('application/x-mobipocket-ebook')) {
            props['name'] = 'book';
        }
    }
    return <Icon disabled={disabled} size={size} {...props}/>
}

export function LoadStatistic({label, value, cores, ...props}) {
    const quarter = cores / 4;
    if (cores && value >= (quarter * 3)) {
        props['color'] = 'red';
    } else if (cores && value >= (quarter * 2)) {
        props['color'] = 'orange';
    }
    return <Statistic
        label={label}
        value={value ? parseFloat(value).toFixed(1) : '?'}
        {...props}/>;
}

export function DarkModeToggle() {
    const {savedTheme, cycleSavedTheme} = useContext(ThemeContext);
    let iconName = 'lightbulb outline';
    if (savedTheme === darkTheme) {
        iconName = 'moon';
    } else if (savedTheme === lightTheme) {
        iconName = 'sun';
    }

    return <Icon
        name={iconName}
        onClick={cycleSavedTheme}
        style={{cursor: 'pointer'}}
    />
}


export function UnsupportedModal(header, message, icon) {
    const [open, setOpen] = useState(false);
    const onOpen = () => setOpen(true);
    const onClose = () => setOpen(false);

    const modal = <Modal basic closeIcon
                         onOpen={onOpen}
                         onClose={onClose}
                         open={open}
    >
        <Header>
            <Icon name={icon || 'exclamation triangle'}/>
            {header || 'Unsupported'}
        </Header>
        <Modal.Content>
            <Modal.Description>
                {message}
            </Modal.Description>
        </Modal.Content>
        <Modal.Actions>
            <Button basic inverted onClick={onClose}>Ok</Button>
        </Modal.Actions>
    </Modal>;

    return {modal, doClose: onClose, doOpen: onOpen};
}

export function HotspotStatusIcon() {
    const {on, setHotspot, dockerized} = useHotspot();
    const {modal, doOpen} = UnsupportedModal('Unsupported on Docker', 'You cannot toggle the hotspot on Docker.');

    const toggleHotspot = (e) => {
        e.preventDefault();
        if (dockerized) {
            doOpen();
        }
        if (on != null) {
            setHotspot(!on);
        }
    }

    return <>
        <a href='#' onClick={toggleHotspot}>
            <IconGroup size='large'>
                <Icon name='wifi' disabled={on !== true}/>
                {on === false && <Icon corner name='x'/>}
                {on === null && <Icon corner name='question'/>}
            </IconGroup>
        </a>
        {modal}
    </>
}

export function useTitle(title) {
    const documentDefined = typeof document !== 'undefined';
    const originalTitle = React.useRef(documentDefined ? document.title : null);
    const name = NAME ? `${NAME} WROLPi` : `WROLPi`;

    useEffect(() => {
        if (!documentDefined) {
            return;
        }

        const newTitle = `${title} - ${name}`
        if (title && document.title !== newTitle) {
            document.title = newTitle;
        }
        return () => {
            document.title = originalTitle.current;
        }
    }, [title]);
}

export function DirectoryInput({disabled, error, placeholder, setInput, value, required, isDirectory}) {
    const {directory, directories, setDirectory, isDir} = useDirectories(value);
    const {settings} = useSettings();

    if (!directories || !settings) {
        return <></>;
    }

    const localSetInput = (e, {value}) => {
        setInput(value);
        setDirectory(value);
    }

    const {media_directory} = settings;
    error = error || isDirectory && !isDir;

    return (<div>
        <Input
            action={{
                color: error ? 'red' : 'green',
                labelPosition: 'left',
                icon: 'folder',
                content: media_directory,
            }}
            required={required}
            disabled={disabled}
            actionPosition='left'
            value={directory}
            onChange={localSetInput}
            placeholder={placeholder}
            list='directories'
        />
        <datalist id='directories'>
            {directories.map(i => <option key={i} value={i}>{i}</option>)}
        </datalist>
    </div>);
}

export const BackButton = () => {
    const navigate = useNavigate();
    return <Button icon='arrow left' content='Back' onClick={() => navigate(-1)}/>;
}

export const ColorToSemanticHexColor = (color) => {
    const colorMap = {
        red: '#db2828',
        orange: '#f2711c',
        yellow: '#fbbd08',
        olive: '#b5cc18',
        green: '#21ba45',
        teal: '#00b5ad',
        blue: '#2185d0',
        violet: '#6435c9',
        purple: '#a333c8',
        pink: '#e03997',
        brown: '#a5673f',
        grey: '#767676',
    }
    return colorMap[color] || null;
}

export const filterToMimetypes = (filter) => {
    if (filter === 'video') {
        return ['video'];
    } else if (filter === 'archive') {
        return ['text/html'];
    } else if (filter === 'pdf') {
        return ['application/pdf'];
    } else if (filter === 'ebook') {
        return ['application/epub+zip', 'application/x-mobipocket-ebook'];
    } else if (filter === 'image') {
        return ['image'];
    } else if (filter === 'zip') {
        return ['application/zip'];
    }
}

export const toLocaleString = (num, locale = 'en-US') => {
    return num.toLocaleString(locale);
}

export const cardTitleWrapper = (title, maxLength = 100, breakWord = true) => {
    const style = breakWord ? {overflowWrap: 'break-word'} : null;
    return <span style={style}>{textEllipsis(title, maxLength)}</span>
}
