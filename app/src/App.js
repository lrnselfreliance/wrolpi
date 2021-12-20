import React from 'react';
import './App.css';
import {NavBar} from "./components/Nav";
import {Route, Switch} from "react-router-dom";
import {FavoriteVideosPreview, VideosRoute, VideoWrapper, ViewedVideosPreview} from "./components/Videos";
import Admin from "./components/Admin";
import {Container, Divider, Header, Segment} from "semantic-ui-react";
import 'semantic-ui-offline/semantic.min.css';
import {SemanticToastContainer} from 'react-semantic-toasts';
import 'react-semantic-toasts/styles/react-semantic-alert.css';
import {AppsRoute} from "./components/Apps";
import {InventoryRoute} from "./components/Inventory";
import {ArchiveRoute} from "./components/Archive";
import {Saver} from "./components/Upload";

function Welcome() {
    return (
        <Container style={{marginTop: '2em'}}>
            <Header as='h2'>Save your media</Header>
            <Saver/>

            <Divider/>

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

export default function App() {
    return (
        <>
            <header>
                <NavBar/>
            </header>
            <Switch>
                <Route path='/videos/video/:video_id' exact component={VideoWrapper}/>
                <Route path='/videos/channel/:channel_link/video/:video_id' exact component={VideoWrapper}/>
                <Route path="/" exact={true} component={Welcome}/>
                <Route path="/videos" component={VideosRoute}/>
                <Route path="/admin" component={Admin}/>
                <Route path="/apps" component={AppsRoute}/>
                <Route path="/inventory" component={InventoryRoute}/>
                <Route path='/archive' component={ArchiveRoute}/>
                <Route component={PageNotFound}/>
            </Switch>
            <SemanticToastContainer position="top-right"/>
        </>
    );
}
