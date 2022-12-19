import React, {useContext} from 'react';
import './App.css';
import {NavBar} from "./components/Nav";
import {Link, Route, Routes} from "react-router-dom";
import {VideosRoute, VideoWrapper} from "./components/Videos";
import Admin from "./components/admin/Admin";
import {Container} from "semantic-ui-react";
import 'semantic-ui-offline/semantic.min.css';
import {SemanticToastContainer} from 'react-semantic-toasts';
import 'react-semantic-toasts/styles/react-semantic-alert.css';
import {AppsRoute} from "./components/Apps";
import {InventoryRoute} from "./components/Inventory";
import {ArchiveRoute} from "./components/Archive";
import {FilesRoute} from "./components/Files";
import {useStatusInterval} from "./hooks/customHooks";
import {MapRoute} from "./components/Map";
import {StatusContext, ThemeContext} from "./contexts/contexts";
import {ThemeWrapper} from "./components/Theme";
import {Dashboard} from "./Dashboard";
import {Donate} from "./components/Donate";

function PageNotFound() {
    return <Container fluid>
        <h1 className="display-4">Page Not Found!</h1>
        <p>The page you requested cannot be found</p>
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
            <a href='https://discord.gg/HrwFk7nqA2'>Discord</a> <Dot/>
            <a href='https://github.com/lrnselfreliance/wrolpi'>GitHub</a> <Dot/>
            <Link to='/donate'>Donate</Link>
            </span>
    </Container>
}

export default function App() {
    const status = useStatusInterval();

    return (<ThemeWrapper>
        <StatusContext.Provider value={status}>
            <header>
                <NavBar/>
            </header>
            <>
                <Routes>
                    <Route path='/videos/video/:videoId' exact element={<VideoWrapper/>}/>
                    <Route path='/videos/channel/:channelId/video/:videoId' exact element={<VideoWrapper/>}/>
                    <Route path="/" exact element={<Dashboard/>}/>
                    <Route path="/videos/*" element={<VideosRoute/>}/>
                    <Route path="/admin/*" element={<Admin/>}/>
                    <Route path="/apps/*" element={<AppsRoute/>}/>
                    <Route path="/inventory/*" element={<InventoryRoute/>}/>
                    <Route path='/archive/*' element={<ArchiveRoute/>}/>
                    <Route path='/map/*' element={<MapRoute/>}/>
                    <Route path='/files/*' element={<FilesRoute/>}/>
                    <Route path='/donate' element={<Donate/>}/>
                    <Route element={<PageNotFound/>}/>
                </Routes>
            </>
            <SemanticToastContainer position="top-right"/>
            <Footer/>
        </StatusContext.Provider>
    </ThemeWrapper>);
}
