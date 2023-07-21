import React from "react";
import {NavLink} from "react-router-dom";
import {Dropdown, Menu} from "semantic-ui-react";
import {Media, StatusContext, ThemeContext} from "../contexts/contexts";
import Icon from "semantic-ui-react/dist/commonjs/elements/Icon";
import {DarkModeToggle, HotspotStatusIcon, NAME} from "./Common";
import {ShareButton} from "./Share";
import {useWROLMode} from "../hooks/customHooks";

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
            {to: '/more/statistics', text: 'Statistics', end: true},
        ]
    },
];
const admin = {to: '/admin', text: 'Admin', key: 'admin'};
const rightLinks = [admin,];

const collapsedLinks = links.concat([admin,]);

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
        return <NavLink
            className='item'
            to={link.to}
            {...end}
        >
            {link.text}
        </NavLink>
    }
}

function NavIcon(props) {
    return <div style={{margin: '0.8em'}}>{props.children}</div>
}

export function NavBar() {
    const wrolModeEnabled = useWROLMode();
    const wrolpiIcon = <img src='/icon.svg' height='32px' width='32px' alt='WROLPi Home Icon'/>;
    const name = NAME || wrolpiIcon;
    const topNavText = wrolModeEnabled ? <>{name}&nbsp; <Icon name='lock'/></> : name;
    const {i} = React.useContext(ThemeContext);

    const homeLink = <NavLink className='item' to='/' style={{paddingTop: 0, paddingBottom: 0}}>
        {topNavText}
    </NavLink>;
    const icons = <React.Fragment>
        <NavIcon><ShareButton/></NavIcon>
        <NavIcon><HotspotStatusIcon/></NavIcon>
        <NavIcon><DarkModeToggle/></NavIcon>
    </React.Fragment>;

    return <>
        <Media at='mobile'>
            <Menu {...i} attached='top' color='violet'>
                {homeLink}
                <Menu.Menu position='right'>
                    {icons}
                    <Dropdown item icon="bars">
                        <Dropdown.Menu>
                            {collapsedLinks.map(i => <MenuLink link={i} key={i.key}/>)}
                        </Dropdown.Menu>
                    </Dropdown>
                </Menu.Menu>
            </Menu>
        </Media>
        <Media greaterThanOrEqual='tablet'>
            <Menu {...i} attached='top' color='violet'>
                {homeLink}
                {links.map(i => <MenuLink link={i} key={i.key}/>)}

                <Menu.Menu position='right'>
                    {icons}
                    {rightLinks.map(i => <MenuLink link={i} key={i.key}/>)}
                </Menu.Menu>
            </Menu>
        </Media>
    </>
}
