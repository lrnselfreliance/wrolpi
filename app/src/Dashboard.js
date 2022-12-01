import {LoadStatistic, PageContainer, SearchInput, useTitle} from "./components/Common";
import {useSearchFiles} from "./hooks/customHooks";
import React, {useContext, useState} from "react";
import {StatusContext} from "./contexts/contexts";
import {DownloadMenu} from "./components/Download";
import {FilesSearchView} from "./components/Files";
import {Header, Segment, Statistic, StatisticGroup} from "./components/Theme";
import {Link} from "react-router-dom";
import {BandwidthProgressCombined, CPUUsageProgress} from "./components/admin/Status";
import {ProgressPlaceholder} from "./components/Placeholder";
import {Divider} from "semantic-ui-react";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";

export function Dashboard() {
    useTitle('Dashboard');

    const {searchStr, setSearchStr} = useSearchFiles();

    const {status} = useContext(StatusContext);
    const wrol_mode = status ? status['wrol_mode'] : null;

    const [downloadOpen, setDownloadOpen] = useState(false);
    const onDownloadOpen = (name) => setDownloadOpen(!!name);
    const downloads = <DownloadMenu onOpen={onDownloadOpen}/>;

    // Only show dashboard parts if not searching.
    let body;
    if (searchStr) {
        body = <FilesSearchView showLimit={true} showSelectButton={true}/>;
    } else {
        body = <>
            {!wrol_mode && downloads}
            {/* Hide Status when user is starting a download */}
            {!downloadOpen && <DashboardStatus/>}
        </>;
    }

    return (<PageContainer>
        <Grid>
            <Grid.Row>
                <Grid.Column mobile={16} computer={8}>
                    <SearchInput clearable
                                 searchStr={searchStr}
                                 onSubmit={setSearchStr}
                                 size='large'
                                 placeholder='Search Everywhere...'
                                 actionIcon='search'
                                 style={{marginBottom: '2em'}}
                    />
                </Grid.Column>
            </Grid.Row>
        </Grid>
        {body}
    </PageContainer>)
}

function DashboardStatus() {
    const {status} = useContext(StatusContext);

    let percent = 0;
    let load = {};
    let cores = 0;
    let pending_downloads = '?';
    if (status && status['cpu_info']) {
        percent = status['cpu_info']['percent'];
        load = status['load'];
        cores = status['cpu_info']['cores'];
    }

    const {downloads} = status;
    if (downloads) {
        pending_downloads = downloads['disabled'] ? 'x' : downloads['pending'];
    }

    let bandwidths = <ProgressPlaceholder/>;
    if (status && status['bandwidth']) {
        bandwidths = status['bandwidth'].map(i => <BandwidthProgressCombined key={i['name']} bandwidth={i}/>);
    }

    return <Segment>
        <Link to='/admin/status'>
            <Header as='h2'>Status</Header>
            <CPUUsageProgress value={percent} label='CPU Usage'/>

            <StatisticGroup size='mini'>
                <LoadStatistic label='1 Min. Load' value={load['minute_1']} cores={cores}/>
                <LoadStatistic label='5 Min. Load' value={load['minute_5']} cores={cores}/>
                <LoadStatistic label='15 Min. Load' value={load['minute_15']} cores={cores}/>
            </StatisticGroup>

            <Header as='h3'>Bandwidth</Header>
            {bandwidths}
        </Link>

        <Divider style={{marginTop: '3em'}}/>

        <Link to='/admin'>
            <StatisticGroup size='mini'>
                <Statistic label='Downloading' value={pending_downloads}/>
            </StatisticGroup>
        </Link>

    </Segment>;
}
