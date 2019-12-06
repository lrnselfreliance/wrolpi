import React from "react";
import {Button, Form, FormControl, Navbar} from "react-bootstrap";
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

function NavSearch() {

    function handleSubmit(event) {
        event.preventDefault();
    }

    return (
        <Form inline>
            <FormControl
                type="text"
                className="mr-sm-2"
                placeholder="Search"
                onSubmit={handleSubmit}
            />
            <Button type="submit" variant="outline-success">
                <span className="fas fa-search"/>
            </Button>
        </Form>
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
                <NavSearch/>
                <Nav className="ml-auto">
                    <NavSettings/>
                </Nav>
            </Navbar.Collapse>
        </Navbar>
    )
}