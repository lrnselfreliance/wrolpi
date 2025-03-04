import React from "react";
import {Link, NavLink} from "react-router-dom";
import {Dropdown, Icon as SIcon, Menu} from "semantic-ui-react";
import {Media, SettingsContext, StatusContext, ThemeContext} from "../contexts/contexts";
import {DarkModeToggle, HotspotStatusIcon, useLocalStorage} from "./Common";
import {ShareButton} from "./Share";
import {useCPUTemperature, useIOStats, useLoad, useMemoryStats, usePowerStats, useWROLMode} from "../hooks/customHooks";
import {SearchIconButton} from "./Search";
import {Icon, Popup} from "./Theme";
import {HELP_VIEWER_URI, NAME} from "./Vars";
import _ from "lodash";

const links = [
    {text: 'Videos', to: '/videos', key: 'videos'},
    {text: 'Archive', to: '/archive', key: 'archive'},
    {text: 'Map', to: '/map', key: 'map'},
    {text: 'Zim', to: '/zim', key: 'zim'},
    {text: 'Files', to: '/files', key: 'files'},
    {
        text: 'More', key: 'more',
        links: [
            {text: 'Inventory', to: '/inventory', key: 'inventory'},
            {to: '/more/otp', text: 'One Time Pad', end: true},
            {to: '/more/vin', text: 'VIN Decoder', end: true},
            {to: '/more/calculators', text: 'Calculators', end: true},
            {to: '/more/statistics', text: 'Statistics', end: true},
        ]
    },
];
const help = {to: HELP_VIEWER_URI, text: 'Help', key: 'help', target: '_blank'};
const admin = {to: '/admin', text: 'Admin', key: 'admin'};
const rightLinks = [help, admin];

const collapsedLinks = links.concat([help, admin]);

function DropdownLinks({link}) {
    return <Dropdown item text={link.text} direction='left'>
        <Dropdown.Menu>
            {link.links.map(l => <MenuLink key={l.to} link={l}/>)}
        </Dropdown.Menu>
    </Dropdown>
}

function MenuLink({link}) {
    // Wrapper around NavLink to handle Navlink/Dropdown change.
    if (link.links) {
        return <DropdownLinks link={link}/>
    } else {
        const end = link.end ? {end: true} : {end: undefined};
        const target = link.target ? {target: link.target} : {};
        return <NavLink
            className='item'
            to={link.to}
            {...end}
            {...target}
        >
            {link.text}
        </NavLink>
    }
}

function NavIconWrapper({children}) {
    if (children) {
        return <div style={{marginTop: '0.8em', marginLeft: '1.5em'}}>{children}</div>
    } else {
        // Do not use navbar space if children is empty.
        return <React.Fragment/>
    }
}

function useNavColorSetting() {
    // Use localstorage to avoid flickering navbar color on startup.
    const {settings} = React.useContext(SettingsContext);
    const [navColor, setNavColor] = useLocalStorage('nav_color', 'violet');

    React.useEffect(() => {
        if (!_.isEmpty(settings)) {
            setNavColor(settings.nav_color);
        }
    }, [settings.nav_color]);

    return navColor
}

