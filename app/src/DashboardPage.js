import {LoadStatistic, PageContainer, SearchResultsInput, useTitle} from "./components/Common";
import React, {useContext, useState} from "react";
import {Media, SettingsContext, StatusContext} from "./contexts/contexts";
import {DownloadMenu} from "./components/Download";
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
import {Link, useNavigate} from "react-router-dom";
import {BandwidthProgressCombined, CPUUsageProgress} from "./components/admin/Status";
import {ProgressPlaceholder} from "./components/Placeholder";
import {GridColumn, GridRow, Icon, Message} from "semantic-ui-react";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {refreshFiles} from "./api";
import _ from "lodash";
import {TagsDashboard} from "./Tags";
import {Upload} from "./components/Upload";
import {SearchView, useSearch, useSearchSuggestions} from "./components/Search";
import {KiwixRestartMessage, OutdatedZimsMessage} from "./components/Zim";
import {useSearchFilter, useWROLMode} from "./hooks/customHooks";
import {FileSearchFilterButton} from "./components/Files";
import {DateSelectorButton} from "./components/DatesSelector";

function FlagsMessages() {
    const {settings, fetchSettings} = React.useContext(SettingsContext);
    const {status} = useContext(StatusContext);

    if (!status || !'flags' in status || _.isEmpty(status['flags'])) {
        return <></>
    }

    const flags = status['flags'];

    let refreshing;
    let refreshRequired;
    let dbDown;
    let kiwixRestart;

    // Do not tell the maintainer to refresh the files if they are already refreshing.
    if (flags['refreshing']) {
        // Actively refreshing.
        refreshing = <Message icon>
            <Icon name='circle notched' loading/>
            <Message.Content>
                <Message.Header>Your files are being refreshed.</Message.Header>
                <p><Link to='/files'>Click here to view the progress</Link></p>
            </Message.Content>
        </Message>;
    } else if (!flags['refresh_complete']) {
        // `refresh_complete` flag is not set.  Tell the maintainer to refresh the files.
        refreshRequired = <Message icon warning onClick={refreshFiles}>
            <Icon name='hand point right'/>
            <Message.Content>
                <Message.Header>Refresh required</Message.Header>
                <a href='#'>Click here</a> to refresh all your files.
            </Message.Content>
        </Message>;
    }

    if (flags['kiwix_restart']) {
        kiwixRestart = <KiwixRestartMessage/>;
    }

    if (!flags['db_up']) {
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
        {settings && settings['ignore_outdated_zims'] === false && flags['outdated_zims'] ?
            <OutdatedZimsMessage onClick={fetchSettings}/> : null}
        {kiwixRestart}
    </>
}

export function Getters() {
    const {status} = useContext(StatusContext);
    const wrolModeEnabled = useWROLMode();

    // Getters are Downloads or Uploads.
    const [selectedGetter, setSelectedGetter] = useState(null);
    const gettersDisabled = status?.flags?.refresh_complete !== true;

    const handleSetGetter = (e, value) => {
        if (e) {
            e.preventDefault();
        }
        setSelectedGetter(value);
    }

    const getter = <Segment>
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
            <ModalHeader>Download from the Internet</ModalHeader>
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
            <ModalHeader>Upload from your device</ModalHeader>
            <ModalContent>
                <Upload disabled={gettersDisabled}/>
            </ModalContent>
        </Modal>;
    }

    if (wrolModeEnabled) {
        return <></>
    }

    return <>
        {getter}
        {getterModal}
    </>
}

