import React from "react";
import {Link, NavLink} from "react-router";
import {IconMenu2, IconPlugOff, IconTemperature, IconTemperaturePlus} from "@tabler/icons-react";
import {Icon, IconButton, Menu, Tooltip} from "./ui";
import {Media, SettingsContext, StatusContext} from "../contexts/contexts";
import {DarkModeToggle, HotspotStatusIcon, useLocalStorage} from "./Common";
import {ShareButton} from "./Share";
import {
    useCPUTemperature,
    useDriveHealth,
    useDriveTemperature,
    useIOStats,
    useLoad,
    useMemoryStats,
    usePowerStats,
    useWROLMode
} from "../hooks/customHooks";
import {useReorganizationStatus} from "../contexts/FileWorkerStatusContext";
import {SearchIconButton} from "./Search";
import {HELP_VIEWER_URI, NAME, navColorHexMap} from "./Vars";
import {useOverflowNav} from "../hooks/useOverflowNav";
import {defaultNavColor, navBarStyle, useNavColors} from "../themes/navColors";
import _ from "lodash";

function updateFavicon(colorName) {
    // Fall back to violet if invalid color
    const safeColor = colorName in navColorHexMap ? colorName : 'violet';
    const faviconPath = `/favicon-${safeColor}.svg`;

    // Update all favicon links
    const iconLinks = document.querySelectorAll('link[rel="icon"], link[rel="shortcut icon"]');
    iconLinks.forEach(link => {
        link.href = faviconPath;
    });

    // Also update the 32x32 and 16x16 specific icons if they exist
    const icon32 = document.querySelector('link[sizes="32x32"]');
    const icon16 = document.querySelector('link[sizes="16x16"]');
    if (icon32) icon32.href = faviconPath;
    if (icon16) icon16.href = faviconPath;

    // Update theme-color meta tag for iOS/Android status bar
    const hexColor = navColorHexMap[safeColor];
    const themeColorMeta = document.querySelector('meta[name="theme-color"]');
    if (themeColorMeta) themeColorMeta.content = hexColor;
}

// A theme token name, or null to inherit the surrounding text/icon color (never
// literally "var(--null)").
const colorVar = (color) => color ? `var(--${color})` : undefined;

const help = {to: HELP_VIEWER_URI, text: 'Help', key: 'help', target: '_blank'};
const admin = {to: '/admin', text: 'Admin', key: 'admin'};
const rightLinks = [help, admin];
const allLinks = [
    {text: 'Videos', to: '/videos', key: 'videos'},
    {text: 'Archive', to: '/archives', key: 'archive'},
    {text: 'Docs', to: '/docs', key: 'docs'},
    {text: 'Map', to: '/map', key: 'map'},
    {text: 'Files', to: '/files', key: 'files'},
    {text: 'Playlists', to: '/playlists', key: 'playlists'},
    {text: 'Zim', to: '/zim', key: 'zim'},
    {text: 'Inventory', to: '/inventory', key: 'inventory'},
    // No `end` on these two: a tab stays current for the pages beneath it, and `end` would
    // drop the mark the moment either grows a sub-page.
    {to: '/more/calculators', text: 'Calculators', key: 'calculators'},
    {text: 'Flasher', to: '/flasher', key: 'flasher'},
    {to: '/more/statistics', text: 'Statistics', key: 'statistics'},
];

function MenuLink({link}) {
    // A top-level tab rendered directly in the bar (not inside a dropdown).
    if (link.links) {
        return <DropdownLinks link={link}/>
    }
    const end = link.end ? {end: true} : {};
    const target = link.target ? {target: link.target, rel: 'noopener noreferrer'} : {};
    return <NavLink
        className='wrolpi-navbar-link'
        to={link.to}
        {...end}
        {...target}
    >
        {link.text}
    </NavLink>
}

