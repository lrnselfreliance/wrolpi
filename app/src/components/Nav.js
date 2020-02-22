import React from "react";
import {NavLink} from "react-router-dom";
import {Dropdown, Menu, Responsive} from "semantic-ui-react";

const responsiveWidth = 500;

const links = [
    {
        text: 'Videos', links: [
            {to: '/videos/manage', text: 'Manage', exact: true},
            {to: '/videos', text: 'Newest Videos', exact: true},
            {to: '/videos/channel', text: 'Channels', exact: true},
            {to: '/videos/favorites', text: 'Favorites', exact: true},
        ]
    },
    {to: '/map', text: 'Map'},
];
const settings = {to: '/settings', text: 'Settings', exact: true};
const rightLinks = [settings,];

const collapsedLinks = links.concat([settings,]);

function DropdownLinks(props) {
    return (
        <Dropdown item text={props.link.text}>
            <Dropdown.Menu>
                {props.link.links.map((l) => {
                    return (
                        <Link key={l.to} link={l}/>
                    )
                })}
            </Dropdown.Menu>
        </Dropdown>
    )
}

function Link(props) {
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
            <Link link={{to: '/', text: 'WROLPi', exact: true}}/>

            {/*Show the links in a menu when on desktop*/}
            {links.map((link) => {
                return (
                    <Responsive minWidth={responsiveWidth} as={Link} link={link} key={link.to}/>
                )
            })}
            <Responsive minWidth={responsiveWidth} as={Menu.Menu} position="right">
                {rightLinks.map((link) => {
                    return (<Link link={link} key={link.to}/>)
                })}
            </Responsive>

            {/*Show the menu items in a dropdown when on mobile*/}
            <Responsive as={Menu.Menu} maxWidth={responsiveWidth - 1} position='right'>
                <Dropdown item icon="bars">
                    <Dropdown.Menu>
                        {collapsedLinks.map((link) => {
                            return (<Link link={link} key={link.to}/>)
                        })}
                    </Dropdown.Menu>
                </Dropdown>
            </Responsive>
        </Menu>
    )
}
