import React, {useContext, useEffect, useState} from "react";
import {
    Button as SButton,
    ButtonGroup,
    Card,
    Confirm,
    Container,
    Icon as SIcon,
    IconGroup,
    Input,
    Label,
    Pagination,
    Search,
    Transition
} from 'semantic-ui-react';
import {Link, NavLink, useNavigate, useSearchParams} from "react-router-dom";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import {
    useCPUTemperature,
    useDirectories,
    useHotspot,
    useLoad,
    useSearchDirectories,
    useSearchOrder,
    useSettings,
    useThrottle,
    useWROLMode
} from "../hooks/customHooks";
import {Media, StatusContext, ThemeContext} from "../contexts/contexts";
import {
    Button,
    CardIcon,
    darkTheme,
    Form,
    Header,
    Icon,
    lightTheme,
    Menu,
    Modal,
    ModalActions,
    ModalContent,
    ModalDescription,
    ModalHeader,
    Popup,
    Statistic
} from "./Theme";
import {FilePreviewContext} from "./FilePreview";
import _ from "lodash";
import {killDownloads, startDownloads} from "../api";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";

export const API_URI = process.env && process.env.REACT_APP_API_URI ? process.env.REACT_APP_API_URI : `${window.location.protocol}//${window.location.host}/api`;
export const VIDEOS_API = `${API_URI}/videos`;
export const ARCHIVES_API = `${API_URI}/archive`;
export const OTP_API = `${API_URI}/otp`;
export const ZIM_API = `${API_URI}/zim`;
export const DEFAULT_LIMIT = 20;
export const NAME = process.env && process.env.REACT_APP_NAME ? process.env.REACT_APP_NAME : null;

export function Paginator({activePage, onPageChange, totalPages, showFirstAndLast, size = 'mini'}) {
    const handlePageChange = (e, {activePage}) => {
        onPageChange(activePage);
    }

    return <>
        <Media at='mobile'>
            <Pagination
                activePage={activePage}
                boundaryRange={1}
                onPageChange={handlePageChange}
                size={size}
                siblingRange={2}
                totalPages={totalPages}
                firstItem={showFirstAndLast ? undefined : null}
                lastItem={showFirstAndLast ? undefined : null}
            />
        </Media>
        <Media greaterThanOrEqual='tablet'>
            <Pagination
                activePage={activePage}
                boundaryRange={1}
                onPageChange={handlePageChange}
                size={size}
                siblingRange={5}
                totalPages={totalPages}
                firstItem={showFirstAndLast ? undefined : null}
                lastItem={showFirstAndLast ? undefined : null}
            />
        </Media>
    </>
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

    // Get seconds elapsed between now and `seconds` which is a UTC epoch.
    const localNow = (new Date()).getTime();

    let years;
    let days;
    let hours;
    let minutes;

    seconds = Math.abs((localNow / 1000) - seconds);
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
    let d = new Date(dt);
    return secondsToElapsedPopup(d.getTime() / 1000);
}

export function secondsToHMS(totalSeconds) {
    let hours = Math.floor(totalSeconds / 3600);
    totalSeconds -= hours * 3600;
    let minutes = Math.floor(totalSeconds / 60);
    let seconds = totalSeconds - (minutes * 60);

    hours = String('00' + hours).slice(-2);
    minutes = String('00' + minutes).slice(-2);
    seconds = String('00' + seconds).slice(-2);

    return {hours, minutes, seconds};
}

export function Duration({totalSeconds}) {
    const {hours, minutes, seconds} = secondsToHMS(totalSeconds);

    if (hours > 0) {
        return <div className='duration-overlay'>{hours}:{minutes}:{seconds}</div>
    } else if (totalSeconds) {
        return <div className='duration-overlay'>{minutes}:{seconds}</div>
    } else {
        return <></>
    }
}

