import React from 'react';
import './App.css';
import {Container, Jumbotron} from "react-bootstrap";
import {NavBar} from "./components/Nav";
import {Route, Switch} from "react-router-dom";
import VideosRoute from "./components/Videos";
import Map_ from "./components/Map";
import Settings from "./components/Settings";

function Welcome() {
    return (
        <Jumbotron>
            <h1 className="display-4">Welcome to WROLPi!</h1>
            <p className="lead">
                Bring your personal internet, off-grid.
            </p>
        </Jumbotron>
    )
}

function PageNotFound() {
    return (
        <Jumbotron>
            <h1 className="display-4">Page Not Found!</h1>
            <p>The page you requested cannot be found</p>
        </Jumbotron>
    )
}

function App() {
    return (
        <>
            <header>
                <NavBar/>
            </header>
            <Switch>
                <Route path="/" exact={true} component={Welcome}/>
                <Route path="/videos" component={VideosRoute}/>
                <Route path="/map" component={Map_}/>
                <Route path="/settings" component={Settings}/>
                <Route component={PageNotFound}/>
            </Switch>
        </>
    );
}

export default App;
