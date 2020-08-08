import React from 'react';
import './App.css';
import {NavBar} from "./components/Nav";
import {Route, Switch} from "react-router-dom";
import {FavoriteVideosPreview, VideosRoute, VideoWrapper, ViewedVideosPreview} from "./components/Videos";
import Settings from "./components/Settings";
import {Container, Header, Segment} from "semantic-ui-react";
import 'semantic-ui-css/semantic.min.css';
import {SemanticToastContainer} from 'react-semantic-toasts';
import 'react-semantic-toasts/styles/react-semantic-alert.css';

function Welcome() {
    return (
        <Container style={{marginTop: '2em'}}>
            <Header as="h1">Welcome to WROLPi!</Header>
            <h3>
                Take your internet, off-grid.
            </h3>
            <Segment>
                <FavoriteVideosPreview/>
            </Segment>
            <Segment>
                <ViewedVideosPreview/>
            </Segment>
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
                <Route path='/videos/channel/:channel_link/video/:video_id' exact component={VideoWrapper}/>
                <Route path="/" exact={true} component={Welcome}/>
                <Route path="/videos" component={VideosRoute}/>
                <Route path="/settings" component={Settings}/>
                <Route component={PageNotFound}/>
            </Switch>
            <SemanticToastContainer position="top-right"/>
        </>
    );
}

export default App;
