import {LoadStatistic, PageContainer, SearchInput, useTitle} from "./components/Common";
import {useQuery} from "./hooks/customHooks";
import React, {useContext, useState} from "react";
import {StatusContext} from "./contexts/contexts";
import {DownloadMenu} from "./components/Download";
import {FilesSearchView} from "./components/Files";
import {
    Button,
    Divider,
    Header,
    Modal,
    ModalContent,
    ModalHeader,
    Segment,
    Statistic,
    StatisticGroup
} from "./components/Theme";
import {Link} from "react-router-dom";
import {BandwidthProgressCombined, CPUUsageProgress} from "./components/admin/Status";
import {ProgressPlaceholder} from "./components/Placeholder";
import {GridColumn, GridRow, Icon, Message} from "semantic-ui-react";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {refreshFiles} from "./api";
import _ from "lodash";
import {TagsDashboard} from "./Tags";
import {Upload} from "./components/Upload";

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
                <Message.Header>Your files are being refreshed.</Message.Header>
                <p><Link to='/files'>Click here to view the progress</Link></p>
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

    const {searchParams, updateQuery} = useQuery();
    const searchStr = searchParams.get('q');
    const activeTags = searchParams.getAll('tag');
    const setSearchStr = (value) => {
        updateQuery({q: value, o: null});
    }

    const {status} = useContext(StatusContext);
    const wrol_mode = status ? status['wrol_mode'] : null;

    // Getters are Downloads or Uploads.
    const [selectedGetter, setSelectedGetter] = useState(null);
    const gettersDisabled = status?.flags?.indexOf('refresh_complete') === -1;
    const handleSetGetter = (e, value) => {
        if (e) {
            e.preventDefault();
        }
        setSelectedGetter(value);
    }

    let getter = <Segment>
        <Grid columns={2} textAlign='center'>
            <Divider vertical>Or</Divider>
            <GridRow verticalAlign='middle'>
                <GridColumn>
                    <Button color='violet' onClick={e => handleSetGetter(e, 'downloads')}>
                        <Icon name='download'/>
                        Download
                    </Button>
                </GridColumn>
                <GridColumn>
                    <Button onClick={e => handleSetGetter(e, 'upload')}>
                        <Icon name='upload'/>
                        Upload
                    </Button>
                </GridColumn>
            </GridRow>
        </Grid>
    </Segment>;
    let getterModal;
    if (selectedGetter === 'downloads') {
        getterModal = <Modal closeIcon
            open={true}
            centered={false}
            onClose={() => handleSetGetter(null, null)}
        >
            <ModalHeader>Downloads</ModalHeader>
            <ModalContent>
                <DownloadMenu disabled={gettersDisabled}/>
            </ModalContent>
        </Modal>;
    } else if (selectedGetter === 'upload') {
        getterModal = <Modal closeIcon
            open={true}
            centered={false}
            onClose={() => handleSetGetter(null, null)}
        >
            <ModalHeader>Upload</ModalHeader>
            <ModalContent>
                <Upload disabled={gettersDisabled}/>
            </ModalContent>
        </Modal>;
    }

    // Only show dashboard parts if not searching.
    let body;
    if (searchStr || (activeTags && activeTags.length > 0)) {
        body = <FilesSearchView/>;
    } else {
        body = <>
            {!wrol_mode && getter}
            {getterModal}
            <TagsDashboard/>
            <DashboardStatus/>
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