function DropdownMenuItem({link}) {
    // An item inside a Menu.Dropdown: the mobile hamburger menu, or the desktop
    // "More" overflow menu.
    if (link.links) {
        // Mantine's Menu does not nest submenus without extra plumbing; a labelled,
        // indented group stands in for one.  No current data uses this path (no
        // allLinks entry has its own `links`).
        return <React.Fragment>
            <Menu.Label>{link.text}</Menu.Label>
            {link.links.map(l => <DropdownMenuItem key={l.key} link={l}/>)}
        </React.Fragment>
    }
    const end = link.end ? {end: true} : {};
    const target = link.target ? {target: link.target, rel: 'noopener noreferrer'} : {};
    return <Menu.Item component={NavLink} to={link.to} {...end} {...target}>
        {link.text}
    </Menu.Item>
}

/*
 * The trigger for a navbar dropdown.
 *
 * Shared with the hidden placeholder DesktopNav measures on its first render, and that is
 * the point of extracting it.  The placeholder used to be a plain `<button>More</button>`
 * with no caret, so the space reserved for the overflow menu was about 21px short of the
 * button that eventually rendered -- the row overflowed by that much and the bar wrapped.
 * Measuring one thing and drawing another is only ever right by coincidence.
 */
const NavDropdownTrigger = React.forwardRef(({text, className, ...props}, ref) =>
    /*
     * `className` is pulled out and MERGED, never spread over.  Menu.Target clones its child
     * and hands it a className of its own, and a `{...props}` spread placed after the
     * attribute replaces ours with it -- which left the real More button with no class at
     * all, so it rendered as a bare grey UA button instead of taking the bar's color, its
     * padding and its hover.  The hidden placeholder is not cloned by Menu.Target, so it
     * kept its class and measured wider than the button that actually drew.
     */
    <button type='button' ref={ref}
            className={['wrolpi-navbar-link', 'wrolpi-navbar-link-button', className]
                .filter(Boolean).join(' ')}
            {...props}>
        {text}
        <Icon name='dropdown' size='small' style={{marginLeft: '0.35em'}}/>
    </button>
);
NavDropdownTrigger.displayName = 'NavDropdownTrigger';

function DropdownLinks({link}) {
    // A labelled dropdown trigger: the desktop "More" overflow, or any nested
    // link group handed to MenuLink.
    return <Menu position='bottom-end' withinPortal>
        <Menu.Target>
            <NavDropdownTrigger text={link.text}/>
        </Menu.Target>
        <Menu.Dropdown>
            {link.links.map(l => <DropdownMenuItem key={l.key} link={l}/>)}
        </Menu.Dropdown>
    </Menu>
}

function MobileMenu({links}) {
    // The mobile hamburger menu: an icon-only trigger holding every link.
    return <Menu position='bottom-end' withinPortal>
        <Menu.Target>
            <IconButton icon={IconMenu2} label='Menu' variant='subtle'/>
        </Menu.Target>
        <Menu.Dropdown>
            {links.map(link => <DropdownMenuItem key={link.key} link={link}/>)}
        </Menu.Dropdown>
    </Menu>
}

/*
 * One status indicator's slot in the right-hand corner.
 *
 * This used to carry `marginTop: 0.8em`, a nudge inherited from the bar this replaced.  The
 * corner centres its children, and a top margin is part of the margin box being centred, so the
 * nudge pushed every indicator down by half of it -- about 6px.
 *
 * That read as an error on some and not others, which is why it survived: the bare-icon
 * anchors (share, search) sit high inside their line box because it reserves descender space
 * for text that is not there, so the nudge happened to cancel out.  An IconButton is a square
 * ActionIcon that centres its glyph exactly, so for the hotspot and the theme picker the
 * nudge was 6px of pure error.  Laying the slot out as a flex box centres both shapes on
 * their real glyph box and needs no nudge at all.
 */
export function NavIconWrapper({children}) {
    if (children) {
        return <div className='wrolpi-navbar-icon'>{children}</div>
    } else {
        // Do not use navbar space if children is empty.
        return <React.Fragment/>
    }
}

function useNavColorSetting() {
    // Use localstorage to avoid flickering navbar color on startup.
    const {settings} = React.useContext(SettingsContext);
    const [navColor, setNavColor] = useLocalStorage('nav_color', defaultNavColor);

    React.useEffect(() => {
        if (!_.isEmpty(settings)) {
            setNavColor(settings.nav_color);
        }
    }, [settings.nav_color]);

    // Update favicon to match nav color
    React.useEffect(() => {
        if (navColor) {
            updateFavicon(navColor);
        }
    }, [navColor]);

    return navColor
}

