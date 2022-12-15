import React, {useContext} from "react";
import {NavLink} from "react-router-dom";
import {Dropdown, Menu, Responsive} from "semantic-ui-react";
import {StatusContext, ThemeContext} from "../contexts/contexts";
import Icon from "semantic-ui-react/dist/commonjs/elements/Icon";
import {DarkModeToggle, HotspotStatusIcon, NAME} from "./Common";

const responsiveWidth = 500;

const links = [
    {text: 'Videos', to: '/videos', key: 'videos'},
    {text: 'Archive', to: '/archive', key: 'archive'},
    {text: 'Map', to: '/map', key: 'map'},
    {text: 'Files', to: '/files', key: 'files'},
    {text: 'Inventory', to: '/inventory', key: 'inventory'},
    {
        key: 'apps', text: 'Apps', links: [
            {to: '/apps/otp', text: 'One Time Pad', end: true},
            {to: '/apps/file_statistics', text: 'File Statistics', end: true},
        ]
    },
];
const admin = {to: '/admin', text: 'Admin', key: 'admin'};
const rightLinks = [admin,];

const collapsedLinks = links.concat([admin,]);

function DropdownLinks(props) {
    return (
        <Dropdown item text={props.link.text}>
            <Dropdown.Menu>
                {props.link.links.map((l) => {
                    return (
                        <MenuLink key={l.to} link={l}/>
                    )
                })}
            </Dropdown.Menu>
        </Dropdown>
    )
}

function MenuLink({link}) {
    // Wrapper around NavLink to handle Navlink/Dropdown change.
    let classes = 'item';

    if (!link.links) {
        const end = link.end ? {end: true} : {end: undefined};
        return (
            <NavLink
                className={classes}
                to={link.to}
                {...end}
            >
                {link.text}
            </NavLink>
        )
    } else {
        return (
            <DropdownLinks link={link}/>
        )
    }
}

function NavIcon(props) {
    return <div style={{margin: '0.8em'}}>{props.children}</div>
}

export function NavBar() {
    const {status} = useContext(StatusContext);
    const wrol_mode = status ? status['wrol_mode'] : null;
    const name = NAME || 'WROLPi';
    const topNavText = wrol_mode ? <>{name}&nbsp; <Icon name='lock'/></> : name;
    const {i} = useContext(ThemeContext);

    return (
        <Menu {...i}>
            {/*Always show WROLPi home button*/}
            <MenuLink link={{to: '/', text: topNavText, end: true}}/>

            {/*Show the links in a menu when on desktop*/}
            {links.map((link) => {
                return (
                    <Responsive minWidth={responsiveWidth} as={MenuLink} link={link} key={link.key}/>
                )
            })}
            <Responsive minWidth={responsiveWidth} as={Menu.Menu} position="right">
                <NavIcon><HotspotStatusIcon/></NavIcon>
                <NavIcon><DarkModeToggle/></NavIcon>
                {rightLinks.map((link) => <MenuLink link={link} key={link.key}/>)}
            </Responsive>

            {/*Show the menu items in a dropdown when on mobile*/}
            <Responsive as={Menu.Menu} maxWidth={responsiveWidth - 1} position='right'>
                <NavIcon><HotspotStatusIcon/></NavIcon>
                <NavIcon><DarkModeToggle/></NavIcon>
                <Dropdown item icon="bars">
                    <Dropdown.Menu>
                        {collapsedLinks.map((link) =>
                            <MenuLink link={link} key={link.key}/>
                        )}
                    </Dropdown.Menu>
                </Dropdown>
            </Responsive>
        </Menu>
    )
}
