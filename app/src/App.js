import React, {useEffect, useState} from 'react';
import './App.css';
import {NavBar} from "./components/Nav";
import {Route, Switch} from "react-router-dom";
import {VideosPreview, VideosRoute, VideoWrapper} from "./components/Videos";
import Admin from "./components/Admin";
import {Container, Header} from "semantic-ui-react";
import 'semantic-ui-offline/semantic.min.css';
import {SemanticToastContainer} from 'react-semantic-toasts';
import 'react-semantic-toasts/styles/react-semantic-alert.css';
import {AppsRoute} from "./components/Apps";
import {InventoryRoute} from "./components/Inventory";
import {ArchiveRoute, ArchivesList} from "./components/Archive";
import {Saver} from "./components/Upload";
import {useSearchParam} from "./hooks/useSearchParam";
import {searchArchives, searchVideos} from "./api";
import {SearchInput} from "./components/Common";

const useSearch = () => {
    let [searchStr, setSearchStr] = useSearchParam('q');

    const [archives, setArchives] = useState();
    const [videos, setVideos] = useState();

    const localSearchArchives = async (term) => {
        setArchives(null);
        const [archives, total] = await searchArchives(0, 6, null, term);
        setArchives(archives);
    }

    const localSearchVideos = async (term) => {
        setVideos(null);
        const [videos, total] = await searchVideos(0, 6, null, term);
        setVideos(videos);
    }

    useEffect(() => {
        localSearchArchives(searchStr);
        localSearchVideos(searchStr)
    }, [searchStr]);

    return {searchStr, setSearchStr, archives, videos}
}

function Welcome() {
    const {searchStr, setSearchStr, archives, videos} = useSearch();

    let body = (
        <>
            <Header as='h2'>Save your media</Header>
            <Saver/>
        </>
    );

    if (searchStr) {
        body = (<>
            <Header as='h3'>Archives</Header>
            <ArchivesList archives={archives} searchStr={searchStr}/>

            <Header as='h3'>Videos</Header>
            <VideosPreview videos={videos}/>
        </>);
    }

    return (
        <Container style={{marginTop: '2em'}}>
            <SearchInput initValue={searchStr} onSubmit={setSearchStr} size='big'/>
            {body}
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
