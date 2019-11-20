import React, {useState} from 'react';
import './App.css';
import {Button, Col, Container, Form, FormControl, Navbar} from "react-bootstrap";
import Nav from "react-bootstrap/Nav";
import NavLink from "react-bootstrap/NavLink";
import Row from "react-bootstrap/Row";

const API_URL = 'http://localhost:8080/api';

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
        let response = await fetch(API_URL + '/plugins');
        let data = await response.json();
        this.setState({'plugins': data});
    }

    render() {
        return this.state.plugins.map(
            (plugin) => <Plugin key={plugin[0]} href={plugin[0]} name={plugin[1]}/>
            )
    }
}

function Settings() {
    return (
        <Nav className="navbar-nav ml-auto">
            <NavLink className="nav-link" href="/settings">Settings</NavLink>
        </Nav>
    )
}

function NavSearch() {
    const [inputText, setInputText] = useState('');

    function handleChange(event) {
        setInputText(event.target.value);
    }

    function handleSubmit(event) {
        event.preventDefault();
    }

    return (
        <Form inline>
            <FormControl
                type="text"
                className="mr-sm-2"
                placeholder="Search"
                onChange={handleChange}
                onSubmit={handleSubmit}
            />
            <Button type="submit" variant="outline-success">Search</Button>
        </Form>
    )
}

function NavBar() {
    return (
        <Navbar bg="light" expand="lg">
            <Navbar.Brand href="/">WROLPi</Navbar.Brand>
            <Navbar.Toggle aria-controls="basic-navbar-nav"/>
            <Navbar.Collapse id="basic-navbar-nav">
                <Nav className="mr-auto">
                    <PluginList/>
                </Nav>
                <NavSearch/>
                <Nav className="ml-auto">
                    <Settings/>
                </Nav>
            </Navbar.Collapse>
        </Navbar>
    )
}

function Body() {
    return (
        <Container id="body">
            <Row>
                <Col>
                    <h1>Welcome to WROLPi!</h1>
                </Col>
            </Row>
        </Container>
    )
}

function App() {
    return (
        <>
            <header>
                <NavBar/>
            </header>
            <Body/>
        </>
    );
}

export default App;
