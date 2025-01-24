import React, {useContext} from 'react';
import './App.css';
import {NavBar} from "./components/Nav";
import {createBrowserRouter, createRoutesFromElements, Link, Outlet, Route, RouterProvider} from "react-router-dom";
import {VideosRoute, VideoWrapper} from "./components/Videos";
import AdminRoute from "./components/admin/AdminRoute";
import {Container} from "semantic-ui-react";
import 'semantic-ui-offline/semantic.min.css';
import {MoreRoute} from "./components/Apps";
import {InventoryRoute} from "./components/Inventory";
import {ArchiveRoute} from "./components/Archive";
import {FilesRoute} from "./components/Files";
import {QueryProvider, StatusProvider} from "./hooks/customHooks";
import {MapRoute} from "./components/Map";
import {MediaContextProvider, mediaStyles, StatusContext, ThemeContext} from "./contexts/contexts";
import {Header, ThemeProvider} from "./components/Theme";
import {DashboardPage} from "./DashboardPage";
import {DonatePage} from "./components/DonatePage";
import {useEventsInterval} from "./Events";
import {SemanticToastContainer} from "react-semantic-toasts-2";
import {FilePreviewProvider} from "./components/FilePreview";
import {TagsProvider} from "./Tags";
import {ZimRoute} from "./components/Zim";

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
    let version;
    try {
        version = status?.version ? `v${status.version}` : null;
    } catch (e) {
        // Not logging because this is not that important.
    }
    return <Container textAlign='center' style={{marginTop: '1.5em', marginBottom: '1em', ...t}}>
        <span {...t}>
            WROLPi {version} <Dot/>
            <a href='https://wrolpi.org' target='_blank' rel='nofollow noreferrer'>WROLPi.org</a> <Dot/>
            <Link to='/donate'>Donate</Link>
            </span>
    </Container>
}

function Root() {
    return <QueryProvider>
        <ThemeProvider>
            <TagsProvider>
                <FilePreviewProvider>
                    <header>
                        <NavBar/>
                    </header>
                    <Outlet/>
                    <Footer/>
                </FilePreviewProvider>
            </TagsProvider>
        </ThemeProvider>
    </QueryProvider>
}

const router = createBrowserRouter(createRoutesFromElements(<Route
    path='/'
    element={<Root/>}
    errorElement={<PageNotFound/>}
>
    <Route index element={<DashboardPage/>}/>
    <Route path='search/*' element={<DashboardPage/>}/>
    <Route path='donate' element={<DonatePage/>}/>
    <Route path='videos/video/:videoId' exact element={<VideoWrapper/>}/>
    <Route path='videos/channel/:channelId/video/:videoId' exact element={<VideoWrapper/>}/>
    <Route path="videos/*" element={<VideosRoute/>}/>
    <Route path="admin/*" element={<AdminRoute/>}/>
    <Route path="more/*" element={<MoreRoute/>}/>
    <Route path="inventory/*" element={<InventoryRoute/>}/>
    <Route path='archive/*' element={<ArchiveRoute/>}/>
    <Route path='map/*' element={<MapRoute/>}/>
    <Route path='zim/*' element={<ZimRoute/>}/>
    <Route path='files/*' element={<FilesRoute/>}/>
</Route>));

export default function App() {
    useEventsInterval();

    return <StatusProvider>
        {/* Context and style to handle switching between mobile/computer. */}
        <style>{mediaStyles}</style>
        {/* Toasts can be on any page. */}
        <SemanticToastContainer position='top-right'/>
        <MediaContextProvider>
            <RouterProvider router={router}/>
        </MediaContextProvider>
    </StatusProvider>
}