export function isoDatetimeToString(dt, time = false) {
    // Convert a datetime to a human-readable date format.
    let d = <React.Fragment/>;
    if (dt && time) {
        d = new Date(dt);
        const hours = String(d.getHours()).padStart(2, '0');
        const minutes = String(d.getMinutes()).padStart(2, '0');
        const seconds = String(d.getSeconds()).padStart(2, '0');
        d = `${d.toDateString()} ${hours}:${minutes}:${seconds}`;
    } else if (dt) {
        d = new Date(dt);
        d = d.toDateString();
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

export function ExternalCardLink({to, children, ...props}) {
    const {t} = useContext(ThemeContext);
    return <a
        href={to}
        target='_blank'
        rel='noopener noreferrer'
        className='no-link-underscore card-link'
        {...t}
        {...props}
    >
        {children}
    </a>
}

export function PreviewLink({file, children, className, ...props}) {
    const {t} = useContext(ThemeContext);
    const {setPreviewFile} = React.useContext(FilePreviewContext);
    className = className ? `clickable ${className}` : `clickable `;
    return <span className={className} onClick={() => setPreviewFile(file)} {...props} {...t}>
        {children}
    </span>
}

export function PreviewPath({path, mimetype, taggable = true, ...props}) {
    return <PreviewLink file={{path, mimetype, taggable}} {...props}/>
}

export function RequiredAsterisk() {
    return <span style={{color: '#db2828'}}> *</span>
}

export let defaultVideoOrder = '-published_datetime';
export let defaultSearchOrder = 'rank';

export const frequencyOptions = [{key: null, text: '', value: null}, {
    key: 'daily', text: 'Daily', value: 86400
}, {key: 'weekly', text: 'Weekly', value: 604800}, {key: 'biweekly', text: 'Biweekly', value: 1209600}, {
    key: '30days', text: '30 Days', value: 2592000
}, {key: '90days', text: '90 Days', value: 7776000},];

export const rssFrequencyOptions = [{key: 'once', text: 'Once', value: 0}, {
    key: 'hourly', text: 'Hourly', value: 3600
}, {key: '3hours', text: '3 hours', value: 10800}, {key: '12hours', text: '12 hours', value: 43200}, {
    key: 'daily', text: 'Daily', value: 86400
}, {key: 'weekly', text: 'Weekly', value: 604800}, {key: 'biweekly', text: 'Biweekly', value: 1209600}, {
    key: '30days', text: '30 Days', value: 2592000
}, {key: '90days', text: '90 Days', value: 7776000}, {key: '180days', text: '180 Days', value: 15552000}];

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
    let duration = '';

    let years, days, hours, minutes;
    [years, seconds] = divmod(seconds, secondsToYears);
    [days, seconds] = divmod(seconds, secondsToDays);
    [hours, seconds] = divmod(seconds, secondsToHours);
    [minutes] = divmod(seconds, secondsToMinutes);
    if (years > 0) {
        duration = `${years}Y`;
    }
    if (days > 0) {
        duration = `${duration} ${days}D`;
    }
    if (hours > 0 || minutes > 0) {
        hours = String(hours).padStart(2, '0');
        minutes = String(minutes).padStart(2, '0');
        duration = `${duration} ${hours}:${minutes}`;
    }
    if (years === 0 && days === 0 && hours === 0 && minutes === 0) {
        // Less than a minute.
        seconds = String(seconds).padStart(2, '0');
        duration = `00:00:${seconds}`;
    }
    return duration.trim();
}

export function secondsToTimestamp(seconds) {
    let d = new Date(seconds * 1000);
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    const sec = String(d.getSeconds()).padStart(2, '0');
    return `${d.getFullYear()}-${month}-${day} ${hours}:${minutes}:${sec}`;
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

export function scrollToTop() {
    window.scrollTo({
        top: 0, behavior: "auto"
    });
}

export function scrollToTopOfElement(element, smooth = true) {
    element.scroll({
        top: 0,
        behavior: smooth ? 'smooth' : 'auto',
    });
}

const useClearableInput = (searchStr, onChange, onClear, onSubmit, size = 'small', placeholder = 'Search...', icon = 'search') => {
    const [value, setValue] = useState(searchStr || '');
    const [submitted, setSubmitted] = useState(false);

    const handleChange = (e) => {
        if (e) {
            e.preventDefault();
        }
        setValue(e.target.value);
        setSubmitted(false);
        if (onChange) {
            // Try to call the remote function, don't let its failure break this.
            try {
                onChange(e.target.value);
            } catch (e) {
                console.error(`Call to ${onChange} failed`);
            }
        }
    }

    const handleClearSearch = (e) => {
        e.preventDefault();
        // Clear the input when the "clear" button is clicked, search again.
        setValue('');
        setSubmitted(false);
        if (onSubmit) {
            onSubmit('');
        }
        if (onClear) {
            onClear();
        }
    }

    const localOnSubmit = (e) => {
        // Send the value up when submitting.
        e.preventDefault();
        setSubmitted(true);
        if (onSubmit) {
            onSubmit(value);
        } else {
            console.debug('No onSubmit defined');
        }
    }

    const clearButton = <Button
        icon='close'
        size={size}
        onClick={handleClearSearch}
        type='button'
        disabled={!!!value}
        className='search-clear'
    />;

    // Can only clear after submitting.
    let action = submitted ? clearButton : <Button type='button' icon={icon} size='big'/>;

    const input = <Input fluid
                         placeholder={placeholder}
                         type='text'
                         onChange={handleChange}
                         value={value}
                         size={size}
                         className='search-input'
                         action={action}
    />;

    return {value, submitted, clearButton, input, localOnSubmit, handleChange}
}

export function SearchInput({
                                searchStr,
                                onSubmit,
                                onChange,
                                onClear,
                                size = 'small',
                                placeholder = 'Search...',
                                icon = 'search',
                                ...props
                            }) {
    // A Semantic <Input> with a Clear button as the action.
    let {input, localOnSubmit} = useClearableInput(searchStr, onChange, onClear, onSubmit, size, placeholder, icon);

    return <Form onSubmit={localOnSubmit} {...props} className='search-container'>
        {input}
    </Form>
}

export function SearchResultsInput({
                                       searchStr,
                                       onSubmit,
                                       onClear = null,
                                       onChange = null,
                                       size = 'small',
                                       placeholder = 'Search...',
                                       icon = 'search',
                                       action,
                                       actionIcon,
                                       clearable = false,
                                       autoFocus = false,
                                       results = undefined,
                                       handleResultSelect = null,
                                       resultRenderer = undefined,
                                       loading = false,
                                       ...props
                                   }) {
    // A Semantic <Search> input with a Clear button.
    let {
        value,
        clearButton,
        localOnSubmit,
        handleChange,
    } = useClearableInput(searchStr, onChange, onClear, onSubmit, size, placeholder);

    const localHandleResultSelect = (e, data) => {
        if (e) {
            e.preventDefault();
        }
        if (handleResultSelect) {
            console.debug(`Selected result`, data);
            handleResultSelect(data);
        } else {
            console.error('No handleResultSelect defined!');
        }
    }

    return <Form onSubmit={localOnSubmit} {...props} className='search-container'>
        <Search category
                input={{fluid: true, icon: icon}}
                placeholder={placeholder}
                type='text'
                onSearchChange={handleChange}
                onResultSelect={localHandleResultSelect}
                value={value}
                size={size}
                results={results}
                resultRenderer={resultRenderer}
                className='search-input'
                loading={loading}
        />
        {clearable === true && <div style={{marginLeft: '1em'}}>{clearButton}</div>}
    </Form>
}

export function WROLModeMessage({content}) {
    const wrolModeEnabled = useWROLMode();

    if (wrolModeEnabled) {
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
    const [searchParams, setSearchParams] = useSearchParams();

    const getTo = (to) => {
        return `${to}?${searchParams.toString()}`;
    }

    return <Menu tabular>
        {links.map((link) => <NavLink
            to={getTo(link.to)}
            className='item'
            style={{padding: '1em'}}
            key={link.to}
            end={link.end === true ? true : null}
        >
            {link.text}
        </NavLink>)}
    </Menu>
}

export function PageContainer(props) {
    return <>
        <Media at='mobile'>
            <Container style={{marginTop: '1em', padding: 0}}>
                {props.children}
            </Container>
        </Media>
        <Media greaterThanOrEqual='tablet'>
            <Container fluid style={{marginTop: '1em', padding: '1em'}}>
                {props.children}
            </Container>
        </Media>
    </>;
}

export function CardGroupCentered(props) {
    return <div style={{marginTop: '1em'}}>
        <Media at='mobile'>
            <Card.Group centered>
                {props.children}
            </Card.Group>
        </Media>
        <Media greaterThanOrEqual='tablet'>
            <Card.Group>
                {props.children}
            </Card.Group>
        </Media>
    </div>
}

export function findPosterPath(file) {
    if (!file) {
        return;
    }
    const {files, poster_path, cover_path, screenshot_path, video} = file;
    if (poster_path) {
        return poster_path;
    }
    if (cover_path) {
        return cover_path;
    }
    if (screenshot_path) {
        return screenshot_path;
    }
    if (file['data'] && file['data']['cover_path']) {
        // Ebook.
        return file['data']['cover_path'];
    }
    if (video && video['poster_path']) {
        // file is a video model.
        return video['poster_path'];
    }
    if (!_.isEmpty(files)) {
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            if (file['mimetype'] && file['mimetype'].startsWith('image/')) {
                // Found an image file, use that as the poster.
                return file['path'];
            }
        }
    }
}

export function CardPoster({to, file}) {
    const {s} = useContext(ThemeContext);
    // Used to center posters in CardIcon.
    const style = {display: 'flex', justifyContent: 'center', ...s['style']};
    const navigate = useNavigate();

    const cardTagIcon = <div className="ui green left corner label">
        <i aria-hidden="true" className="tag icon"></i>
    </div>;
    let imageLabel = !_.isEmpty(file.tags) ? cardTagIcon : null;

    let posterPath = findPosterPath(file);

    if (posterPath) {
        // FileGroup has a poster (screenshot/thumbnail) file.
        posterPath = `/media/${encodeMediaPath(posterPath)}`;

        const image = <>
            {/* Replicate <Image label/> but with maxHeight applied to image */}
            {imageLabel}
            <img alt='poster' src={posterPath} style={{maxHeight: '163px', width: 'auto'}}/>
        </>;

        if (to) {
            // Link within this App.
            return <Link to={to} style={style}>
                {image}
            </Link>
        } else {
            // Preview the file.
            return <div style={style}>
                <PreviewLink file={file}>
                    {image}
                </PreviewLink>
            </div>
        }
    } else {
        // FileGroup has no poster.
        if (!to || (to.startsWith('/media/') || to.startsWith('/download/'))) {
            // "to" is a downloadable file outside the app, preview the file.
            return <PreviewLink file={file}>
                <CardIcon>
                    {imageLabel}
                    <FileIcon file={file}/>
                </CardIcon>
            </PreviewLink>
        } else if (!posterPath && to) {
            // Link to the full page in this App.
            return <Link to={to}>
                <CardIcon onClick={() => navigate(to)}>
                    {imageLabel}
                    <FileIcon file={file}/>
                </CardIcon>
            </Link>
        }
    }
}

export function HelpPopup({icon, size, content, position, iconSize = 'small'}) {
    return <Popup
        content={content}
        size={size || null}
        position={position || 'left center'}
        trigger={<Icon circular link name={icon || 'question'} size={iconSize}
                       style={{marginLeft: '0.25em', marginRight: '0.25em'}}
        />}
    />
}

export function HelpHeader({icon, headerSize, iconSize, headerContent, popupContent}) {
    return <div className='inline-header'>
        <Header as={headerSize || 'h2'}>{headerContent}</Header>
        <span>
                <HelpPopup content={popupContent} size={iconSize} icon={icon}/>
            </span>
    </div>
}

export function HotspotToggle() {
    let {on, setHotspot} = useHotspot();
    const disabled = on === null;
    return <div style={{margin: '0.5em'}}>
        <Toggle
            label='WiFi Hotspot'
            disabled={disabled}
            checked={on === true}
            onChange={checked => setHotspot(checked)}
        />
        {disabled && <HelpPopup content='Hotspot is not supported on this server'/>}
    </div>;
}

export function ThrottleToggle() {
    let {on, setThrottle} = useThrottle();
    const disabled = on === null;
    return <div style={{margin: '0.5em'}}>
        <Toggle
            label='CPU Power-save'
            disabled={disabled}
            checked={on === true}
            onChange={checked => setThrottle(checked)}
        />
        {disabled && <HelpPopup content='CPU Power-save is not supported on this server'/>}
    </div>;
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

    let onMouseUp = () => {
    };
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
            <input type="checkbox" className={inputClassName} checked={checked} onChange={onMouseUp}
                   data-testid='toggle'/>
            <span className={sliderClassName}></span>
        </div>
        <span style={style} data-testid='toggle-label'>
            {icon}
            {label}
        </span>
    </>
}

export function DisableDownloadsToggle() {
    const [pending, setPending] = React.useState(false);
    const {status, fetchStatus} = React.useContext(StatusContext);

    const {downloads} = status ? status : {downloads: null};
    const wrolModeEnabled = useWROLMode();

    const setDownloads = async (enable) => {
        setPending(true);
        if (enable) {
            await startDownloads();
        } else {
            await killDownloads();
        }
        await fetchStatus();
        setPending(false);
    }

    const on = downloads && downloads['disabled'] === false && downloads['stopped'] === false;
    return <Form>
        <Toggle
            label={on === true ? 'Downloading Enabled' : 'Downloading Disabled'}
            disabled={wrolModeEnabled || pending || downloads === null}
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
    if (!mimetype) {
        return 'grey';
    }
    try {
        if (mimetype === 'application/pdf') {
            return 'red'
        } else if (mimetype.startsWith('video/')) {
            return 'blue'
        } else if (mimetype.startsWith('image/')) {
            return 'pink'
        } else if (mimetype.startsWith('text/html')) {
            return 'green'
        } else if (mimetype.startsWith('application/epub')) {
            return 'yellow'
        } else if (mimetype.startsWith('audio/')) {
            return 'violet'
        } else if (isZipMimetype(mimetype)) {
            return 'purple'
        }
    } catch (e) {
        console.error(e);
        console.error('Unable to choose mimetype color');
    }
    return 'grey'
}

export function isZipMimetype(mimetype) {
    return mimetype.startsWith('application/zip') || mimetype.startsWith('application/zlib') || mimetype.startsWith('application/x-7z-compressed') || mimetype.startsWith('application/x-bzip2') || mimetype.startsWith('application/x-xz') || mimetype.startsWith('application/gzip') || mimetype.startsWith('application/x-rar');
}

export function mimetypeIconName(mimetype, lowerPath = '') {
    if (mimetype) {
        if (mimetype.startsWith('text/html') || mimetype.startsWith('application/json') || mimetype.startsWith('text/yaml') || mimetype.startsWith('text/xml')) {
            return 'file code';
        } else if (mimetype.startsWith('application/pdf')) {
            return 'file pdf';
        } else if (mimetype.startsWith('text/plain')) {
            return 'file text';
        } else if (mimetype.startsWith('image/')) {
            return 'image';
        } else if (mimetype.startsWith('video/')) {
            return 'film';
        } else if (mimetype.startsWith('message/rfc822')) {
            return 'mail';
        } else if (isZipMimetype(mimetype)) {
            return 'file archive';
        } else if (mimetype.startsWith('application/x-iso9660-image') || mimetype.startsWith('application/x-raw-disk-image') || mimetype.startsWith('application/x-cd-image')) {
            return 'dot circle';
        } else if (mimetype.startsWith('application/epub') || mimetype.startsWith('application/x-mobipocket-ebook') || mimetype.startsWith('application/vnd.amazon.mobi8-ebook')) {
            return 'book';
        } else if (mimetype.startsWith('text/vtt') || mimetype.startsWith('text/srt')) {
            return 'closed captioning';
        } else if (mimetype.startsWith('application/x-openscad') || mimetype.startsWith('model/stl')) {
            return 'cube';
        } else if (mimetype.startsWith('application/x-dosexec') || mimetype.startsWith('application/x-msi') || mimetype.startsWith('application/vnd.microsoft.portable-executable')) {
            return 'windows';
        } else if (mimetype.startsWith('audio/')) {
            return 'file audio';
        } else if (mimetype.startsWith('application/vnd.openxmlformats-officedocument.wordprocessingml.document')) {
            return 'file word';
        } else if (mimetype.startsWith('application/x-x509-ca-cert')) {
            return 'certificate';
        } else if (mimetype.startsWith('application/octet-stream')) {
            if (lowerPath.endsWith('.mp3')) {
                return 'file audio';
            } else if (lowerPath.endsWith('.stl')) {
                return 'cube';
            } else if (lowerPath.endsWith('.blend')) {
                return 'cube';
            } else if (lowerPath.endsWith('.dmg')) {
                return 'apple';
            } else if (lowerPath.endsWith('.azw3')) {
                return 'book';
            } else if (lowerPath.endsWith('.exe')) {
                return 'windows';
            }
        } else if (mimetype.startsWith('application/vnd.openxmlformats-officedocument.spreadsheetml.') || mimetype.startsWith('application/vnd.ms-excel') || mimetype.startsWith('application/vnd.oasis.opendocument.spreadsheet')) {
            return 'file excel'
        } else if (mimetype.startsWith('application/vnd.openxmlformats-officedocument.wordprocessingml.') || mimetype.startsWith('application/msword') || mimetype.startsWith('application/vnd.oasis.opendocument.text')) {
            return 'file word'
        } else if (mimetype.startsWith('application/vnd.openxmlformats-officedocument.presentationml.') || mimetype.startsWith('application/vnd.ms-powerpoint') || mimetype.startsWith('application/vnd.oasis.opendocument.presentation')) {
            return 'file powerpoint'
        } else if (mimetype.startsWith('font/') || mimetype.startsWith('application/font-sfnt') || mimetype.startsWith('application/vnd.ms-fontobject')) {
            return 'font'
        }
    }
    if (lowerPath.endsWith('.pem')) {
        return 'certificate';
    }
    return 'file';
}

export function FileIcon({file, disabled = true, size = 'huge', ...props}) {
    // Default to a grey file icon.
    const {mimetype, path, primary_path} = file;
    // `file` may be a file_group or a file.
    const lowerPath = primary_path ? primary_path.toLocaleString() : path.toLowerCase();
    props['name'] = mimetypeIconName(mimetype, lowerPath);
    props['color'] = mimetypeColor(mimetype);
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
        <ModalContent>
            <ModalDescription>
                {message}
            </ModalDescription>
        </ModalContent>
        <ModalActions>
            <Button basic inverted onClick={onClose}>Ok</Button>
        </ModalActions>
    </Modal>;

    return {modal, doClose: onClose, doOpen: onOpen};
}

export function HotspotStatusIcon() {
    const {on, setHotspot, dockerized} = useHotspot();
    const {modal, doOpen} = UnsupportedModal('Unsupported', 'You cannot toggle the hotspot on this machine.');
    const [confirmOpen, setConfirmOpen] = React.useState(false);

    const handleConfirm = (e) => {
        if (e) {
            e.preventDefault()
        }
        setConfirmOpen(false);
        setHotspot(false);
    }

    if (dockerized === false && on === true) {
        return <>
            <Confirm
                open={confirmOpen}
                onCancel={() => setConfirmOpen(false)}
                onClose={() => setConfirmOpen(false)}
                onConfirm={handleConfirm}
                header='Disable the hotspot'
                content='You will be disconnected when using the hotspot. Are you sure?'
                confirmButton='Disable'
            />
            <a href='#' onClick={() => setConfirmOpen(true)}>
                <IconGroup size='large'>
                    <Icon name='wifi' disabled={on !== true}/>
                    {on === false && <Icon corner name='x'/>}
                    {on === null && <Icon corner name='question'/>}
                </IconGroup>
            </a>
        </>
    } else if (dockerized === false && on === false) {
        return <a href='#' onClick={() => setHotspot(true)}>
            <IconGroup size='large'>
                <Icon name='wifi' disabled/>
                <Icon corner name='x'/>
            </IconGroup>
        </a>
    }

    // Hotspot is not available, or, status has not yet been fetched.
    return <>
        <a href='#' onClick={doOpen}>
            <IconGroup size='large'>
                <Icon name='wifi' disabled/>
                <Icon corner name='question'/>
            </IconGroup>
        </a>
        {modal}
    </>
}

export function CPUTemperatureIcon({size = 'large', fallback = null}) {
    // Returns an Icon only if temperature is too high.
    const {temperature, highTemperature, criticalTemperature} = useCPUTemperature();

    if (temperature === null || temperature < highTemperature) {
        // Temperature is not a problem.
        return fallback;
    }

    let icon = temperature >= criticalTemperature ?
        <Icon data-testid='cpuTemperatureIcon' name='thermometer' size={size} color='red'/>
        : <Icon data-testid='cpuTemperatureIcon' name='thermometer half' size={size} color='yellow'/>;
    icon = <Link to='/admin/status'>{icon}</Link>;

    return <Popup content={`CPU: ${temperature}°C`} trigger={icon}/>
}

export function SystemLoadIcon({size = 'large', fallback = null}) {
    const {minute_1, mediumLoad, highLoad} = useLoad();

    if (!mediumLoad && !highLoad) {
        return fallback;
    }

    // Only return the icon if the load is not low.
    const color = highLoad ? 'red' : 'yellow';
    let icon = <Link to='/admin/status'>
        <Icon name='tachometer alternate' size={size} color={color}/>
    </Link>;
    return <Popup content={`Load: ${minute_1}`} trigger={icon}/>
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

export function DirectorySearch({onSelect, value, ...props}) {
    const {
        directoryName,
        setDirectoryName,
        directories,
        channelDirectories,
        domainDirectories,
        loading,
    } = useSearchDirectories(value);
    const [results, setResults] = useState();

    useEffect(() => {
        if (
            (directories && directories.length >= 0)
            || (channelDirectories && channelDirectories.length >= 0)
            || (domainDirectories && domainDirectories.length >= 0)) {
            setResults({
                directories: {
                    name: 'Directories',
                    results: directories.map(i => {
                        return {title: i['path']}
                    }),
                },
                channel_directories: {
                    name: 'Channels',
                    results: channelDirectories.map(i => {
                        return {title: i['path'], description: i['name']};
                    }),
                },
                domain_directories: {
                    name: 'Domains',
                    results: domainDirectories.map(i => {
                        return {title: i['path'], description: i['domain']};
                    }),
                }
            });
        }
    }, [
        JSON.stringify(directories),
        JSON.stringify(channelDirectories),
        JSON.stringify(domainDirectories),
        loading,
    ]);

    const handleSearchChange = (e, data) => {
        if (e) {
            e.preventDefault();
        }
        if (onSelect) {
            onSelect('');
        }
        setDirectoryName(data.value);
    }

    const handleResultSelect = (e, data) => {
        if (e) {
            e.preventDefault();
        }
        // title is the relative path.
        if (onSelect) {
            onSelect(data.result.title);
        }
        setDirectoryName(data.result.title);
    }

    const handleClear = (e) => {
        if (e) {
            e.preventDefault();
        }
        onSelect('');
        setDirectoryName('');
    }

    return <Grid>
        <Grid.Row>
            <Grid.Column mobile={13} tablet={14} computer={15}>
                <Search category
                        placeholder='Search directory names...'
                        onSearchChange={handleSearchChange}
                        onResultSelect={handleResultSelect}
                        loading={loading}
                        value={directoryName}
                        results={results}
                        {...props}
                />
            </Grid.Column>
            <Grid.Column mobile={3} tablet={2} computer={1}>
                <Button secondary icon='close' onClick={handleClear}/>
            </Grid.Column>
        </Grid.Row>
    </Grid>
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

    return <div>
        <Input
            action={{
                color: error ? 'red' : 'green', labelPosition: 'left', icon: 'folder', content: media_directory,
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
    </div>;
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
    const zipMimetypes = ['application/zip', 'application/zlib', 'application/x-bzip2', 'application/x-xz', 'application/x-bzip', 'application/x-bzip2', 'application/gzip', 'application/vnd.rar', 'application/x-tar', 'application/x-7z-compressed'];
    const softwareMimetypes = [...zipMimetypes, 'application/x-iso9660-image', 'application/x-executable', 'application/x-dosexec'];

    if (filter === 'video') {
        return ['video'];
    } else if (filter === 'archive') {
        return ['text/html'];
    } else if (filter === 'pdf') {
        return ['application/pdf'];
    } else if (filter === 'audio') {
        return ['audio'];
    } else if (filter === 'ebook') {
        return ['application/epub+zip', 'application/x-mobipocket-ebook'];
    } else if (filter === 'image') {
        return ['image'];
    } else if (filter === 'zip') {
        return zipMimetypes;
    } else if (filter === 'model') {
        return ['application/x-openscad', 'model/stl', 'application/sla', 'model/obj'];
    } else if (filter === 'software') {
        return softwareMimetypes;
    }
}

export const toLocaleString = (num, locale = 'en-US') => {
    return num.toLocaleString(locale);
}

function luma(color) {
    let rgb = (typeof color === 'string') ? hexToRGBArray(color) : color;
    return (0.2126 * rgb[0]) + (0.7152 * rgb[1]) + (0.0722 * rgb[2]); // SMPTE C, Rec. 709 weightings
}

function hexToRGBArray(color) {
    if (color.length === 7) {
        color = color.slice(1);
    }
    if (color.length !== 6) {
        console.error('Invalid hex color: ' + color);
        return;
    }
    let rgb = [];
    for (let i = 0; i <= 2; i++) rgb[i] = parseInt(color.substr(i * 2, 2), 16);
    return rgb;
}

export function contrastingColor(color) {
    return (luma(color) >= 120) ? '#000000' : '#dddddd';
}

export const encodeMediaPath = (path) => {
    // Replace % first to avoid replacing the other replacements.
    path = path.replaceAll('%', '%25');

    path = path.replaceAll('&', '%26');
    path = path.replaceAll('=', '%3d');
    path = path.replaceAll('#', '%23');
    path = path.replaceAll(' ', '%20');
    return path
}

export function SortButton({sorts = []}) {
    const {sort, setSort} = useSearchOrder();

    if (!sorts || (sorts && sorts.length === 0)) {
        console.error('No sorts have been defined!');
    }

    const [localSort, setLocalSort] = useState(sort ? sort.replaceAll(/^-/g, '') : null);
    const [desc, setDesc] = useState(sort ? sort.startsWith('-') : true);
    const [open, setOpen] = useState(false);

    // Remove the - from the front of the query sort, it will be added when toggling direction.
    const sortKey = localSort ? localSort.replaceAll(/^-/g, '') : sorts[0]['value'];
    const selectedSort = sorts.find(i => i['value'] === sortKey);

    useEffect(() => {
        if (localSort) {
            const newSort = desc ? `-${localSort}` : localSort;
            console.debug(`Setting new sort: ${newSort}`)
            setSort(newSort);
        }
    }, [localSort, desc]);

    const handleSortButton = (o) => {
        setLocalSort(o);
        setOpen(false);
    }

    const toggleDesc = () => {
        setDesc(!desc);
        if (!localSort) {
            // No sort in URL, use the first.
            setLocalSort(sorts[0]['value']);
        }
        setOpen(false);
    }

    let sortFields;
    if (sorts && sorts.length) {
        sortFields = sorts.map((i) => {
            return <Button key={i['value']} onClick={() => handleSortButton(i['value'])}>{i['text']}</Button>
        })
    }

    return <>
        <Modal closeIcon
               open={open}
               onClose={() => setOpen(false)}
        >
            <ModalHeader>Sort By</ModalHeader>
            <ModalContent>
                {sortFields}
            </ModalContent>
        </Modal>
        <ButtonGroup icon>
            <Button icon={desc ? 'sort down' : 'sort up'} onClick={() => toggleDesc()}/>
            <Button content={selectedSort['short'] || selectedSort['text']} onClick={() => setOpen(true)}/>
        </ButtonGroup>
    </>
}

export function TagIcon() {
    return <Label circular color='green' style={{padding: '0.5em', marginRight: '0.5em'}}>
        <Icon name='tag' style={{margin: 0}}/>
    </Label>
}

export function normalizeEstimate(estimate) {
    return estimate > 999 ? '>999' : estimate;
}

export function useAPIButton(
    color = 'violet',
    size = 'medium',
    floated,
    onClick,
    disabled,
    confirmContent,
    confirmButton,
    themed = true,
    obeyWROLMode = false,
    icon = null,
    props
) {
    props = props || {};
    const ref = React.useRef();

    const [confirmOpen, setConfirmOpen] = React.useState(false);
    const [pending, setPending] = React.useState(false);
    const [animation, setAnimation] = React.useState('jiggle');
    const [animationVisible, setAnimationVisible] = React.useState(true);
    const [showSuccess, setShowSuccess] = React.useState(false);
    const [showFailure, setShowFailure] = React.useState(false);

    const wrolModeEnabled = useWROLMode();

    // Disable when API call is pending, or button is disabled.
    disabled = pending || disabled;
    // Disable when WROL Mode is enabled, otherwise normal disabled.
    disabled = obeyWROLMode ? wrolModeEnabled || disabled : disabled;

    const reset = () => {
        setShowSuccess(false);
        setShowFailure(false);
    };

    const setSuccess = () => {
        setShowSuccess(true);
        setAnimation('pulse');
        setAnimationVisible(!animationVisible);
        setTimeout(reset, 2000);
    }

    const setFailure = () => {
        setShowFailure(true);
        setAnimation('shake');
        setAnimationVisible(!animationVisible);
        setTimeout(reset, 2000);
    }

    const handleAPICall = async () => {
        // Handle when user clicks button, or clicks confirm.
        setPending(true);
        try {
            await onClick();
            setSuccess();
        } catch (e) {
            console.error(e);
            setFailure();
        }
        setPending(false);
    }

    const localOnClick = async (e) => {
        if (e) {
            e.preventDefault();
        }

        if (confirmContent) {
            // Clicking button opens confirm.
            setConfirmOpen(true);
        } else if (onClick) {
            // No <Confirm/> send the API request.
            await handleAPICall();
        } else {
            throw Error('No onClick defined!');
        }
    }

    const localOnConfirm = async () => {
        // User clicked the "OK" button in the <Confirm/>.
        setConfirmOpen(false);

        if (onClick) {
            await handleAPICall();
        }
    }

    // Create button with or without theme.  Pass all props to the <Button/> (except props.children).
    const buttonArgs = {color, onClick: localOnClick, disabled, loading: pending, size, floated, ...props};

    let buttonContent = props.children || null;
    if (icon) {
        // Send Icon as Button properties.
        buttonContent = null;
        buttonArgs['icon'] = showSuccess ? 'check' : showFailure ? 'close' : icon;
    } else if (showSuccess || showFailure) {
        // Show ✔ or ✖ overtop the contents after API call has completed.
        buttonContent = <>
            <Icon style={{position: 'absolute'}} name={showSuccess ? 'check' : 'close'}/>
            {/* Keep contents to avoid resizing button */}
            <div style={{opacity: 0}}>{buttonContent}</div>
        </>
    }

    let button = themed ?
        <Button ref={ref} {...buttonArgs}>{buttonContent}</Button>
        : <SButton ref={ref} {...buttonArgs}>{buttonContent}</SButton>;
    // Wrap button in <Transition/> to show success or failure animations.
    button = <Transition animation={animation} duration={500} visible={animationVisible}>
        {button}
    </Transition>;

    if (confirmContent) {
        // Wrap button with <Confirm/>
        button = <>
            {button}
            <Confirm open={confirmOpen}
                     content={confirmContent}
                     onClose={() => setConfirmOpen(false)}
                     onCancel={() => setConfirmOpen(false)}
                     onConfirm={localOnConfirm}
                     confirmButton={confirmButton}
            />
        </>
    }

    button = <>
        {button}
    </>

    return {button, ref}
}

export function APIButton({
                              color,
                              size,
                              floated,
                              onClick,
                              disabled,
                              confirmContent,
                              confirmButton,
                              themed,
                              obeyWROLMode,
                              icon,
                              ...props
                          }) {
    const {button} = useAPIButton(
        color,
        size,
        floated,
        onClick,
        disabled,
        confirmContent,
        confirmButton,
        themed,
        obeyWROLMode,
        icon,
        props
    );

    return button;
}

export function InfoMessage({children, size = null}) {
    return <Message info icon size={size}>
        <SIcon name='question'/>
        <Message.Content>
            {children}
        </Message.Content>
    </Message>
}

export function WarningMessage({children, size = null}) {
    return <Message warning icon size={size}>
        <SIcon name='hand point right'/>
        <Message.Content>
            {children}
        </Message.Content>
    </Message>
}

export function ErrorMessage({children, size = null}) {
    return <Message error icon size={size}>
        <SIcon name='exclamation'/>
        <Message.Content>{children}</Message.Content>
    </Message>
}

function levenshteinDistance(a, b) {
    const matrix = [];

    // Initialize the matrix
    for (let i = 0; i <= b.length; i++) {
        matrix[i] = [i];
    }
    for (let j = 0; j <= a.length; j++) {
        matrix[0][j] = j;
    }

    // Populate the matrix
    for (let i = 1; i <= b.length; i++) {
        for (let j = 1; j <= a.length; j++) {
            if (b.charAt(i - 1) === a.charAt(j - 1)) {
                matrix[i][j] = matrix[i - 1][j - 1];
            } else {
                matrix[i][j] = Math.min(matrix[i - 1][j - 1], matrix[i][j - 1], matrix[i - 1][j]) + 1;
            }
        }
    }

    return matrix[b.length][a.length];
}

export function fuzzyMatch(a, b, threshold = 3) {
    return levenshteinDistance(a, b) <= threshold;
}