export function NavBar() {
    const wrolModeEnabled = useWROLMode();
    const {status} = React.useContext(StatusContext);
    const navColor = useNavColorSetting();
    /*
     * The bar's foreground is measured against the background the theme resolved for the
     * user's color, not taken from a single token.  See themes/navColors.
     */
    const navColors = useNavColors(navColor);
    const wrolpiIcon = <img src='/icon.svg' height='32px' width='32px' alt='WROLPi Home Icon'/>;
    const name = <i>{NAME || wrolpiIcon}</i>;
    const topNavText = wrolModeEnabled ? <>{name}&nbsp; <Icon name='lock'/></> : name;

    const homeLink = <NavLink className='wrolpi-navbar-link' to='/' style={{paddingTop: 0, paddingBottom: 0}}>
        {topNavText}
    </NavLink>;

    // Red/Yellow colors will blend in to some navbar colors, swap the colors for high contrast.
    const conflictingColors = ['red', 'orange', 'yellow', 'olive', 'pink'];
    const [lowWarningColor, highWarningColor] = conflictingColors.includes(navColor)
        ? [null, 'black']
        : ['yellow', 'red'];

    // Generic system load, the least important warning.
    const {minute_1, mediumLoad, highLoad} = useLoad();
    let systemLoadIcon;
    if (mediumLoad || highLoad) {
        // System load is high, display a warning icon.
        const color = highLoad ? highWarningColor : lowWarningColor;
        const icon = <Link to='/admin/status'>
            <Icon name='tachometer alternate' size='large' style={{color: colorVar(color)}}
                  label='System load warning'/>
        </Link>;
        systemLoadIcon = <Tooltip label={`Load: ${minute_1}`}>{icon}</Tooltip>
    }

    // RAM consumption.
    const {percent: memoryPercent} = useMemoryStats();
    let memoryIcon;
    if (memoryPercent > 80) {
        const color = memoryPercent > 90 ? highWarningColor : lowWarningColor;
        {/*
          The color goes on the Icon, as it does for every other indicator.  It used to
          be passed to `Link`, which ignores it, so the memory warning never actually
          changed color -- 81% and 95% looked identical.
        */}
        const icon = <Link to='/admin/status'>
            <Icon name='microchip' size='large' label='Memory usage warning'
                  style={{color: colorVar(color)}}/>
        </Link>;
        memoryIcon = <Tooltip label={`System Memory: ${memoryPercent.toFixed()}%`}>{icon}</Tooltip>
    }

    // Any disk is busy and processes are waiting.
    const {percentIOWait} = useIOStats();
    let diskWaitIcon;
    if (percentIOWait >= 50) {
        // Processes are waiting on disk, display a warning icon.
        const color = percentIOWait > 75 ? highWarningColor : lowWarningColor;
        const icon = <Link to='/admin/status'>
            <Icon name='disk' size='large' style={{color: colorVar(color)}} label='Disk I/O wait warning'/>
        </Link>;
        diskWaitIcon = <Tooltip label={`Processes waiting on disk: ${percentIOWait.toFixed()}%`}>{icon}</Tooltip>
    }

    // CPU temperature.
    const {temperature, highTemperature, criticalTemperature} = useCPUTemperature();
    let temperatureIcon;
    if (temperature && temperature >= highTemperature) {
        // CPU temperature is high, display a warning icon.
        const color = temperature >= criticalTemperature ? highWarningColor : lowWarningColor;
        const temperatureComponent = temperature >= criticalTemperature ? IconTemperaturePlus : IconTemperature;
        const icon = <Icon data-testid='cpuTemperatureIcon' component={temperatureComponent} size='large'
                            style={{color: colorVar(color)}} label='CPU temperature warning'/>
        const link = <Link to='/admin/status'>{icon}</Link>;
        temperatureIcon = <Tooltip label={`CPU: ${temperature.toFixed()}°C`}>{link}</Tooltip>;
    }

    // Hard-drive temperature.  An overheating drive risks data loss.
    const {
        device: hotDrive,
        temperature: driveTemperature,
        highTemperature: driveHighTemperature,
        criticalTemperature: driveCriticalTemperature,
    } = useDriveTemperature();
    let driveTemperatureIcon;
    if (driveTemperature && driveTemperature >= driveHighTemperature) {
        const color = driveTemperature >= driveCriticalTemperature ? highWarningColor : lowWarningColor;
        const icon = <Icon data-testid='driveTemperatureIcon' name='hdd' size='large'
                            style={{color: colorVar(color)}} label='Drive temperature warning'/>
        const link = <Link to='/admin/controller'>{icon}</Link>;
        driveTemperatureIcon = <Tooltip label={`${hotDrive}: ${driveTemperature.toFixed()}°C`}>{link}</Tooltip>;
    }

    // A drive's SMART health is degraded.  FAIL is an imminent failure (back
    // up now); WARN means unreadable/pending sectors are accumulating.  Always
    // displayed (like power); too important to hide behind a transient warning
    // in the priority chain.  Links to the Controller page, which shows the
    // SMART detail (the Status page does not).
    const {failingDevices, failing: driveFailing, warningDevices, warning: driveWarning} = useDriveHealth();
    let driveHealthIcon;
    if (driveFailing) {
        const icon = <Icon data-testid='driveHealthIcon' name='warning sign' size='large'
                            style={{color: colorVar(highWarningColor)}} label='Drive health failing'/>;
        const link = <Link to='/admin/controller'>{icon}</Link>;
        const message = failingDevices.length === 1
            ? `Drive ${failingDevices[0]} is failing its SMART health check! Back up your data.`
            : `Drives failing SMART health check: ${failingDevices.join(', ')}. Back up your data.`;
        driveHealthIcon = <Tooltip label={message}>{link}</Tooltip>;
    } else if (driveWarning) {
        const icon = <Icon data-testid='driveHealthIcon' name='warning sign' size='large'
                            style={{color: colorVar(lowWarningColor)}} label='Drive health warning'/>;
        const link = <Link to='/admin/controller'>{icon}</Link>;
        const message = warningDevices.length === 1
            ? `Drive ${warningDevices[0]} has unreadable or pending sectors — check its SMART health.`
            : `Drives with unreadable or pending sectors: ${warningDevices.join(', ')}. Check their SMART health.`;
        driveHealthIcon = <Tooltip label={message}>{link}</Tooltip>;
    }

    // Power issues, this is always displayed if detected.
    const {underVoltage, overCurrent} = usePowerStats();
    let powerIcon;
    if (underVoltage || overCurrent) {
        const icon = underVoltage
            ? <Icon component={IconPlugOff} size='large' style={{color: colorVar(highWarningColor)}}
                    label='Under-voltage warning'/>
            : <Icon name='lightning' size='large' style={{color: colorVar(highWarningColor)}}
                    label='Over-current warning'/>;
        const message = underVoltage
            ? 'Under-voltage detected! Your power supply is insufficient!'
            : 'Over-current detected! Your peripherals are using too much power!';
        powerIcon = <Tooltip label={message}><span>{icon}</span></Tooltip>;
    }

    // Display the temperature icon first because it can cause the system to throttle.  The rest are in order of effects
    // that will slow down the system and the user should address.  Generic load is last because it is probably not an
    // issue.
    const warningIcon = temperatureIcon || driveTemperatureIcon || diskWaitIcon || memoryIcon || systemLoadIcon;

    const {isReorganizing, taskType, collectionId, collectionKind} = useReorganizationStatus();

    let processingLink;
    if (status && status.flags) {
        if (status.flags.file_worker_busy) {
            // Smart navigation based on what the file worker is doing
            if (isReorganizing && collectionId && collectionKind) {
                // Single collection reorganization - navigate to that collection
                if (collectionKind === 'channel') {
                    processingLink = `/videos/channel/${collectionId}/edit`;
                } else if (collectionKind === 'domain') {
                    processingLink = `/archives/domain/${collectionId}/edit`;
                } else {
                    processingLink = '/files';
                }
            } else if (isReorganizing && taskType === 'batch_reorganize' && collectionKind) {
                // Batch reorganization - navigate to settings page for that kind
                if (collectionKind === 'channel') {
                    processingLink = '/videos/settings';
                } else if (collectionKind === 'domain') {
                    processingLink = '/archives/settings';
                } else {
                    processingLink = '/files';
                }
            } else {
                processingLink = '/files';
            }
        }
    }
    const processingIcon = processingLink &&
        <Link to={processingLink}>
            <Icon loading name='circle notch' size='large' label='File worker busy'/>
        </Link>;

    let apiDownIcon;
    if (window.apiDown) {
        apiDownIcon = <Tooltip label='API is not responding'>
            <span><Icon name='plug' style={{color: colorVar(highWarningColor)}} label='API is not responding'/></span>
        </Tooltip>
    }

    // Upgrade available notification - only show on native (non-Docker) installs and when WROL Mode is disabled
    let upgradeIcon;
    if (status?.update_available && !status?.dockerized && !wrolModeEnabled) {
        const commitsBehind = status.commits_behind || 0;
        const branch = status.git_branch || 'unknown';
        const icon = <Link to='/admin/settings#upgrade'>
            <Icon name='arrow alternate circle up' size='large' style={{color: 'var(--green)'}}
                  label='Upgrade available'/>
        </Link>;
        upgradeIcon = <Tooltip label={`Upgrade available: ${commitsBehind} commit(s) behind on ${branch}`}>
            {icon}
        </Tooltip>;
    }

    const icons = <React.Fragment>
        <NavIconWrapper>{apiDownIcon}</NavIconWrapper>
        <NavIconWrapper>{processingIcon}</NavIconWrapper>
        <NavIconWrapper>{upgradeIcon}</NavIconWrapper>
        <NavIconWrapper>{driveHealthIcon}</NavIconWrapper>
        <NavIconWrapper>{powerIcon}</NavIconWrapper>
        <NavIconWrapper>{warningIcon}</NavIconWrapper>
        <NavIconWrapper><ShareButton/></NavIconWrapper>
        <NavIconWrapper><HotspotStatusIcon/></NavIconWrapper>
        <NavIconWrapper><DarkModeToggle/></NavIconWrapper>
    </React.Fragment>;

    return <>
        <Media between={['mobile', 'tablet']}>
            <nav className='wrolpi-navbar' id='global_navbar' style={navBarStyle(navColors)}>
                {homeLink}
                <div className='wrolpi-navbar-right'>
                    {icons}
                    <SearchIconButton/>
                    <MobileMenu links={[...allLinks, ...rightLinks]}/>
                </div>
            </nav>
        </Media>
        <Media greaterThanOrEqual='tablet'>
            <DesktopNav navColors={navColors} homeLink={homeLink} icons={icons}/>
        </Media>
    </>
}

