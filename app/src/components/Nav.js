import React from "react";
import {Navbar} from "react-bootstrap";
import Nav from "react-bootstrap/Nav";
import {NavLink} from "react-router-dom";

const Modules = [
    {href: '/videos', name: 'Videos'},
    {href: '/map', name: 'Map'}
];

function Module(props) {
    return (
        <NavLink
            className="nav-link"
            to={props.href}
            activeClassName="active"
        >
            {props.name}
        </NavLink>
    )
}

function ModuleList(props) {
    return props.plugins.map(
        (plugin) => <Module key={plugin['href']} {...plugin}/>
    )
}

function NavSettings() {
    return (
        <Nav className="navbar-nav ml-auto">
            <NavLink
                className="nav-link"
                to="/settings"
                activeClassName="active"
            >
                Settings
            </NavLink>
        </Nav>
    )
}

export function NavBar() {
    return (
        <Navbar bg="light" expand="lg">
            <NavLink
                className="navbar-brand"
                to="/"
                exact={true}
                activeClassName="active"
            >
                WROLPi
            </NavLink>
            <Navbar.Toggle aria-controls="basic-navbar-nav"/>
            <Navbar.Collapse id="basic-navbar-nav">
                <Nav className="mr-auto">
                    <ModuleList plugins={Modules}/>
                </Nav>
                <Nav className="ml-auto">
                    <NavSettings/>
                </Nav>
            </Navbar.Collapse>
        </Navbar>
    )
}