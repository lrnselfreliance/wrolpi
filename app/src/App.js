import React, {useContext, useEffect, useState} from 'react';
import './App.css';
import {NavBar} from "./components/Nav";
import {Link, Route, Routes} from "react-router-dom";
import {VideosRoute, VideoWrapper} from "./components/Videos";
import Admin, {CPUUsageProgress} from "./components/Admin";
import {Container, Divider} from "semantic-ui-react";
import 'semantic-ui-offline/semantic.min.css';
import {SemanticToastContainer} from 'react-semantic-toasts';
import 'react-semantic-toasts/styles/react-semantic-alert.css';
import {AppsRoute} from "./components/Apps";
import {InventoryRoute} from "./components/Inventory";
import {ArchiveRoute} from "./components/Archive";
import {DownloadMenu} from "./components/Upload";
import {LoadStatistic, PageContainer, SearchInput, useTitle} from "./components/Common";
import {FilesRoute, FilesSearchView} from "./components/Files";
import {useSearchFiles, useSettingsInterval, useStatus} from "./hooks/customHooks";
import {MapRoute} from "./components/Map";
import {darkTheme, lightTheme, SettingsContext, ThemeContext} from "./contexts/contexts";
import {Header, Segment, Statistic, StatisticGroup} from "./components/Theme";

function Dashboard() {
    useTitle('Dashboard');

    const {searchStr, setSearchStr} = useSearchFiles();

    const [downloadOpen, setDownloadOpen] = useState(false);
    const onDownloadOpen = (name) => setDownloadOpen(!!name);
    const {wrol_mode} = useContext(SettingsContext);

    const downloads = <DownloadMenu onOpen={onDownloadOpen}/>;

    // Only show dashboard parts if not searching.
    let body;
    if (searchStr) {
        body = <FilesSearchView showLimit={true} showSelect={true} showSelectButton={true}/>;
    } else {
        body = <>
            {!wrol_mode && downloads}
            {/* Hide Status when user is starting a download */}
            {!downloadOpen && <DashboardStatus/>}
        </>;
    }

    return (
        <PageContainer>
            <SearchInput clearable
                         searchStr={searchStr}
                         onSubmit={setSearchStr}
                         size='large'
                         placeholder='Search Everywhere...'
                         actionIcon='search'
                         style={{marginBottom: '2em'}}
            />
            {body}
        </PageContainer>
    )
}

function DashboardStatus() {
    const {status} = useStatus();
    let percent = 0;
    let load = {};
    let cores = 0;
    let pending_downloads = '?';
    if (status && status['cpu_info']) {
        percent = status['cpu_info']['percent'];
        load = status['load'];
        cores = status['cpu_info']['cores'];
        pending_downloads = status['downloads']['pending_downloads'];
    }

    const {download_manager_disabled, download_manager_stopped} = useContext(SettingsContext);
    if (pending_downloads === 0 && (download_manager_disabled || download_manager_stopped)) {
        pending_downloads = 'x';
    }

    return <Segment>
        <Link to='/admin/status'>
            <Header as='h2'>Status</Header>
            <CPUUsageProgress value={percent} label='CPU Usage'/>
            <Header as='h3'>Load</Header>
            <StatisticGroup size='mini'>
                <LoadStatistic label='1 Minute' value={load['minute_1']} cores={cores}/>
                <LoadStatistic label='5 Minute' value={load['minute_5']} cores={cores}/>
                <LoadStatistic label='15 Minute' value={load['minute_15']} cores={cores}/>
            </StatisticGroup>
        </Link>

        <Divider/>

        <Link to='/admin'>
            <StatisticGroup size='mini'>
                <Statistic label='Downloads' value={pending_downloads}/>
            </StatisticGroup>
        </Link>

    </Segment>;
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
    const {t} = useContext(ThemeContext);

    const {version} = useContext(SettingsContext);
    return <Container textAlign='center' style={{marginTop: '1.5em', marginBottom: '1em'}}>
        <span {...t}>WROLPi v{version} <a href='https://github.com/lrnselfreliance/wrolpi'>GitHub</a></span>
    </Container>
}

export default function App() {
    const {settings} = useSettingsInterval();

    const [i, setI] = useState({});
    const [s, setS] = useState({});
    const [t, setT] = useState({});
    const [theme, setTheme] = useState();

    const setDarkTheme = () => {
        console.debug('setDarkTheme');
        setI({inverted: true});
        setS({style: {backgroundColor: '#1B1C1D', color: '#dddddd'}});
        setT({style: {color: '#dddddd'}});
        setTheme(darkTheme);
        document.body.style.background = '#1B1C1D';
    }

    const setLightTheme = () => {
        console.debug('setLightTheme');
        setI({inverted: undefined});
        setS({});
        setT({});
        setTheme(lightTheme);
        document.body.style.background = '#FFFFFF';
    }

    useEffect(() => {
        window.matchMedia('(prefers-color-scheme: dark)').matches && setDarkTheme();

        window.matchMedia('(prefers-color-scheme: dark)').addEventListener(
            'change', (e) => e.matches && setDarkTheme());
        window.matchMedia('(prefers-color-scheme: light)').addEventListener(
            'change', (e) => e.matches && setLightTheme());
    }, []);

    const themeValue = {i, s, t, theme, setDarkTheme, setLightTheme};

    return (
        <ThemeContext.Provider value={themeValue}>
            <SettingsContext.Provider value={settings}>
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
                        <Route element={<PageNotFound/>}/>
                    </Routes>
                </>
                <SemanticToastContainer position="top-right"/>
                <Footer/>
            </SettingsContext.Provider>
        </ThemeContext.Provider>
    );
}
