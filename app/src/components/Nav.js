import React, {useContext} from "react";
import {NavLink} from "react-router-dom";
import {Dropdown, Menu} from "semantic-ui-react";
import {Media, StatusContext, ThemeContext} from "../contexts/contexts";
import Icon from "semantic-ui-react/dist/commonjs/elements/Icon";
import {DarkModeToggle, HotspotStatusIcon, NAME} from "./Common";

const links = [{text: 'Videos', to: '/videos', key: 'videos'}, {
    text: 'Archive', to: '/archive', key: 'archive'
}, {text: 'Map', to: '/map', key: 'map'}, {text: 'Files', to: '/files', key: 'files'}, {
    text: 'Inventory', to: '/inventory', key: 'inventory'
}, {
    key: 'apps', text: 'Apps', links: [{to: '/apps/otp', text: 'One Time Pad', end: true}, {
        to: '/apps/statistics', text: 'Statistics', end: true
    },]
},];
const admin = {to: '/admin', text: 'Admin', key: 'admin'};
const rightLinks = [admin,];

const collapsedLinks = links.concat([admin,]);

function DropdownLinks(props) {
    return (<Dropdown item text={props.link.text}>
        <Dropdown.Menu>
            {props.link.links.map((l) => {
                return (<MenuLink key={l.to} link={l}/>)
            })}
        </Dropdown.Menu>
    </Dropdown>)
}

function MenuLink({link}) {
    // Wrapper around NavLink to handle Navlink/Dropdown change.
    let classes = 'item';

    if (!link.links) {
        const end = link.end ? {end: true} : {end: undefined};
        return (<NavLink
            className={classes}
            to={link.to}
            {...end}
        >
            {link.text}
        </NavLink>)
    } else {
        return (<DropdownLinks link={link}/>)
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

    const homeLink = <MenuLink link={{to: '/', text: topNavText, end: true}}/>;
    const icons = <React.Fragment>
        <NavIcon><HotspotStatusIcon/></NavIcon>
        <NavIcon><DarkModeToggle/></NavIcon>
    </React.Fragment>;

    return <>
        <Media at='mobile'>
            <Menu {...i}>
                {homeLink}
                <Menu.Menu position='right'>
                    {icons}
                    <Dropdown item icon="bars">
                        <Dropdown.Menu>
                            {collapsedLinks.map(i =><MenuLink link={i} key={i.key}/>)}
                        </Dropdown.Menu>
                    </Dropdown>
                </Menu.Menu>
            </Menu>
        </Media>
        <Media greaterThanOrEqual='tablet'>
            <Menu {...i}>
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
