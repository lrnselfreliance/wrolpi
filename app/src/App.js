import React, {useContext} from 'react';
import './App.css';
import {NavBar} from "./components/Nav";
import {createBrowserRouter, createRoutesFromElements, Link, Outlet, Route, RouterProvider} from "react-router";
import {VideosTabLayout, VideosPage, VideosSettingsPage, VideosStatistics, VideoWrapper} from "./components/Videos";
import AdminRoute from "./components/admin/AdminRoute";
import {Box, Header} from "./components/ui";
import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';
// Theme tokens load last so they win over both component libraries.
import './themes/fonts.css';
import './themes/tokens.css';
import {MediaFilterDefs} from "./themes/MediaFilterDefs";
import {MoreRoute} from "./components/Apps";
import {InventoryRoute} from "./components/inventory/InventoryRoute";
import {ArchiveRoute} from "./components/Archive";
import {FilesRoute} from "./components/Files";
import {QueryProvider, StatusProvider} from "./hooks/customHooks";
import {FileWorkerStatusProvider} from "./contexts/FileWorkerStatusContext";
import {ChannelEditPage, ChannelNewPage, ChannelsPage} from "./components/Channels";
import {MapRoute} from "./components/Map";
import {MediaContextProvider, mediaStyles, StatusContext} from "./contexts/contexts";
import {ThemeProvider} from "./components/Theme";
import {DashboardPage} from "./DashboardPage";
import {DonatePage} from "./components/DonatePage";
import {ThemeSamplePage} from "./components/ThemeSamplePage";
import {useEventsInterval} from "./Events";
import {FilePreviewProvider} from "./components/FilePreview";
import {TagsProvider} from "./Tags";
import {ZimRoute} from "./components/Zim";
import {PlaylistsRoute} from "./components/Playlists";
import {DocsRoute} from "./components/Docs";
import {FlasherRoute} from "./components/Flasher";
import ErrorBoundary from "./components/ErrorBoundary";
import {KeyboardShortcutsProvider} from "./components/KeyboardShortcutsProvider";

function PageNotFound() {
    return <Box>
        <Header as='h1'>Page Not Found!</Header>
        <p>The page you requested cannot be found</p>
    </Box>
}

function Dot() {
    return <>&nbsp;•&nbsp;</>
}

function Footer() {
    const {status} = useContext(StatusContext);
    let version;
    try {
        version = status?.version ? `v${status.version}` : null;
    } catch (e) {
        // Not logging because this is not that important.
    }
    return <Box style={{textAlign: 'center', marginTop: '1.5em', marginBottom: '1em'}}>
        <span>
            WROLPi {version} <Dot/>
            <a href='https://wrolpi.org' target='_blank' rel='nofollow noreferrer'>WROLPi.org</a> <Dot/>
            <Link to='/donate'>Donate</Link>
            </span>
    </Box>
}

function Root() {
    return <QueryProvider>
        <ThemeProvider>
            <MediaFilterDefs/>
            <TagsProvider>
                <KeyboardShortcutsProvider>
                    <FilePreviewProvider>
                        <header>
                            <NavBar/>
                        </header>
                        <ErrorBoundary>
                            <Outlet/>
                        </ErrorBoundary>
                        <Footer/>
                    </FilePreviewProvider>
                </KeyboardShortcutsProvider>
            </TagsProvider>
        </ThemeProvider>
    </QueryProvider>
}

const router = createBrowserRouter(createRoutesFromElements(<Route
    path='/'
    element={<Root/>}
    errorElement={<PageNotFound/>}
>
    <Route index element={<ErrorBoundary><DashboardPage/></ErrorBoundary>}/>
    <Route path='search/*' element={<ErrorBoundary><DashboardPage/></ErrorBoundary>}/>
    <Route path='donate' element={<DonatePage/>}/>
    {/* Component gallery: lets a user see a theme before committing to it, and lets us
        review the design.  Linked from Settings. */}
    <Route path='theme-sample' element={<ErrorBoundary><ThemeSamplePage/></ErrorBoundary>}/>
    <Route path='videos'>
        <Route element={<ErrorBoundary><VideosTabLayout/></ErrorBoundary>}>
            <Route index element={<ErrorBoundary><VideosPage/></ErrorBoundary>}/>
            <Route path='channel' element={<ErrorBoundary><ChannelsPage/></ErrorBoundary>}/>
            <Route path='channel/new' element={<ErrorBoundary><ChannelNewPage/></ErrorBoundary>}/>
            <Route path='channel/:channelId/edit' element={<ErrorBoundary><ChannelEditPage/></ErrorBoundary>}/>
            <Route path='channel/:channelId/video' element={<ErrorBoundary><VideosPage/></ErrorBoundary>}/>
            <Route path='settings' element={<ErrorBoundary><VideosSettingsPage/></ErrorBoundary>}/>
            <Route path='statistics' element={<ErrorBoundary><VideosStatistics/></ErrorBoundary>}/>
        </Route>
        <Route path=':fileGroupId' element={<ErrorBoundary><VideoWrapper/></ErrorBoundary>}/>
    </Route>
    <Route path="admin/*" element={<ErrorBoundary><AdminRoute/></ErrorBoundary>}/>
    <Route path="more/*" element={<ErrorBoundary><MoreRoute/></ErrorBoundary>}/>
    <Route path="inventory/*" element={<ErrorBoundary><InventoryRoute/></ErrorBoundary>}/>
    <Route path='archives/*' element={<ErrorBoundary><ArchiveRoute/></ErrorBoundary>}/>
    <Route path='docs/*' element={<ErrorBoundary><DocsRoute/></ErrorBoundary>}/>
    <Route path='map/*' element={<ErrorBoundary><MapRoute/></ErrorBoundary>}/>
    <Route path='zim/*' element={<ErrorBoundary><ZimRoute/></ErrorBoundary>}/>
    <Route path='playlists/*' element={<ErrorBoundary><PlaylistsRoute/></ErrorBoundary>}/>
    <Route path='files/*' element={<ErrorBoundary><FilesRoute/></ErrorBoundary>}/>
    <Route path='flasher/*' element={<ErrorBoundary><FlasherRoute/></ErrorBoundary>}/>
</Route>));

export default function App() {
    useEventsInterval();

    return <StatusProvider>
        <FileWorkerStatusProvider>
            {/* Context and style to handle switching between mobile/computer. */}
            <style>{mediaStyles}</style>
            {/* Toasts (from components/ui) are mounted by ThemeProvider, which wraps every page. */}
            <MediaContextProvider>
                <RouterProvider router={router}/>
            </MediaContextProvider>
        </FileWorkerStatusProvider>
    </StatusProvider>
}
