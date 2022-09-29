import {LoadStatistic, PageContainer, SearchInput, useTitle} from "./components/Common";
import {useSearchFiles, useStatus} from "./hooks/customHooks";
import React, {useContext, useState} from "react";
import {SettingsContext} from "./contexts/contexts";
import {DownloadMenu} from "./components/Upload";
import {FilesSearchView} from "./components/Files";
import {Header, Segment, Statistic, StatisticGroup} from "./components/Theme";
import {Link} from "react-router-dom";
import {CPUUsageProgress} from "./components/admin/Status";
import {Divider} from "semantic-ui-react";

export function Dashboard() {
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
                <Statistic label='Downloading' value={pending_downloads}/>
            </StatisticGroup>
        </Link>

    </Segment>;
}
