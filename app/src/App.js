import React from 'react';
import './App.css';
import {NavBar} from "./components/Nav";
import {Route, Switch} from "react-router-dom";
import {NewestVideosPreview, VideosRoute} from "./components/Videos";
import Map_ from "./components/Map";
import Settings from "./components/Settings";
import {Container, Header} from "semantic-ui-react";
import 'semantic-ui-css/semantic.min.css';
import {SemanticToastContainer} from 'react-semantic-toasts';
import 'react-semantic-toasts/styles/react-semantic-alert.css';

function Welcome() {
    return (
        <Container style={{marginTop: '2em'}}>
            <Header as="h1">Welcome to WROLPi!</Header>
            <p>
                Take your internet, off-grid.
            </p>
            <NewestVideosPreview />
        </Container>
    )
}

function PageNotFound() {
    return (
        <Container>
            <h1 className="display-4">Page Not Found!</h1>
            <p>The page you requested cannot be found</p>
        </Container>
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
            <SemanticToastContainer position="top-right"/>
        </>
    );
}

export default App;
