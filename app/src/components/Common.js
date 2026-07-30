import React, {useContext, useEffect, useState} from "react";
import {Link, NavLink, useNavigate} from "react-router";
import {
    Accordion,
    Breadcrumbs as UIBreadcrumbs,
    Button,
    ButtonGroup,
    CardGroup,
    Confirm,
    Header,
    Icon,
    IconButton,
    IconStack,
    Label,
    Loading,
    Menu,
    Message,
    Modal,
    Pagination,
    Panel,
    SearchBox,
    Statistic,
    TabBar,
    tabClassName,
    TextInput,
    Toggle as UIToggle,
    Tooltip,
} from "./ui";
import {useBluetooth, useDesktop, useHotspot, useSearchDirectories, useSearchOrder, useThrottle, useVnc, useWROLMode} from "../hooks/customHooks";
import {Media, SettingsContext, StatusContext, ThemeContext} from "../contexts/contexts";
import {themeChoices} from "../themes/names";
import {FilePreviewContext} from "./FilePreview";
import _ from "lodash";
import {killDownloads, startDownloads, unlockCookies} from "../api";
import {allFrequencyOptions, HELP_VIEWER_URI, NAME, validUrlRegex} from "./Vars";

export function Paginator({activePage, onPageChange, totalPages, showFirstAndLast, size = 'mini'}) {
    // Fewer page numbers on a phone: the strip has to fit without wrapping.
    const pager = (siblingRange) => <Pagination
        activePage={activePage}
        totalPages={totalPages}
        onPageChange={onPageChange}
        siblingRange={siblingRange}
        showFirstAndLast={showFirstAndLast}
    />;

    return <>
        <Media at='mobile'>{pager(1)}</Media>
        <Media greaterThanOrEqual='tablet'>{pager(3)}</Media>
    </>
}

export function divmod(x, y) {
    return [Math.floor(x / y), x % y];
}

export function secondsToHumanElapsed(seconds, short = true) {
    // Convert the provided seconds into a human-readable string of the time elapsed between the provided timestamp
    // and now.
    if (!seconds || seconds < 0) {
        return null;
    }

    // Get seconds elapsed between now and `seconds` which is a UTC epoch.
    const localNow = (new Date()).getTime() / 1000;

    let years;
    let days;
    let hours;
    let minutes;

    seconds = Math.abs(localNow - seconds);
    [years, seconds] = divmod(seconds, secondsToYears);
    [days, seconds] = divmod(seconds, secondsToDays);
    [hours, seconds] = divmod(seconds, secondsToHours);
    [minutes, seconds] = divmod(seconds, secondsToMinutes);
    seconds = Math.floor(seconds);

    if (short) {
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
    } else {
        if (years > 0 && days > 30) {
            return `${years} years ${days} days`;
        } else if (years > 0) {
            return `${years} years`;
        } else if (days > 0) {
            return `${days} days`;
        } else if (hours > 0) {
            return `${hours} hours`;
        } else if (minutes > 0) {
            return `${minutes} minutes`;
        }
        return `${seconds} seconds`
    }
}

export function secondsToElapsedPopup(seconds) {
    // Return a Popup which allows the user see a more detailed timestamp when hovering.
    const elapsed = secondsToHumanElapsed(seconds);
    if (!elapsed) {
        return <></>;
    }
    return <Tooltip label={secondsToTimestamp(seconds)}>
        <span>{elapsed}</span>
    </Tooltip>
}

export function isoDatetimeToElapsedPopup(dt) {
    let d = new Date(dt);
    return secondsToElapsedPopup(d.getTime() / 1000);
}

export function isoDatetimeToAgoPopup(dt, short = true) {
    const seconds = (new Date(dt)).getTime() / 1000;
    // Return a Popup which allows the user see a more detailed timestamp when hovering.
    const elapsed = secondsToHumanElapsed(seconds, short);
    if (seconds === 0 || !elapsed) {
        return <></>;
    }
    return <Tooltip label={`${elapsed} ago`}>
        <span>{isoDatetimeToString(dt)}</span>
    </Tooltip>
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
    props = newTab === true ? {...props, target: '_blank', rel: 'noopener noreferrer'} : props;
    return <Link to={to} className="no-link-underscore card-link" {...props}>
        {props.children}
    </Link>
}

export function ExternalCardLink({to, children, ...props}) {
    return <a
        href={to}
        target='_blank'
        rel='noopener noreferrer'
        className='no-link-underscore card-link'
        {...props}
    >
        {children}
    </a>
}

export function PreviewLink({file, children, className, ...props}) {
    const {setPreviewFile} = React.useContext(FilePreviewContext);
    className = className ? `clickable ${className}` : `clickable `;
    return <span className={className} onClick={() => setPreviewFile(file)} {...props}>
        {children}
    </span>
}

export function PreviewPath({path, mimetype, taggable = true, ...props}) {
    return <PreviewLink file={{path, mimetype, taggable}} {...props}/>
}

export function DirectoryLink({path}) {
    if (!path) return <span>Unknown</span>;
    const href = `/media/${encodeMediaPath(path)}/`;
    return <a href={href} target='_blank' rel='noopener noreferrer'
              style={{color: 'inherit', textDecoration: 'none'}}>
        {path}
    </a>
}

export function RequiredAsterisk() {
    return <span style={{color: '#db2828'}}> *</span>
}

/**
 * Format a frequency value (in seconds) to a human-readable string using allFrequencyOptions.
 * @param {number|null} frequency - Frequency in seconds
 * @returns {string} Human-readable frequency text or '-' if null/undefined
 */
