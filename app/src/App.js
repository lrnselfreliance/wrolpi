import React from 'react';
import './App.css';
import {NavBar} from "./components/Nav";
import {Route, Switch, useHistory} from "react-router-dom";
import {VideosPreview, VideosRoute, VideoWrapper} from "./components/Videos";
import Admin from "./components/Admin";
import {Container, Divider, Header} from "semantic-ui-react";
import 'semantic-ui-offline/semantic.min.css';
import {SemanticToastContainer} from 'react-semantic-toasts';
import 'react-semantic-toasts/styles/react-semantic-alert.css';
import {AppsRoute} from "./components/Apps";
import {InventoryRoute} from "./components/Inventory";
import {ArchiveRoute, ArchivesList} from "./components/Archive";
import {Saver} from "./components/Upload";
import {MoreButton, PageContainer, SearchInput} from "./components/Common";
import {FilesRoute} from "./components/Files";
import {useSearch, useUp, useVersion} from "./hooks/customHooks";
import {MapRoute} from "./components/Map";

function Welcome() {
    const {searchStr, setSearchStr, archives, videos} = useSearch();
    const history = useHistory();
    useUp();

    let body = (
        <>
            <Header as='h2'>Save your media</Header>
            <Saver/>
        </>
    );

    if (searchStr) {
        let archiveMore = () => {
            history.push(`/archive?q=${searchStr}`);
        };
        let videosMore = () => {
            history.push(`/videos?q=${searchStr}&o=rank`);
        };

        body = (<>
            <Header as='h2'>Archives</Header>
            <ArchivesList archives={archives} searchStr={searchStr}/>
            <MoreButton onClick={archiveMore} disabled={!archives || archives.length === 0}/>

            <Divider/>

            <Header as='h2'>Videos</Header>
            <VideosPreview videos={videos}/>
            <MoreButton onClick={videosMore} disabled={!videos || videos.length === 0}/>
        </>);
    }

    return (
        <PageContainer>
            <SearchInput initValue={searchStr} onSubmit={setSearchStr} size='big' placeholder='Search Everywhere...'/>
            {body}
        </PageContainer>
    )
}

function PageNotFound() {
    return (
        <Container fluid>
            <h1 className="display-4">Page Not Found!</h1>
            <p>The page you requested cannot be found</p>
        </Container>
    )
}

function Footer() {
    const version = useVersion();
    return <Container textAlign='center' style={{marginTop: '1.5em', marginBottom: '1em'}}>
        WROLPi v{version} <a href='https://github.com/lrnselfreliance/wrolpi'>GitHub</a>
    </Container>
}

export default function App() {
    return (
        <>
            <header>
                <NavBar/>
            </header>
            <>
                <Switch>
                    <Route path='/videos/video/:video_id' exact component={VideoWrapper}/>
                    <Route path='/videos/channel/:channel_id/video/:video_id' exact component={VideoWrapper}/>
                    <Route path="/" exact={true} component={Welcome}/>
                    <Route path="/videos" component={VideosRoute}/>
                    <Route path="/admin" component={Admin}/>
                    <Route path="/apps" component={AppsRoute}/>
                    <Route path="/inventory" component={InventoryRoute}/>
                    <Route path='/archive' component={ArchiveRoute}/>
                    <Route path='/map' component={MapRoute}/>
                    <Route path='/files' component={FilesRoute}/>
                    <Route component={PageNotFound}/>
                </Switch>
            </>
            <SemanticToastContainer position="top-right"/>
            <Footer/>
        </>
    );
}
