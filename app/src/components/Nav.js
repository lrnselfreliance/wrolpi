import React from "react";
import {Link, NavLink} from "react-router-dom";
import {Dropdown, Icon as SIcon, Menu} from "semantic-ui-react";
import {Media, SettingsContext, StatusContext, ThemeContext} from "../contexts/contexts";
import {CPUTemperatureIcon, DarkModeToggle, HotspotStatusIcon, SystemLoadIcon, useLocalStorage} from "./Common";
import {ShareButton} from "./Share";
import {useWROLMode} from "../hooks/customHooks";
import {SearchIconButton} from "./Search";
import {Icon} from "./Theme";
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

function NavIconWrapper(props) {
    if (_.isEmpty(props.children)) {
        return <></>
    } else {
        if (props.name === 'warning') {
            // console.log(props.name, props.children);
        }
        return <div style={{marginTop: '0.8em', marginLeft: '1.5em'}}>{props.children}</div>
    }
}

function useNavColorSetting() {
    // Use localstorage to avoid flickering navbar color on startup.
    const {settings} = React.useContext(SettingsContext);
    const [navColor, setNavColor] = useLocalStorage('nav_color', 'violet');

    React.useEffect(() => {
        const newColor = settings.nav_color || 'violet';
        setNavColor(newColor);
        localStorage.setItem('nav_color', newColor);
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

    // Display the temperature icon first because it can cause the system to throttle.
    const warningIcon = <CPUTemperatureIcon fallback={<SystemLoadIcon/>}/>;

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

    const icons = <React.Fragment>
        <NavIconWrapper name='processing'>{processingIcon}</NavIconWrapper>
        <NavIconWrapper name='warning'>{warningIcon}</NavIconWrapper>
        <NavIconWrapper name='share'><ShareButton/></NavIconWrapper>
        <NavIconWrapper name='hotspot'><HotspotStatusIcon/></NavIconWrapper>
        <NavIconWrapper name='dark mode'><DarkModeToggle/></NavIconWrapper>
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
