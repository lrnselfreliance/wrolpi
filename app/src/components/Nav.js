import React from "react";
import {NavLink} from "react-router-dom";
import {Dropdown, Menu, Responsive} from "semantic-ui-react";

const responsiveWidth = 500;

const links = [
    {text: 'Videos', to: '/videos', key: 'videos'},
    {text: 'Archive', to: '/archive', key: 'archive'},
    {text: 'Map', to: '/map', key: 'map'},
    {text: 'Files', to: '/files', key: 'files'},
    {text: 'Inventory', to: '/inventory', key: 'inventory'},
    {
        key: 'apps', text: 'Apps', links: [
            {to: '/apps/otp', text: 'One Time Pad', exact: true},
        ]
    },
];
const admin = {to: '/admin', text: 'Admin', exact: true, key: 'admin'};
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

function MenuLink(props) {
    // Wrapper around NavLink to handle Navlink/Dropdown change.
    let classes = 'item';
    if (props.link.header) {
        classes = `${classes} header`;
    }

    if (!props.link.links) {
        return (
            <NavLink
                className={classes}
                exact={props.link.exact || false}
                to={props.link.to}
            >
                {props.link.text}
            </NavLink>
        )
    } else {
        return (
            <DropdownLinks link={props.link}/>
        )
    }
}

export function NavBar() {
    return (
        <Menu>
            {/*Always show WROLPi home button*/}
            <MenuLink link={{to: '/', text: 'WROLPi', exact: true}}/>

            {/*Show the links in a menu when on desktop*/}
            {links.map((link) => {
                return (
                    <Responsive minWidth={responsiveWidth} as={MenuLink} link={link} key={link.key}/>
                )
            })}
            <Responsive minWidth={responsiveWidth} as={Menu.Menu} position="right">
                {rightLinks.map((link) => <MenuLink link={link} key={link.key}/>)}
            </Responsive>

            {/*Show the menu items in a dropdown when on mobile*/}
            <Responsive as={Menu.Menu} maxWidth={responsiveWidth - 1} position='right'>
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
