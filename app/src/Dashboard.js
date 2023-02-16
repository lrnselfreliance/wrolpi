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
import {Divider, Icon, Message} from "semantic-ui-react";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {refreshFiles} from "./api";
import _ from "lodash";

function FlagsMessages({flags}) {
    if (!flags) {
        return <></>
    }

    let refreshing;
    let refreshRequired;
    let dbDown;

    // Do not tell the maintainer to refresh the files if they are already refreshing.
    if (flags.indexOf('refreshing') >= 0) {
        // Actively refreshing.
        refreshing = <Message icon>
            <Icon name='circle notched' loading/>
            <Message.Content>
                <Message.Header>Refreshing</Message.Header>
                Your files are being refreshed.
            </Message.Content>
        </Message>;
    } else if (flags.indexOf('refresh_complete') === -1) {
        // `refresh_complete` flag is not set.  Tell the maintainer to refresh the files.
        refreshRequired = <Message icon warning onClick={refreshFiles}>
            <Icon name='hand point right'/>
            <Message.Content>
                <Message.Header>Refresh required</Message.Header>
                <a href='#'>Click here</a> to refresh all your files.
            </Message.Content>
        </Message>;
    }

    if (flags.indexOf('db_up') === -1) {
        dbDown = <Message icon error>
            <Icon name='exclamation'/>
            <Message.Content>
                <Message.Header>Database is down</Message.Header>
                API is unable to connect to the database. Check the server logs.
            </Message.Content>
        </Message>
    }

    return <>
        {refreshing}
        {dbDown || refreshRequired}
    </>
}

export function Dashboard() {
    useTitle('Dashboard');

    const {searchStr, setSearchStr} = useSearchFiles();

    const {status} = useContext(StatusContext);
    const wrol_mode = status ? status['wrol_mode'] : null;

    const [downloadOpen, setDownloadOpen] = useState(false);
    const onDownloadOpen = (name) => setDownloadOpen(!!name);
    const downloadsDisabled = status?.flags?.indexOf('refresh_complete') === -1;
    const downloads = <Segment><DownloadMenu onOpen={onDownloadOpen} disabled={downloadsDisabled}/></Segment>;

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

    return <PageContainer>
        <Grid>
            <Grid.Row>
                <Grid.Column mobile={16} computer={8}>
                    <SearchInput clearable
                                 searchStr={searchStr}
                                 onSubmit={setSearchStr}
                                 size='large'
                                 placeholder='Search everywhere...'
                                 actionIcon='search'
                                 style={{marginBottom: '2em'}}
                    />
                </Grid.Column>
            </Grid.Row>
        </Grid>
        {!searchStr && <FlagsMessages flags={status['flags']}/>}
        {body}
    </PageContainer>
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
    if (!_.isEmpty(downloads)) {
        pending_downloads = downloads && downloads['disabled'] ? 'x' : downloads['pending'];
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