export function DashboardPage() {
    const navigate = useNavigate();

    // The search the user submitted.
    const {searchStr, setSearchStr, activeTags, isEmpty} = useSearch();
    // The search that the user is typing.
    const [localSearchStr, setLocalSearchStr] = React.useState(searchStr);
    const {
        suggestions,
        suggestionsResults,
        suggestionsSums,
        handleResultSelect,
        resultRenderer,
        loading,
        setSearchStr: setSuggestionSearchStr,
        setSearchTags,
        months, dateRange, setDates, clearDate,
    } = useSearchSuggestions(searchStr, activeTags);

    React.useEffect(() => {
        setSuggestionSearchStr(localSearchStr);
    }, [localSearchStr]);

    React.useEffect(() => {
        setLocalSearchStr(searchStr);
    }, [searchStr]);

    React.useEffect(() => {
        if (activeTags) {
            setSearchTags(activeTags);
        }
    }, [JSON.stringify(activeTags)]);

    let title = 'Dashboard';
    if (searchStr) {
        title = `Search: ${searchStr} - Dashboard`;
    } else if (activeTags && activeTags.length === 1) {
        title = `Tag: ${activeTags[0]} - Dashboard`;
    } else if (activeTags && activeTags.length > 1) {
        const tagNames = activeTags.join(' & ');
        title = `Tags: ${tagNames} - Dashboard`;
    }
    useTitle(title);

    // Only show dashboard parts if not searching.
    let body = <React.Fragment>
        <Getters/>
        <TagsDashboard/>
        <DashboardStatus/>
    </React.Fragment>;
    if (searchStr || (activeTags && activeTags.length > 0)) {
        // User has submitted and wants full search.
        body = <SearchView suggestions={suggestions} suggestionsSums={suggestionsSums} loading={loading}/>;
    }
    const {setFilter} = useSearchFilter();

    const clearAllSearch = () => {
        clearDate();
        setFilter(null);
        setSearchStr(null);
        navigate('/');
    }

    const getSearchResultsInput = (props) => {
        return <SearchResultsInput clearable
                                   searchStr={localSearchStr}
                                   onChange={setLocalSearchStr}
                                   onSubmit={setSearchStr}
                                   placeholder='Search everywhere...'
                                   onClear={clearAllSearch}
                                   clearDisabled={isEmpty}
                                   style={{marginBottom: '2em'}}
                                   results={suggestionsResults}
                                   handleResultSelect={handleResultSelect}
                                   resultRenderer={resultRenderer}
                                   loading={loading}
                                   {...props}
        />;
    };

    return <PageContainer>
        <Media at='mobile'>
            <Grid>
                <Grid.Row columns={2}>
                    <Grid.Column width={12}>
                        {getSearchResultsInput()}
                    </Grid.Column>
                    <Grid.Column width={1} textAlign='right' style={{padding: 0}}>
                        <DateSelectorButton defaultMonthsSelected={months} defaultDateRange={dateRange}
                                            onClear={clearDate} onDatesChange={setDates}
                        />
                    </Grid.Column>
                    <Grid.Column width={1} textAlign='right'>
                        <FileSearchFilterButton/>
                    </Grid.Column>
                </Grid.Row>
            </Grid>
        </Media>
        <Media at='tablet'>
            <Grid>
                <Grid.Row columns={2}>
                    <Grid.Column textAlign='right' width={2}>
                        <DateSelectorButton defaultMonthsSelected={months} defaultDateRange={dateRange}
                                            onClear={clearDate} onDatesChange={setDates}
                                            buttonProps={{size: 'big'}}/>
                    </Grid.Column>
                    <Grid.Column textAlign='right' width={2}>
                        <FileSearchFilterButton size='big'/>
                    </Grid.Column>
                    <Grid.Column mobile={12}>
                        {getSearchResultsInput({size: 'big'})}
                    </Grid.Column>
                </Grid.Row>
            </Grid>
        </Media>
        <Media greaterThanOrEqual='computer'>
            <Grid>
                <Grid.Row columns={2}>
                    <Grid.Column textAlign='right' width={1}>
                        <DateSelectorButton defaultMonthsSelected={months} defaultDateRange={dateRange}
                                            onClear={clearDate} onDatesChange={setDates}
                                            buttonProps={{size: 'big'}}/>
                    </Grid.Column>
                    <Grid.Column textAlign='right' width={1}>
                        <FileSearchFilterButton size='big'/>
                    </Grid.Column>
                    <Grid.Column mobile={14}>
                        {getSearchResultsInput({size: 'big'})}
                    </Grid.Column>
                </Grid.Row>
            </Grid>
        </Media>
        {!searchStr && <FlagsMessages/>}
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