export function NavBar() {
    const wrolModeEnabled = useWROLMode();
    const {status} = React.useContext(StatusContext);
    const navColor = useNavColorSetting();
    const wrolpiIcon = <img src='/icon.svg' height='32px' width='32px' alt='WROLPi Home Icon'/>;
    const name = <i>{NAME || wrolpiIcon}</i>;
    const topNavText = wrolModeEnabled ? <>{name}&nbsp; <SIcon name='lock'/></> : name;
    const {i} = React.useContext(ThemeContext);

    const homeLink = <NavLink className='item' to='/' style={{paddingTop: 0, paddingBottom: 0}}>
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
            <Icon name='tachometer alternate' size='large' color={color}/>
        </Link>;
        systemLoadIcon = <Popup content={`Load: ${minute_1}`} trigger={icon}/>
    }

    // RAM consumption.
    const {percent: memoryPercent} = useMemoryStats();
    let memoryIcon;
    if (memoryPercent > 80) {
        const color = memoryPercent > 90 ? highWarningColor : lowWarningColor;
        const icon = <Link to='/admin/status' color={color}>
            <Icon name='microchip' size='large'/>
        </Link>;
        memoryIcon = <Popup content={`System Memory: ${memoryPercent.toFixed()}%`} trigger={icon}/>
    }

    // Any disk is busy and processes are waiting.
    const {percentIOWait} = useIOStats();
    let diskWaitIcon;
    if (percentIOWait >= 50) {
        // Processes are waiting on disk, display a warning icon.
        const color = percentIOWait > 75 ? highWarningColor : lowWarningColor;
        const icon = <Link to='/admin/status'>
            <Icon name='disk' size='large' color={color}/>
        </Link>;
        diskWaitIcon = <Popup content={`Processes waiting on disk: ${percentIOWait.toFixed()}%`} trigger={icon}/>
    }

    // CPU temperature.
    const {temperature, highTemperature, criticalTemperature} = useCPUTemperature();
    let temperatureIcon;
    if (temperature && temperature >= highTemperature) {
        // CPU temperature is high, display a warning icon.
        const color = temperature >= criticalTemperature ? highWarningColor : lowWarningColor;
        const name = temperature >= criticalTemperature ? 'thermometer' : 'thermometer half';
        const icon = <Icon data-testid='cpuTemperatureIcon' name={name} size='large' color={color}/>
        const link = <Link to='/admin/status'>{icon}</Link>;
        temperatureIcon = <Popup content={`CPU: ${temperature.toFixed()}°C`} trigger={link}/>;
    }

    // Power issues, this is always displayed if detected.
    const {underVoltage, overCurrent} = usePowerStats();
    let powerIcon;
    if (underVoltage || overCurrent) {
        const name = underVoltage ? 'power cord' : 'lightning';
        const icon = <Icon name={name} size='large' color={highWarningColor}/>;
        const message = underVoltage
            ? 'Under-voltage detected! Your power supply is insufficient!'
            : 'Over-current detected! Your peripherals are using too much power!';
        powerIcon = <Popup content={message} trigger={icon}/>;
    }

    // Display the temperature icon first because it can cause the system to throttle.  The rest are in order of effects
    // that will slow down the system and the user should address.  Generic load is last because it is probably not an
    // issue.
    const warningIcon = temperatureIcon || diskWaitIcon || memoryIcon || systemLoadIcon;

    let processingLink;
    if (status && status.flags) {
        if (status.flags.refreshing) {
            processingLink = '/files';
        } else if (status.flags.map_importing) {
            processingLink = '/map/manage';
        }
    }
    const processingIcon = processingLink &&
        <Link to={processingLink}>
            <Icon loading name='circle notch' size='large'/>
        </Link>;

    let apiDownIcon;
    if (window.apiDown) {
        apiDownIcon = <Popup
            content='API is not responding'
            trigger={<Icon name='plug' color={highWarningColor}/>}
        />
    }

    const icons = <React.Fragment>
        <NavIconWrapper>{apiDownIcon}</NavIconWrapper>
        <NavIconWrapper>{processingIcon}</NavIconWrapper>
        <NavIconWrapper>{powerIcon}</NavIconWrapper>
        <NavIconWrapper>{warningIcon}</NavIconWrapper>
        <NavIconWrapper><ShareButton/></NavIconWrapper>
        <NavIconWrapper><HotspotStatusIcon/></NavIconWrapper>
        <NavIconWrapper><DarkModeToggle/></NavIconWrapper>
    </React.Fragment>;

    return <>
        <Media at='mobile'>
            <Menu {...i} attached='top' color={navColor} id='global_navbar'>
                {homeLink}
                <Menu.Menu position='right'>
                    {icons}
                    <SearchIconButton/>
                    <Dropdown item icon="bars">
                        <Dropdown.Menu>
                            {collapsedLinks.map(i => <MenuLink link={i} key={i.key}/>)}
                        </Dropdown.Menu>
                    </Dropdown>
                </Menu.Menu>
            </Menu>
        </Media>
        <Media greaterThanOrEqual='tablet'>
            <Menu {...i} attached='top' color={navColor} id='global_navbar'>
                {homeLink}
                {links.map(i => <MenuLink link={i} key={i.key}/>)}

                <Menu.Menu position='right'>
                    {icons}
                    <SearchIconButton/>
                    {rightLinks.map(i => <MenuLink link={i} key={i.key}/>)}
                </Menu.Menu>
            </Menu>
        </Media>
    </>
}
