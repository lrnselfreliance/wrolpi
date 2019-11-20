import React from 'react';
import './App.css';
import {Navbar} from "react-bootstrap";
import Nav from "react-bootstrap/Nav";
import NavLink from "react-bootstrap/NavLink";

const API = 'http://localhost:8080/api';

function Plugin(props) {
    return (
        <NavLink href={props.href}>{props.name}</NavLink>
    )
}

class PluginList extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            plugins: [],
        }
    }

    async componentDidMount() {
        let response = await fetch(API + '/plugins');
        let data = await response.json();
        this.setState({'plugins': data});
    }

    render() {
        return this.state.plugins.map((plugin) => <Plugin key={plugin[0]} href={plugin[0]} name={plugin[1]}/>)
    }
}

function NavBar() {
    return (
        <Navbar bg="dark" expand="lg">
            <Navbar.Brand href="/">WROLPi</Navbar.Brand>
            <Navbar.Toggle aria-controls="basic-navbar-nav"/>
            <Navbar.Collapse id="basic-navbar-nav">
                <Nav className="mr-auto">
                    <PluginList/>
                </Nav>
            </Navbar.Collapse>
        </Navbar>
    )
}

function App() {
    return (
        <div className="App">
            <header className="App-header">
                <NavBar/>
            </header>
        </div>
    );
}

export default App;
