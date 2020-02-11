import React from "react";
import {NavLink} from "react-router-dom";
import {Dropdown, Menu, Responsive} from "semantic-ui-react";

const links = [
    {to: '/videos', text: 'Videos'},
    {to: '/map', text: 'Map'},
];

const settings = {to: '/settings', text: 'Settings', exact: true};

const collapsedLinks = links.concat([settings,]);

const rightLinks = [settings,];

const responsiveWidth = 500;

function NavLink_(props) {
    return (
        <NavLink
            className="item"
            exact={props.link.exact || false}
            to={props.link.to}
        >
            {props.link.text}
        </NavLink>
    )
}

export function NavBar() {
    return (
        <Menu>
            {/*Always show WROLPi home button*/}
            <NavLink_ link={{to: '/', text: 'WROLPi', exact: true}}/>

            {/*Show the links in a menu when on desktop*/}
            {links.map((link) => {
                return (
                    <Responsive minWidth={responsiveWidth}
                                as={NavLink_}
                                link={link}
                    />
                )
            })}
            <Responsive minWidth={responsiveWidth}
                        as={Menu.Menu}
                        position="right">
                {rightLinks.map((link) => {
                    return (<NavLink_ link={link}/>)
                })}
            </Responsive>

            {/*Show the menu items in a dropdown when on mobile*/}
            <Responsive as={Menu.Menu} maxWidth={responsiveWidth - 1} position='right'>
                <Dropdown item icon="bars">
                    <Dropdown.Menu>
                        {collapsedLinks.map((link) => {
                            return (<NavLink_ link={link}/>)
                        })}
                    </Dropdown.Menu>
                </Dropdown>
            </Responsive>
        </Menu>
    )
}