export function formatFrequency(frequency) {
    if (frequency === null || frequency === undefined) {
        return '-';
    }
    const option = allFrequencyOptions[frequency];
    return option ? option.text : `${frequency}s`;
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
    // Handle null/undefined
    if (bytes == null) {
        return '-';
    }

    // Convert string to number if needed
    if (typeof bytes === 'string') {
        bytes = parseFloat(bytes);
    }

    // Handle invalid numbers
    if (isNaN(bytes) || !isFinite(bytes)) {
        return '-';
    }

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

/**
 * Shared behaviour for the search inputs: keep a local value so typing is not
 * throttled by the parent, but follow `searchStr` when it changes underneath.
 */
const useSearchValue = (searchStr, onChange) => {
    const [value, setValue] = useState(searchStr || '');

    React.useEffect(() => {
        // `searchStr` is the source of truth from the parent (often an async URL query
        // param).  Depend ONLY on `searchStr` -- never on `value` -- otherwise a transient
        // render where the local `value` has advanced ("ex") but `searchStr` still trails
        // ("e") fires this effect and reverts `value`, garbling fast typing.
        if ((searchStr || '') !== value) {
            setValue(searchStr || '');
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [searchStr]);

    const handleChange = (newValue) => {
        setValue(newValue);
        if (onChange) {
            // Try to call the remote function, don't let its failure break this.
            try {
                onChange(newValue);
            } catch (e) {
                console.error('Call to onChange failed', e);
            }
        }
    }

    return {value, setValue, handleChange};
}

export function SearchInput({
                                searchStr,
                                onSubmit,
                                onChange,
                                onClear,
                                placeholder = 'Search...',
                                inputRef = null,
                                ...props
                            }) {
    const {value, setValue, handleChange} = useSearchValue(searchStr, onChange);

    const handleClear = () => {
        setValue('');
        if (onClear) {
            onClear();
        }
    }

    return <div className='search-container' {...props}>
        <SearchBox
            value={value}
            onChange={handleChange}
            onSubmit={onSubmit}
            onClear={handleClear}
            placeholder={placeholder}
            inputRef={inputRef}
            clearable
        />
    </div>
}

export function SearchResultsInput({
                                       searchStr,
                                       onSubmit,
                                       onClear = null,
                                       onChange = null,
                                       placeholder = 'Search...',
                                       clearable = false,
                                       clearDisabled = null,
                                       results = undefined,
                                       handleResultSelect = null,
                                       resultRenderer = undefined,
                                       loading = false,
                                       inputRef = null,
                                       autoFocus = false,
                                       ...props
                                   }) {
    const {value, setValue, handleChange} = useSearchValue(searchStr, onChange);

    const handleClear = () => {
        setValue('');
        if (onClear) {
            onClear();
        }
    }

    const localHandleResultSelect = (result) => {
        if (handleResultSelect) {
            // Semantic handed its callers `{result}`, and they destructure it -- passing the
            // bare result silently broke navigation from the search suggestions.  The shape
            // stays until the call sites are ready to change together.
            handleResultSelect({result});
        } else {
            console.error('No handleResultSelect defined!');
        }
    }

    return <div className='search-container' {...props}>
        <SearchBox
            value={value}
            onChange={handleChange}
            onSubmit={onSubmit}
            onResultSelect={localHandleResultSelect}
            onClear={handleClear}
            results={results}
            resultRenderer={resultRenderer}
            loading={loading}
            placeholder={placeholder}
            clearable={clearable}
            clearDisabled={clearDisabled}
            inputRef={inputRef}
            autoFocus={autoFocus}
        />
    </div>
}

export function WROLModeMessage({content}) {
    const wrolModeEnabled = useWROLMode();

    if (wrolModeEnabled) {
        return <Message kind='warning' icon='lock' title='WROL Mode Enabled'>{content}</Message>
    }
    return null;
}

export function DownloadWindowMessage() {
    const {status} = React.useContext(StatusContext);
    const downloads = status ? status.downloads : null;

    if (downloads && downloads.outside_download_window) {
        return <Message kind='info' icon='history' title='Outside Download Window'>
            Downloads are paused because the current time is outside the configured download window.
        </Message>
    }
    return null;
}

export function DailyLimitMessage() {
    const {status} = React.useContext(StatusContext);
    const downloads = status ? status.downloads : null;

    if (downloads && downloads.daily_limit_reached && !downloads.disabled && !downloads.stopped) {
        return <Message kind='info' icon='stop' title='Max Daily Downloads Reached'>
            Downloads are paused because the daily download limit has been reached. Downloads will
            resume tomorrow.
        </Message>
    }
    return null;
}

export function CookiesUnlockModal({open, onClose, onSuccess}) {
    const [password, setPassword] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const passwordRef = React.useRef(null);

    useEffect(() => {
        if (open) {
            const timer = setTimeout(() => {
                if (passwordRef.current) {
                    passwordRef.current.focus();
                }
            }, 100);
            return () => clearTimeout(timer);
        }
    }, [open]);

    const handleUnlock = async () => {
        setSubmitting(true);
        const result = await unlockCookies(password);
        setSubmitting(false);
        if (result.success) {
            setPassword('');
            if (onSuccess) onSuccess();
            onClose();
        }
    };

    return <Modal open={open} onClose={onClose} size='tiny'>
        <Modal.Header>Unlock Cookies</Modal.Header>
        <Modal.Content>
            <TextInput
                ref={passwordRef}
                label='Password'
                type='password'
                placeholder='Enter your encryption password'
                value={password}
                onChange={(e) => setPassword(e.currentTarget.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleUnlock()}
            />
        </Modal.Content>
        <Modal.Actions>
            <Button role='cancel' onClick={onClose}>Cancel</Button>
            <Button
                role='save'
                icon='unlock'
                onClick={handleUnlock}
                loading={submitting}
                disabled={!password || submitting}
            >
                Unlock
            </Button>
        </Modal.Actions>
    </Modal>;
}

export function CookiesLockedMessage() {
    const {settings} = React.useContext(SettingsContext);
    const {status} = React.useContext(StatusContext);
    const flags = status?.flags || {};

    const [modalOpen, setModalOpen] = useState(false);

    if (!flags.cookies_exist || flags.cookies_unlocked || settings?.wrol_mode) {
        return null;
    }

    return <>
        <Message kind='warning' icon='lock' title='Cookies Locked'>
            You have encrypted cookies stored, but they are currently locked.
            <Button role='cancel' icon='unlock' size='xs' style={{marginLeft: '0.7em'}}
                    onClick={() => setModalOpen(true)}>
                Unlock Cookies
            </Button>
        </Message>

        <CookiesUnlockModal open={modalOpen} onClose={() => setModalOpen(false)}/>
    </>;
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

export function TabLinks({links, right}) {
    return <TabBar right={right}>
        {links.map((link) => <NavLink
            to={link.to}
            key={link.to}
            end={link.end === true ? true : null}
            className={({isActive}) => tabClassName(link.isActive ? link.isActive() : isActive)}
        >
            {link.text}
        </NavLink>)}
    </TabBar>
}

export function PageContainer(props) {
    return <>
        <Media at='mobile'>
            <div style={{marginTop: '1em', padding: 0}}>{props.children}</div>
        </Media>
        <Media greaterThanOrEqual='tablet'>
            <div style={{marginTop: '1em', padding: '1em'}}>{props.children}</div>
        </Media>
    </>;
}

export function CardGroupCentered(props) {
    // One responsive grid; it centres what it cannot fill, so the two viewports no
    // longer need separate markup.
    return <div style={{marginTop: '1em'}}>
        <CardGroup>{props.children}</CardGroup>
    </div>
}

/**
 * Resolve a filename-only path to a full relative path using the file's directory.
 * Paths in FileGroup.data are stored as filenames only for performance (fast moves/renames).
 * This function resolves them to full relative paths suitable for /media/ URLs.
 *
 * @param {string} path - The path to resolve (may be filename-only or already a full path)
 * @param {string} directory - The directory to prepend if path is filename-only
 * @returns {string|null} - The resolved path, or null if path is falsy
 */
export function resolveDataPath(path, directory) {
    if (!path) return null;
    if (path.includes('/')) return path;  // Already a full relative path
    return directory ? `${directory}/${path}` : path;
}

export function findPosterPath(file) {
    if (!file) {
        return;
    }
    const {files, poster_path, cover_path, screenshot_path, video, directory} = file;

    if (poster_path) {
        return poster_path;
    }
    if (cover_path) {
        return cover_path;
    }
    if (screenshot_path) {
        return screenshot_path;
    }
    // video.poster_path is already a full relative path (from Video.__json__)
    if (video && video['poster_path']) {
        return video['poster_path'];
    }
    // data paths are filename-only, need to resolve with directory
    if (file['data'] && file['data']['cover_path']) {
        // Ebook.
        return resolveDataPath(file['data']['cover_path'], directory);
    }
    if (file['data'] && file['data']['poster_path']) {
        // PDF or Video (cached).
        return resolveDataPath(file['data']['poster_path'], directory);
    }
    if (file['data'] && file['data']['screenshot_path']) {
        // Archive.
        return resolveDataPath(file['data']['screenshot_path'], directory);
    }
    // files[].path is already resolved by my_files() on the backend
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
    // Used to center posters in CardIcon.
    const style = {display: 'flex', justifyContent: 'center'};
    const navigate = useNavigate();

    // Marks a tagged file, pinned to the poster's corner.
    const cardTagIcon = <div className='wrolpi-card-tag'><Icon name='tag' size={14} label='Tagged'/></div>;
    let imageLabel = !_.isEmpty(file.tags) ? cardTagIcon : null;

    let posterPath = findPosterPath(file);

    if (posterPath) {
        // FileGroup has a poster (screenshot/thumbnail) file.
        posterPath = `/media/${encodeMediaPath(posterPath)}`;

        const image = <>
            {/* Replicate <Image label/> but with maxHeight applied to image */}
            {imageLabel}
            <img alt='poster' src={posterPath} style={{maxHeight: '163px', maxWidth: '290px', width: 'auto'}}/>
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
                <div className='wrolpi-card-icon'>
                    {imageLabel}
                    <FileIcon file={file}/>
                </div>
            </PreviewLink>
        } else if (!posterPath && to) {
            // Link to the full page in this App.
            return <Link to={to}>
                <div className='wrolpi-card-icon' onClick={() => navigate(to)}>
                    {imageLabel}
                    <FileIcon file={file}/>
                </div>
            </Link>
        }
    }
}

export function InfoPopup({
                              icon = 'info circle',
                              size = null,
                              content,
                              position = 'left center',
                              iconSize = null,
                              header = '',
                              iconStyle = { margin: '0.5em'},
                              ...props
                          }) {
    return <Tooltip label={header ? <><strong>{header}</strong><br/>{content}</> : content}
                    multiline w={260} {...props}>
        <span style={iconStyle}><Icon name={icon} size={iconSize || 'small'}/></span>
    </Tooltip>
}

export function InfoHeader({
                               icon,
                               headerSize = 'h2',
                               iconSize,
                               headerContent,
                               popupContent,
                               popupPosition = null,
                               popupProps = {},
                               for_ = null,
                               required = false,
                               ...props
                           }) {
    return <div className='inline-header' {...props}>
        <label htmlFor={for_}>
            <Header as={headerSize}>{headerContent} {required && <RequiredAsterisk/>}</Header>
        </label>
        <span>
            <InfoPopup content={popupContent} iconSize={iconSize} icon={icon} position={popupPosition} {...popupProps}/>
        </span>
    </div>
}

export function HelpModal({
                              icon = 'help circle',
                              iconSize = null,
                              iconStyle = {margin: '0.5em'},
                              helpPath,
                              title = null,
                              modalSize = 'fullscreen',
                          }) {
    const [open, setOpen] = useState(false);
    const src = `${HELP_VIEWER_URI}${helpPath}`;
    const style = {position: 'relative', height: '75vh', width: '100%', border: 'none'};

    return <>
        <IconButton icon={icon} label={title || 'Help'} variant='subtle'
                    style={iconStyle} onClick={() => setOpen(true)}/>
        <Modal open={open} onClose={() => setOpen(false)} size={modalSize} closeIcon>
            {title && <Modal.Header>{title}</Modal.Header>}
            <Modal.Content>
                <IframeViewer title={title} src={src} style={style}/>
            </Modal.Content>
        </Modal>
    </>
}

export function HelpHeader({
                                icon,
                                headerSize = 'h2',
                                iconSize,
                                headerContent,
                                helpPath,
                                helpTitle,
                                helpModalProps = {},
                                for_ = null,
                                required = false,
                                ...props
                            }) {
    return <div className='inline-header' {...props}>
        <label htmlFor={for_}>
            <Header as={headerSize}>{headerContent} {required && <RequiredAsterisk/>}</Header>
        </label>
        <span>
            <HelpModal helpPath={helpPath} iconSize={iconSize} icon={icon} title={helpTitle} {...helpModalProps}/>
        </span>
    </div>
}

// All the hardware toggles share this shape: a Toggle whose state comes from a
// subsystem hook, disabled when the status is unknown, with an InfoPopup explaining
// why it cannot be used.  `confirmStop` asks before switching off.
function SubsystemToggle({label, on, onChange, unsupportedMessage, info = null, disabled = null, confirmStop = null}) {
    const [confirmOpen, setConfirmOpen] = React.useState(false);
    const unsupported = on === null;

    const handleChange = (checked) => {
        if (!checked && confirmStop) {
            setConfirmOpen(true);
        } else {
            onChange(checked);
        }
    }

    const handleConfirm = (e) => {
        if (e) {
            e.preventDefault()
        }
        setConfirmOpen(false);
        onChange(false);
    }

    const popup = unsupported ? unsupportedMessage : info;

    return <div style={{margin: '0.5em'}}>
        {confirmStop && <Confirm
            open={confirmOpen}
            onCancel={() => setConfirmOpen(false)}
            onConfirm={handleConfirm}
            title={confirmStop.header}
            confirmLabel={confirmStop.button}
            destructive
        >
            {confirmStop.content}
        </Confirm>}
        <Toggle
            label={label}
            disabled={disabled === null ? unsupported : disabled}
            checked={on === true}
            onChange={handleChange}
        />
        {popup && <InfoPopup content={popup}/>}
    </div>;
}

export function HotspotToggle() {
    const {on, setHotspot} = useHotspot();
    return <SubsystemToggle
        label='WiFi Hotspot'
        on={on}
        onChange={setHotspot}
        unsupportedMessage='Hotspot is not supported on this server'
    />;
}

export function ThrottleToggle() {
    const {on, setThrottle} = useThrottle();
    return <SubsystemToggle
        label='CPU Power-save'
        on={on}
        onChange={setThrottle}
        unsupportedMessage='CPU Power-save is not supported on this server'
    />;
}

export function BluetoothToggle() {
    const {on, setBluetooth} = useBluetooth();
    return <SubsystemToggle
        label='Bluetooth'
        on={on}
        onChange={setBluetooth}
        unsupportedMessage='Bluetooth is not supported on this server'
    />;
}

export function DesktopToggle() {
    const {on, setDesktop} = useDesktop();
    return <SubsystemToggle
        label='Desktop'
        on={on}
        onChange={setDesktop}
        unsupportedMessage='The Desktop is not supported on this server'
        // Stopping the desktop kills any session on this WROLPi's own screen.
        confirmStop={{
            header: 'Stop the desktop',
            content: "Anyone using this WROLPi's own screen will lose their session and the display will"
                + ' drop to a terminal. The desktop will return on the next reboot. Are you sure?',
            button: 'Stop',
        }}
    />;
}

export function VncToggle() {
    const {on, desktopRunning, setVnc} = useVnc();
    const unsupported = on === null;
    // VNC serves the desktop session; it cannot be started without one.  Stopping
    // stays available so a running VNC server is never stranded on.
    const blockedByDesktop = !desktopRunning && on !== true;

    let info = null;
    if (blockedByDesktop) {
        info = 'Start the Desktop before starting VNC';
    } else if (on === true && !desktopRunning) {
        info = 'The Desktop is stopped, so VNC clients will see nothing';
    }

    return <SubsystemToggle
        label='VNC'
        on={on}
        onChange={setVnc}
        unsupportedMessage='VNC is not supported on this server'
        info={info}
        disabled={unsupported || blockedByDesktop}
    />;
}

export function Toggle({label, checked, disabled, onChange, icon, popupContent = null, info = null}) {
    // Keeps this call signature -- `onChange` receives the new boolean, not an event --
    // because a dozen call sites are written against it.
    const body = <span style={{display: 'inline-flex', alignItems: 'center', gap: 6}}>
        <UIToggle
            label={<span style={{display: 'inline-flex', alignItems: 'center', gap: 6}}>
                {icon && <Icon name={icon}/>}
                {label}
            </span>}
            checked={checked === true}
            disabled={disabled === true}
            onChange={(e) => onChange && onChange(e.currentTarget.checked)}
            data-testid='toggle'
        />
        {info && <InfoPopup content={info}/>}
    </span>;

    if (popupContent) {
        return <Tooltip label={popupContent}>{body}</Tooltip>
    }
    return body
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
    return <Toggle
        label={on === true ? 'Downloading Enabled' : 'Downloading Disabled'}
        disabled={wrolModeEnabled || pending || downloads === null}
        checked={on === true}
        onChange={setDownloads}
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

export function mimetypeColor(mimetype, path = '') {
    if (!mimetype) {
        return 'grey';
    }
    try {
        const lowerPath = path.toLowerCase();
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
        } else if (mimetype.includes('cbz') || mimetype.includes('cbr')
            || mimetype.includes('comicbook')
            || lowerPath.endsWith('.cbz') || lowerPath.endsWith('.cbr')
            || lowerPath.endsWith('.cbt') || lowerPath.endsWith('.cb7')) {
            return 'yellow'
        } else if (mimetype.startsWith('audio/')) {
            return 'violet'
        } else if (mimetype.startsWith('model/') || mimetype.startsWith('application/x-openscad') || mimetype.startsWith('application/sla')
            || lowerPath.endsWith('.stl') || lowerPath.endsWith('.3mf') || lowerPath.endsWith('.obj') || lowerPath.endsWith('.scad')) {
            return 'teal'
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

export function isSupportedArchive(mimetype, lowerPath) {
    // Zip is always supported.
    if (mimetype.startsWith('application/zip') || mimetype.startsWith('application/zlib')) return true;
    if (mimetype.startsWith('application/x-tar')) return true;
    // Suffix-based detection for tar variants whose mimetype may be the compression type.
    if (lowerPath.endsWith('.tar') || lowerPath.endsWith('.tar.gz') || lowerPath.endsWith('.tgz') || lowerPath.endsWith('.tar.bz2') || lowerPath.endsWith('.tar.xz')) return true;
    // 7z and RAR archives.
    if (mimetype.startsWith('application/x-7z-compressed')) return true;
    if (mimetype.startsWith('application/x-rar') || mimetype.startsWith('application/vnd.rar')) return true;
    if (lowerPath.endsWith('.7z') || lowerPath.endsWith('.rar')) return true;
    return false;
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
        } else if (mimetype.startsWith('application/x-openscad') || mimetype.startsWith('model/')
            || lowerPath.endsWith('.stl') || lowerPath.endsWith('.3mf') || lowerPath.endsWith('.obj') || lowerPath.endsWith('.scad')) {
            return 'cube';
        } else if (isZipMimetype(mimetype)) {
            return 'file archive';
        } else if (mimetype.startsWith('application/x-iso9660-image') || mimetype.startsWith('application/x-raw-disk-image') || mimetype.startsWith('application/x-cd-image')) {
            return 'dot circle';
        } else if (mimetype.startsWith('application/epub') || mimetype.startsWith('application/x-mobipocket-ebook') || mimetype.startsWith('application/vnd.amazon.mobi8-ebook')
            || mimetype.startsWith('application/vnd.comicbook') || mimetype.startsWith('application/x-cbz') || mimetype.startsWith('application/x-cbr')) {
            return 'book';
        } else if (mimetype.startsWith('text/vtt') || mimetype.startsWith('text/srt')) {
            return 'closed captioning';
        } else if (mimetype.startsWith('application/x-dosexec') || mimetype.startsWith('application/x-msi') || mimetype.startsWith('application/vnd.microsoft.portable-executable')) {
            return 'windows';
        } else if (mimetype.startsWith('audio/')) {
            return 'file audio';
        } else if (mimetype.startsWith('application/vnd.openxmlformats-officedocument.wordprocessingml.document')) {
            return 'file word';
        } else if (mimetype.startsWith('application/x-x509-ca-cert')) {
            return 'certificate';
        } else if (mimetype.startsWith('application/x-pie-executable')) {
            return 'linux';
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

const SUFFIX_ICON_MAP = {
    // Code
    html: 'file code', htm: 'file code', json: 'file code', xml: 'file code',
    yaml: 'file code', yml: 'file code', js: 'file code', css: 'file code',
    py: 'file code', sh: 'file code', c: 'file code', cpp: 'file code',
    h: 'file code', java: 'file code', rs: 'file code', go: 'file code',
    ts: 'file code', tsx: 'file code', jsx: 'file code',
    // Documents
    pdf: 'file pdf',
    txt: 'file text', md: 'file text', csv: 'file text', log: 'file text', rst: 'file text',
    doc: 'file word', docx: 'file word', odt: 'file word',
    xls: 'file excel', xlsx: 'file excel', ods: 'file excel',
    ppt: 'file powerpoint', pptx: 'file powerpoint', odp: 'file powerpoint',
    // Media
    jpg: 'image', jpeg: 'image', png: 'image', gif: 'image', svg: 'image',
    bmp: 'image', webp: 'image', ico: 'image', tiff: 'image',
    mp4: 'film', mkv: 'film', avi: 'film', mov: 'film', wmv: 'film', webm: 'film', flv: 'film',
    mp3: 'file audio', wav: 'file audio', flac: 'file audio', ogg: 'file audio',
    aac: 'file audio', wma: 'file audio', m4a: 'file audio',
    vtt: 'closed captioning', srt: 'closed captioning',
    // Archives
    zip: 'file archive', tar: 'file archive', gz: 'file archive', bz2: 'file archive',
    xz: 'file archive', '7z': 'file archive', rar: 'file archive', tgz: 'file archive',
    // Books
    epub: 'book', mobi: 'book', azw3: 'book',
    // 3D
    stl: 'cube', blend: 'cube', scad: 'cube',
    // Platform
    exe: 'windows', msi: 'windows',
    dmg: 'apple',
    iso: 'dot circle', img: 'dot circle',
    // Certs
    pem: 'certificate', crt: 'certificate', cer: 'certificate',
    // Email
    eml: 'mail',
};

export function fileSuffixIconName(filename) {
    const dot = filename.lastIndexOf('.');
    if (dot >= 0) {
        const ext = filename.substring(dot + 1).toLowerCase();
        return SUFFIX_ICON_MAP[ext] || 'file';
    }
    return 'file';
}

export function FileIcon({file, disabled = true, size = 48, ...props}) {
    const {mimetype, path, primary_path} = file;
    // `file` may be a file_group or a file.
    const lowerPath = primary_path ? primary_path.toLocaleString() : path.toLowerCase();
    const name = mimetypeIconName(mimetype, lowerPath);
    // The mimetype picks a hue; the token picks what that hue is in this theme.
    const color = mimetypeColor(mimetype, lowerPath);
    return <Icon
        name={name}
        size={size}
        style={{color: `var(--${color})`, opacity: disabled ? 0.75 : 1}}
        {...props}
    />
}

export function LoadStatistic({label, value, cores, ...props}) {
    // Load is a warning above half the cores, and a problem above three quarters.
    const quarter = cores / 4;
    let color;
    if (cores && value >= (quarter * 3)) {
        color = 'red';
    } else if (cores && value >= (quarter * 2)) {
        color = 'orange';
    }
    return <Statistic
        label={label}
        value={value ? parseFloat(value).toFixed(1) : '?'}
        color={color}
        {...props}/>;
}

export function DarkModeToggle() {
    const {savedTheme, setTheme} = useContext(ThemeContext);
    const active = themeChoices.find(i => i.value === savedTheme) || themeChoices[0];

    return <Menu position='bottom-end' withinPortal>
        <Menu.Target>
            <IconButton
                icon={active.icon}
                label={`Theme: ${active.text}`}
                variant='subtle'
                style={{marginRight: '0.8em'}}
            />
        </Menu.Target>
        <Menu.Dropdown>
            <Menu.Label>Theme</Menu.Label>
            {themeChoices.map(choice => <Menu.Item
                key={choice.value}
                leftSection={<Icon name={choice.icon}/>}
                onClick={() => setTheme(choice.value)}
                // The chosen theme is marked by weight as well as color, so the mark
                // survives in the monochrome themes.
                style={choice.value === active.value ? {fontWeight: 700} : undefined}
            >
                {choice.text}
            </Menu.Item>)}
        </Menu.Dropdown>
    </Menu>
}


export function UnsupportedModal(header, message, icon) {
    const [open, setOpen] = useState(false);
    const onOpen = () => setOpen(true);
    const onClose = () => setOpen(false);

    const modal = <Modal open={open} onClose={onClose} size='tiny'>
        <Modal.Header>
            <span style={{display: 'inline-flex', alignItems: 'center', gap: 8}}>
                <Icon name={icon || 'exclamation triangle'}/>
                {header || 'Unsupported'}
            </span>
        </Modal.Header>
        <Modal.Content>{message}</Modal.Content>
        <Modal.Actions>
            <Button role='cancel' onClick={onClose}>Ok</Button>
        </Modal.Actions>
    </Modal>;

    return {modal, doClose: onClose, doOpen: onOpen};
}

/**
 * The hotspot glyph in the nav bar: a wifi icon with a corner mark for the state.
 * A button, not an anchor -- every one of these opens a dialog or toggles the
 * hotspot, and `<a href='#'>` was neither keyboard-honest nor navigable.
 */
function HotspotButton({label, corner, on, onClick}) {
    const wifi = <Icon name='wifi' size='large' style={{opacity: on ? 1 : 0.55}}/>;
    return <IconButton label={label} variant='subtle' onClick={onClick} icon={() =>
        corner
            ? <IconStack corner={<Icon name={corner} size={12}/>} label={label}>{wifi}</IconStack>
            : wifi
    }/>
}

export function HotspotStatusIcon() {
    const {on, inUse, setHotspot, dockerized, hotspotSsid} = useHotspot();
    const {modal: unsupportedModal, doOpen: openUnsupportedModal} =
        UnsupportedModal('Unsupported', 'You cannot toggle the hotspot on this machine.');
    const [stopHotspotOpen, setStopHotspotOpen] = React.useState(false);
    const [inUseOpen, setInUseOpen] = React.useState(false);

    const handleConfirmStop = (e) => {
        if (e) {
            e.preventDefault()
        }
        setStopHotspotOpen(false);
        setHotspot(false);
    }

    const handleConfirmInUse = (e) => {
        if (e) {
            e.preventDefault()
        }
        setInUseOpen(false);
        setHotspot(true);
    }

    if (inUse === true) {
        const content = hotspotSsid ? `Wifi device is in use for ${hotspotSsid}.  Disconnect and start hotspot?`
            : 'Wifi device is in use.  Disconnect and start hotspot?'
        return <>
            <Confirm open={inUseOpen}
                     onCancel={() => setInUseOpen(false)}
                     onConfirm={handleConfirmInUse}
                     title='Wifi is in-use'
                     confirmLabel='Start Hotspot'
            >
                {content}
            </Confirm>
            <HotspotButton label='Wifi is in use; start the hotspot' corner='exclamation'
                           onClick={() => setInUseOpen(true)}/>
        </>
    } else if (dockerized === false && on === true) {
        return <>
            <Confirm
                open={stopHotspotOpen}
                onCancel={() => setStopHotspotOpen(false)}
                onConfirm={handleConfirmStop}
                title='Stop the hotspot'
                confirmLabel='Stop'
                destructive
            >
                You will be disconnected when using the hotspot. Are you sure?
            </Confirm>
            <HotspotButton label='Hotspot is on; stop it' on
                           onClick={() => setStopHotspotOpen(true)}/>
        </>
    } else if (dockerized === false && on === false) {
        return <HotspotButton label='Hotspot is off; start it' corner='x'
                              onClick={() => setHotspot(true)}/>
    }

    // Hotspot is not available, or, status has not yet been fetched.
    return <>
        <HotspotButton label='Hotspot status is unknown' corner='question'
                       onClick={openUnsupportedModal}/>
        {unsupportedModal}
    </>
}

export function useMediaSession(title, artist, artworkUrl) {
    useEffect(() => {
        if ('mediaSession' in navigator && title) {
            const artwork = [];
            if (artworkUrl) {
                artwork.push({src: artworkUrl, type: 'image/jpeg'});
            }

            navigator.mediaSession.metadata = new MediaMetadata({
                title: title,
                artist: artist || '',
                artwork: artwork,
            });
        }
    }, [title, artist, artworkUrl]);
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

export function DirectorySearch({onSelect, value, disabled, required, ...props}) {
    const {
        directoryName,
        setDirectoryName,
        directories,
        channelDirectories,
        domainDirectories,
        isDir,
        loading,
    } = useSearchDirectories(value);
    const [results, setResults] = useState({});

    useEffect(() => {
        if (directories && directories.length >= 0) {
            const newDirectory = isDir ? {} : {
                newDirectory: {
                    name: 'New Directory',
                    results: [{title: directoryName || ''}],
                }
            };
            const newResults = {
                ...newDirectory,
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
                },
            };
            setResults(newResults);
        }
    }, [
        JSON.stringify(directories),
        JSON.stringify(channelDirectories),
        JSON.stringify(domainDirectories),
        loading,
    ]);

    const handleSearchChange = (value) => {
        setDirectoryName(value);
    }

    const handleResultSelect = (result) => {
        setDirectoryName(result.title);
        // title is the relative path.
        if (onSelect) {
            onSelect(result.title);
        }
    }

    const handleBlur = (e) => {
        // When user leaves the field, commit the typed value to the form
        if (onSelect && directoryName !== value) {
            onSelect(directoryName);
        }
    }

    return <SearchBox
        placeholder='Search directory names...'
        onChange={handleSearchChange}
        onResultSelect={handleResultSelect}
        onBlur={handleBlur}
        loading={loading}
        value={directoryName || ''}
        results={results}
        disabled={disabled}
        required={required}
        {...props}
    />
}

export const BackButton = ({...props}) => {
    const navigate = useNavigate();
    return <Button role='cancel' icon='arrow left' onClick={() => navigate(-1)} {...props}>Back</Button>;
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
    } else if (filter === 'doc') {
        return ['application/epub+zip', 'application/x-mobipocket-ebook', 'application/pdf',
            'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.oasis.opendocument.text', 'application/x-cbz', 'application/x-cbr'];
    } else if (filter === 'image') {
        return ['image'];
    } else if (filter === 'zip') {
        return zipMimetypes;
    } else if (filter === 'model') {
        return ['application/x-openscad', 'model/stl', 'application/sla', 'model/obj', 'model/3mf'];
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
            return <Button key={i['value']} role='cancel' fullWidth
                           onClick={() => handleSortButton(i['value'])}>{i['text']}</Button>
        })
    }

    return <>
        <Modal closeIcon
               open={open}
               onClose={() => setOpen(false)}
        >
            <Modal.Header>Sort By</Modal.Header>
            <Modal.Content>
                {sortFields}
            </Modal.Content>
        </Modal>
        <ButtonGroup>
            <IconButton
                icon={desc ? 'arrow down' : 'arrow up'}
                label={desc ? 'Sort descending' : 'Sort ascending'}
                onClick={() => toggleDesc()}
            />
            <Button role='cancel' onClick={() => setOpen(true)}>
                {selectedSort['short'] || selectedSort['text']}
            </Button>
        </ButtonGroup>
    </>
}

export function TagIcon() {
    return <Label color='green' icon='tag' className='wrolpi-tag-icon'/>
}

export function normalizeEstimate(estimate) {
    if (Number.isInteger(estimate)) {
        return estimate > 999 ? '>999' : estimate.toString();
    }
    return '?';
}

export function useAPIButton(
    color = 'violet',
    size = 'medium',
    floated,
    onClick,
    disabled,
    confirmContent,
    confirmButton,
    confirmHeader,
    themed = true,
    obeyWROLMode = false,
    icon = null,
    type = 'button',
    id = null,
    props
) {
    props = props || {};
    const ref = React.useRef();

    const [confirmOpen, setConfirmOpen] = React.useState(false);
    const [loading, setLoading] = React.useState(false);
    const [showSuccess, setShowSuccess] = React.useState(false);
    const [showFailure, setShowFailure] = React.useState(false);

    const wrolModeEnabled = useWROLMode();

    // Disable when API call is pending, or button is disabled.
    disabled = loading || disabled;
    // Disable when WROL Mode is enabled, otherwise normal disabled.
    disabled = obeyWROLMode ? wrolModeEnabled || disabled : disabled;

    const reset = () => {
        setShowSuccess(false);
        setShowFailure(false);
    };

    const setSuccess = () => {
        setShowSuccess(true);
        setTimeout(reset, 2000);
    }

    const setFailure = () => {
        setShowFailure(true);
        setTimeout(reset, 2000);
    }

    const handleAPICall = async () => {
        // Handle when user clicks button, or clicks confirm.
        setLoading(true);
        try {
            await onClick();
            setSuccess();
        } catch (e) {
            console.error(e);
            setFailure();
        } finally {
            setLoading(false);
        }
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

    // `color` was a Semantic color name; a role carries the meaning instead, and a
    // caller that really wants a color can still pass one through `props`.
    const buttonArgs = {
        onClick: localOnClick, disabled, loading, type,
        ...props,
    };
    if (id) {
        buttonArgs['id'] = id;
    }
    if (!props.color && !props.role) {
        buttonArgs['role'] = 'primary';
    }

    // The result is shown as the icon rather than an animation: the outcome should be
    // legible at a glance, and in night mode a moving element is the last thing wanted.
    const outcomeIcon = showSuccess ? 'check' : showFailure ? 'close' : null;
    const outcomeColor = showSuccess ? 'green' : showFailure ? 'red' : undefined;
    if (outcomeColor) {
        buttonArgs['color'] = outcomeColor;
    }

    let buttonContent = props.children || null;
    if (icon) {
        // Icon-only: swap the glyph for the outcome.
        buttonArgs['icon'] = outcomeIcon || icon;
    } else if (outcomeIcon) {
        buttonArgs['icon'] = outcomeIcon;
    }

    let button = <Button ref={ref} {...buttonArgs}>{buttonContent}</Button>;

    if (confirmContent) {
        // Wrap button with <Confirm/>
        button = <>
            {button}
            <Confirm open={confirmOpen}
                     onCancel={() => setConfirmOpen(false)}
                     onConfirm={localOnConfirm}
                     confirmLabel={confirmButton}
                     title={confirmHeader}
                     destructive
            >
                {confirmContent}
            </Confirm>
        </>
    }

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
                              confirmHeader,
                              themed,
                              obeyWROLMode,
                              icon,
                              type = 'button',
                              id = null,
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
        confirmHeader,
        themed,
        obeyWROLMode,
        icon,
        type,
        id,
        props
    );

    return button;
}

export const useMessageDismissal = (messageName) => {
    const [dismissed, setDismissed] = useLocalStorage('dismissed_hints', {});

    return {
        dismissed: dismissed[messageName] || false, // true or false
        setDismissed: (value) => setDismissed({...dismissed, [messageName]: !!value}), // force true/false
        clearAll: () => setDismissed({}),
    }
}

/** A dismissible note.  `storageName` makes the dismissal stick across reloads. */
function DismissibleMessage({kind, icon, children, storageName}) {
    const {dismissed, setDismissed} = useMessageDismissal(storageName);

    if (dismissed) {
        return <React.Fragment/>
    }

    return <Message
        kind={kind}
        icon={icon}
        onDismiss={storageName ? () => setDismissed(true) : undefined}
    >
        {children}
    </Message>
}

export function InfoMessage({children, size = null, storageName = null, icon = 'warning circle'}) {
    return <DismissibleMessage kind='info' icon={icon} storageName={storageName}>
        {children}
    </DismissibleMessage>
}

export function HandPointMessage({children, size = null, storageName = null}) {
    return <DismissibleMessage kind='info' icon='hand point right' storageName={storageName}>
        {children}
    </DismissibleMessage>
}

export function WarningMessage({children, size = null, icon = 'exclamation', storageName = null}) {
    return <DismissibleMessage kind='warning' icon={icon} storageName={storageName}>
        {children}
    </DismissibleMessage>
}

export function ErrorMessage({children, size = null, icon = 'exclamation', storageName = null}) {
    return <DismissibleMessage kind='error' icon={icon} storageName={storageName}>
        {children}
    </DismissibleMessage>
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

export function useIsIgnoredDirectory(directory) {
    const {settings} = React.useContext(SettingsContext);

    if (!settings || _.isEmpty(settings)) {
        // Settings have not yet been fetched.
        return false;
    }

    let ignoredDirectories = settings['ignored_directories'];
    if (directory.endsWith('/')) {
        ignoredDirectories = ignoredDirectories.map(i => `${i}/`);
    }

    return ignoredDirectories.indexOf(directory) >= 0;
}

export function getParentDirectory(filePath) {
    // Remove trailing slashes for consistency
    const normalizedPath = filePath.endsWith('/') ? filePath.slice(0, -1) : filePath;

    // Find the last occurrence of "/" and extract the substring up to it
    const parentDirectory = normalizedPath.substring(0, normalizedPath.lastIndexOf('/'));

    return parentDirectory;
}

export function MultilineText({text, ...props}) {
    return <div {...props}>
        {text.split('\n').map((line, index, array) =>
            index === array.length - 1 ? line : <p key={index}>{line}</p>
        )}
    </div>
}

export const monthNames = [
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
];

export function IframeViewer({title, src, fallback, style, timeout = 5000}) {
    // This function checks that an iframe can be fetched before displaying it.  Otherwise, it will display the fallback
    // element which should help the maintainer to fix the issue.
    const [contentAvailable, setContentAvailable] = useState(false);
    const [loading, setLoading] = useState(true);

    fallback = fallback || <pre>Frame could not load.</pre>;

    useEffect(() => {
        const controller = new AbortController();  // To manage fetch timeout
        const timeoutId = setTimeout(() => {
            controller.abort();  // Abort the fetch after 5 seconds
        }, timeout);

        fetch(src, {signal: controller.signal})
            .then(response => {
                // Only display content if it can be fetched.
                setContentAvailable(response.ok);
            })
            .catch(() => {
                setContentAvailable(false);  // Handle fetch errors (including aborts)
            })
            .finally(() => {
                setLoading(false);  // Update loading state regardless of result
                clearTimeout(timeoutId);  // Clear the timeout
            });

        return () => clearTimeout(timeoutId);  // Cleanup timeout on unmount
    }, [src]);

    // Mobile needs less height, otherwise it hides the content below the screen.
    let mobileStyle = {
        position: 'fixed',
        height: '80%',
        width: '100%',
        border: 'none',
        padding: 0,
        backgroundColor: 'var(--panel)',
    };
    // Allow provided `style` to overwrite.
    mobileStyle = style ? {...mobileStyle, ...style} : mobileStyle;
    let tabletStyle = {...mobileStyle, height: '93%'};
    tabletStyle = style ? {...tabletStyle, ...style} : tabletStyle;

    const iframeMedia = <>
        <Media at='mobile'>
            <iframe title={title} src={src} style={mobileStyle} allow="geolocation"/>
        </Media>
        <Media greaterThan='mobile'>
            <iframe title={title} src={src} style={tabletStyle} allow="geolocation"/>
        </Media>
    </>;

    return <>
        {loading ? <Panel><Loading/></Panel>
            : contentAvailable ? iframeMedia
                : fallback
        }
    </>
}

export function roundDigits(value, decimals = 2) {
    return Number(Math.round(value + 'e' + decimals) + 'e-' + decimals);
}


export function Breadcrumbs({crumbs, size = undefined}) {
    function getSection(crumb, index) {
        const {text, link, icon} = crumb;
        if (link) {
            return <Link key={index} to={link} style={{display: 'inline-flex', alignItems: 'center', gap: 4}}>
                {icon && <Icon name={icon}/>}
                {text}
            </Link>;
        }
        return <span key={index}>{text}</span>
    }

    // The separator is a chevron rather than Semantic's slash, matching the icon set.
    return <UIBreadcrumbs separator={<Icon name='chevron right' size={14}/>}>
        {crumbs.map(getSection)}
    </UIBreadcrumbs>
}

export function validURL(url) {
    return !(url && !validUrlRegex.test(url));
}

export function validURLs(urls) {
    if (!!!urls) {
        // Invalid while empty.
        return false;
    }
    urls = urls.split(/\r?\n/);
    for (let i = 0; i < urls.length; i++) {
        if (!validURL(urls[i])) {
            return false;
        }
    }
    return true;
}

export function useLocalStorage(key, initialValue, decode = JSON.parse, encode = JSON.stringify) {
    // Use localstorage to store some JSON encode-able.

    // Initialize state with the value from localStorage or initial value
    const [value, setValue] = useState(() => {
        let item;
        try {
            const item = window.localStorage.getItem(key);
            // Parse the stored item (integer, bool, etc.).  Use the initial value if empty.
            return item ? decode(item) : initialValue;
        } catch (error) {
            console.error('useLocalStorage', key, item, initialValue);
            console.error('Error reading localStorage:', error);
            return initialValue;
        }
    });

    // Save to localStorage when the value changes
    useEffect(() => {
        if (key === null || key === undefined) {
            // key was not defined, do not add this to storage.
            return
        }
        try {
            decode(value);
            window.localStorage.setItem(key, value);
        } catch (error) {
            window.localStorage.setItem(key, encode(value));
        }
    }, [key, value, encode]);

    // Return the stored value and a function to update it
    return [value, setValue];
}

export function useLocalStorageInt(key, initialValue) {
    // Use localStorage to store an integer.
    const [storedValue, setStoredValue] = useLocalStorage(key, initialValue, parseInt, (num) => num.toString());
    return [storedValue, setStoredValue];
}

export function SimpleAccordion({title = 'Advanced', ...props}) {
    return <Accordion chevronPosition='left'>
        <Accordion.Item value='content'>
            <Accordion.Control>{title}</Accordion.Control>
            <Accordion.Panel>{props.children}</Accordion.Panel>
        </Accordion.Item>
    </Accordion>
}

export function mergeDeep(target, source) {
    if (_.isEmpty(source)) {
        return target;
    }

    // Initialize the result as target
    let result = Object.assign({}, target);

    for (let key of Object.keys(source)) {
        if (Array.isArray(source[key])) {
            // source overwrites target if it is a list with values.
            result[key] = source[key] || target[key];
        } else if (typeof source[key] === 'object' && typeof target[key] === 'object' && source[key] !== null) {
            result[key] = mergeDeep(target[key] || {}, source[key]);
        } else {
            result[key] = source[key] !== undefined ? source[key] : target[key];
        }
    }

    return result;
}

export function getDistinctColor(hexColors) {
    function hexToHSL(hex) {
        if (!hex) {
            return {h: 0, s: 0, l: 0};
        }
        let r = parseInt(hex.slice(1, 3), 16) / 255;
        let g = parseInt(hex.slice(3, 5), 16) / 255;
        let b = parseInt(hex.slice(5, 7), 16) / 255;

        let cmax = Math.max(r, g, b), cmin = Math.min(r, g, b);
        let delta = cmax - cmin;
        let h, s, l = (cmax + cmin) / 2;

        if (delta === 0) h = 0;
        else if (cmax === r) h = ((g - b) / delta) % 6;
        else if (cmax === g) h = (b - r) / delta + 2;
        else h = (r - g) / delta + 4;

        h = Math.round(h * 60);
        if (h < 0) h += 360;

        s = delta === 0 ? 0 : delta / (1 - Math.abs(2 * l - 1));

        return {h: h, s: s, l: l};
    }

    function hslToHex(h, s, l) {
        l /= 100;
        const a = s * Math.min(l, 1 - l) / 100;
        const f = n => {
            const k = (n + h / 30) % 12;
            const color = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
            return Math.round(255 * color).toString(16).padStart(2, '0');
        };
        return `#${f(0)}${f(8)}${f(4)}`;
    }

    function generateRandomHSL() {
        return {
            h: Math.random() * 360,
            s: Math.random() * 100,
            l: Math.random() * 100
        };
    }

    function isDistinct(newColor, existingColors, threshold) {
        const hslNew = newColor;
        for (const color of existingColors) {
            const hslColor = hexToHSL(color);
            const h = Math.abs(hslNew.h - hslColor.h);
            const s = Math.abs(hslNew.s * 100 - hslColor.s * 100);
            const l = Math.abs(hslNew.l - hslColor.l * 100);
            if (h < threshold && s < threshold && l < threshold) {
                console.debug(`trying distinct color h=${h} s=${s} l=${l} with threshold=${threshold}`);
                return false;
            }
        }
        return true;
    }

    let newColor, attempt = 0;
    const maxAttempts = 1000; // Max attempts before returning any color
    const baseThreshold = 30; // Starting threshold

    do {
        newColor = generateRandomHSL();
        // Decreasing threshold as attempts increase, but never below 10 for distinctiveness
        let threshold = Math.max(baseThreshold - (attempt / 10), 10);
        if (isDistinct(newColor, hexColors, threshold)) {
            return hslToHex(newColor.h, newColor.s, newColor.l);
        }
        attempt++;
    } while (attempt < maxAttempts);

    // If we've tried maxAttempts times, return the last generated color regardless
    return hslToHex(newColor.h, newColor.s, newColor.l);
}

export const RefreshHeader = ({header, headerSize = 'h2', onRefresh, popupContents}) => {
    const refreshButton = <APIButton icon='refresh' onClick={onRefresh}/>;
    let popup;
    if (popupContents) {
        popup = <Tooltip label={popupContents}>{refreshButton}</Tooltip>;
    }
    return <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
    }}>
        <Header as={headerSize}>{header}</Header>
        {popup || refreshButton}
    </div>
}
