import React, {useContext} from 'react';
import './App.css';
import {NavBar} from "./components/Nav";
import {createBrowserRouter, createRoutesFromElements, Link, Outlet, Route, RouterProvider} from "react-router-dom";
import {VideosRoute, VideoWrapper} from "./components/Videos";
import Admin from "./components/admin/Admin";
import {Container} from "semantic-ui-react";
import 'semantic-ui-offline/semantic.min.css';
import {MoreRoute} from "./components/Apps";
import {InventoryRoute} from "./components/Inventory";
import {ArchiveRoute} from "./components/Archive";
import {FilesRoute} from "./components/Files";
import {useStatusInterval} from "./hooks/customHooks";
import {MapRoute} from "./components/Map";
import {MediaContextProvider, mediaStyles, StatusContext, ThemeContext} from "./contexts/contexts";
import {Header, ThemeWrapper} from "./components/Theme";
import {Dashboard} from "./Dashboard";
import {Donate} from "./components/Donate";
import {useEventsInterval} from "./Events";
import {SemanticToastContainer} from "react-semantic-toasts-2";
import {FilePreviewWrapper} from "./components/FilePreview";
import {TagsContext, useTags, useTagsInterval} from "./Tags";

function PageNotFound() {
    const {t} = useContext(ThemeContext);
    return <Container fluid>
        <Header as='h1'>Page Not Found!</Header>
        <p {...t}>The page you requested cannot be found</p>
    </Container>
}

function Dot() {
    return <>&nbsp;•&nbsp;</>
}

function Footer() {
    const {t} = useContext(ThemeContext);
    const {status} = useContext(StatusContext);
    let {version} = status;
    version = version ? `v${version}` : null;
    return <Container textAlign='center' style={{marginTop: '1.5em', marginBottom: '1em', ...t}}>
        <span {...t}>
            WROLPi {version} <Dot/>
            <a href='https://wrolpi.org' target='_blank' rel='nofollow noreferrer'>WROLPi.org</a> <Dot/>
            <Link to='/donate'>Donate</Link>
            </span>
    </Container>
}

function Root() {
    return <>
        <header>
            <NavBar/>
        </header>
        <Outlet/>
        <Footer/>
    </>
}

const router = createBrowserRouter(createRoutesFromElements(<Route
    path='/'
    element={<Root/>}
    errorElement={<PageNotFound/>}
>
    <Route index element={<Dashboard/>}/>
    <Route path='donate' element={<Donate/>}/>
    <Route path='videos/video/:videoId' exact element={<VideoWrapper/>}/>
    <Route path='videos/channel/:channelId/video/:videoId' exact element={<VideoWrapper/>}/>
    <Route path="videos/*" element={<VideosRoute/>}/>
    <Route path="admin/*" element={<Admin/>}/>
    <Route path="more/*" element={<MoreRoute/>}/>
    <Route path="inventory/*" element={<InventoryRoute/>}/>
    <Route path='archive/*' element={<ArchiveRoute/>}/>
    <Route path='map/*' element={<MapRoute/>}/>
    <Route path='files/*' element={<FilesRoute/>}/>
</Route>));

export default function App() {
    const statusValue = useStatusInterval();
    const tagsValue = useTagsInterval();

    useEventsInterval();

    return <ThemeWrapper>
        <TagsContext.Provider value={tagsValue}>
            <FilePreviewWrapper>
                {/* Context and style to handle switching between mobile/computer. */}
                <style>{mediaStyles}</style>
                {/* Toasts can be on any page. */}
                <SemanticToastContainer position='top-right'/>
                <MediaContextProvider>
                    <StatusContext.Provider value={statusValue}>
                        <RouterProvider router={router}/>
                    </StatusContext.Provider>
                </MediaContextProvider>
            </FilePreviewWrapper>
        </TagsContext.Provider>
    </ThemeWrapper>
}