export function DesktopNav({navColors, homeLink, icons}) {
    const containerRef = React.useRef(null);
    const homeRef = React.useRef(null);
    const rightMenuRef = React.useRef(null);
    const moreRef = React.useRef(null);
    const {visibleLinks, overflowLinks, itemRefCallback, isReady} = useOverflowNav({
        links: allLinks,
        containerRef,
        homeRef,
        rightMenuRef,
        moreRef,
    });

    return (
        <div ref={containerRef}>
            <nav className='wrolpi-navbar' id='global_navbar' style={navBarStyle(navColors)}>
                <span ref={homeRef} style={{display: 'contents'}}>{homeLink}</span>
                {(isReady ? visibleLinks : allLinks).map((link, idx) => (
                    <span
                        key={link.key}
                        ref={itemRefCallback(idx)}
                        style={isReady ? {display: 'contents'} : {visibility: 'hidden', flexShrink: 0}}
                    >
                        <MenuLink link={link}/>
                    </span>
                ))}
                {!isReady && <span ref={moreRef} style={{visibility: 'hidden', flexShrink: 0}}>
                    <NavDropdownTrigger text='More'/>
                </span>}
                {isReady && overflowLinks.length > 0 &&
                    <DropdownLinks link={{text: 'More', key: 'more', links: overflowLinks}}/>}
                <div ref={rightMenuRef} className='wrolpi-navbar-right'>
                    {icons}
                    <SearchIconButton/>
                    {rightLinks.map(i => <MenuLink link={i} key={i.key}/>)}
                </div>
            </nav>
        </div>
    );
}
