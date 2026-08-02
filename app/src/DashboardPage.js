import {
    CookiesLockedMessage,
    ErrorMessage,
    LoadStatistic,
    PageContainer,
    RefreshHeader,
    SearchResultsInput,
    useTitle
} from "./components/Common";
import React, {useContext, useState} from "react";
import {useHotkeys} from "react-hotkeys-hook";
import {Media, SettingsContext, StatusContext} from "./contexts/contexts";
import {DownloadMenu} from "./components/Download";
import {
    ActionInput,
    Button,
    Divider,
    Group,
    Header,
    Icon,
    Message,
    Modal,
    Panel,
    Stack,
    Statistic,
    StatisticGroup,
} from "./components/ui";
import {Link, useNavigate, useSearchParams} from "react-router";
import {BandwidthProgressCombined, CPUUsageProgress} from "./components/admin/Status";
import {ProgressPlaceholder} from "./components/Placeholder";
import {refreshFiles} from "./api";
import _ from "lodash";
import {TagsDashboard} from "./Tags";
import {Upload} from "./components/Upload";
import {SearchView, useSearch, useSearchSuggestions} from "./components/Search";
import {OutdatedZimsMessage} from "./components/Zim";
import {useSearchFilter, useSearchRecentFiles, useWROLMode} from "./hooks/customHooks";
import {ExtensionInstallSuggestion} from "./components/admin/ExtensionInstallSuggestion";
import {fileMimetypeFilterOptions, FileCards, SearchFilterButton} from "./components/Files";
import {useCalculators} from "./components/Calculators";
import {classifyAndEvaluate} from "./components/calculators/mathConfig";

// A spinning refresh glyph, used as the `icon` for the "files are being refreshed" Message.
const RefreshingIcon = (props) => <Icon name='circle notched' loading {...props}/>;

export function FlagsMessages() {
    const {settings, fetchSettings} = React.useContext(SettingsContext);
    const {status} = useContext(StatusContext);

    if (_.isEmpty(status?.flags)) {
        return <></>
    }

    const flags = status['flags'];

    let refreshingMessage;
    let refreshRequiredMessage;

    // Do not tell the maintainer to refresh the files if the FileWorker is busy.
    if (flags.file_worker_busy) {
        // FileWorker is busy.
        refreshingMessage = <Message kind='info' icon={RefreshingIcon} title='Your files are being refreshed.'>
            <p><Link to='/files'>Click here to view the progress</Link></p>
        </Message>;
    } else if (!flags.refresh_complete) {
        // `refresh_complete` flag is not set.  Tell the maintainer to refresh the files.
        refreshRequiredMessage = <Message kind='warning' icon='hand point right' title='Refresh required'>
            <a href='#' onClick={(e) => {
                e.preventDefault();
                refreshFiles();
            }}>Click here</a> to refresh all your files.
        </Message>;
    }

    let dbDownMessage;
    if (!flags.db_up) {
        dbDownMessage = <ErrorMessage>
            <strong>Database is down</strong>
            <p>API is unable to connect to the database. Check the server logs.</p>
        </ErrorMessage>
    }

    let internetDownMessage;
    if (!flags.have_internet && !settings.wrol_mode) {
        internetDownMessage = <ErrorMessage icon='globe'>
            <strong>No Internet</strong>
            <p>WROLPi has no Internet. Downloads will not start.</p>
        </ErrorMessage>;
    }

    let mediaUnmountedMessage;
    if (flags.media_mounted === false) {
        mediaUnmountedMessage = <ErrorMessage icon='hdd'>
            <strong>No drive mounted</strong>
            <p>
                WROLPi has no media drive mounted for one or more storage locations.
                Downloads would write to the root filesystem and can fill it.
                {' '}<Link to='/admin/controller'>Open the Controller</Link> to mount a drive.
            </p>
        </ErrorMessage>;
    }

    return <>
        {refreshingMessage}
        {dbDownMessage || refreshRequiredMessage}
        {mediaUnmountedMessage}
        {settings && settings['ignore_outdated_zims'] === false && flags.outdated_zims ?
            <OutdatedZimsMessage onClick={fetchSettings}/> : null}
        {internetDownMessage}
        <CookiesLockedMessage/>
    </>
}

function EvaluateForm() {

    const helpContents = <span>
        <p>Enter an equation or a value with units.</p>

        <h5>Math:</h5>
        <pre>2 + 3</pre>
        <pre>sqrt(15)</pre>
        <pre>8 * pi</pre>

        <h5>Unit Conversions:</h5>
        <pre>15 km to miles</pre>
        <pre>65 degF to degC</pre>
        <pre>1 gallon to liters</pre>
        <pre>5 psi to atm</pre>

        <h5>Auto-Convert (enter value + unit):</h5>
        <pre>5 miles</pre>
        <pre>100 degF</pre>
        <pre>1 gallon</pre>
        <pre>500 Wh</pre>

        <h5>Radiation:</h5>
        <pre>0.5 Sv</pre>
        <pre>1 Gy to raddose</pre>
        <pre>100 remdose to Sv</pre>

        <h5>Data:</h5>
        <pre>7 * 750 Mb</pre>
        <pre>2 Tb to Gb</pre>
    </span>

    const [showMessage, setShowMessage] = React.useState(false);
    const [inputValue, setInputValue] = React.useState('');
    const [evaluatedValue, setEvaluatedValue] = React.useState(helpContents);

    const doEvaluate = () => {
        if (!inputValue) {
            setEvaluatedValue(helpContents);
            return;
        }
        setEvaluatedValue(''); // Clear input temporarily so the user can tell something happened.
        try {
            const {primary, conversions} = classifyAndEvaluate(inputValue);
            setEvaluatedValue(<div>
                <strong>{primary}</strong>
                {conversions.length > 0 && <div style={{marginTop: '0.5em'}}>
                    <em>Also:</em>
                    {conversions.map((c, i) => <div key={i}>{c}</div>)}
                </div>}
            </div>);
        } catch (error) {
            console.error(error);
            setEvaluatedValue(`Unable to evaluate: ${error.message}`);
        }
    }

    return <form onSubmit={(e) => {
        e.preventDefault();
        doEvaluate();
    }}>
        <ActionInput
            value={inputValue}
            leftSection='𝒇'
            type='text'
            onFocus={() => setShowMessage(true)}
            onChange={(e) => setInputValue(e.currentTarget.value)}
            action={<Button type='submit' role='primary'>Evaluate</Button>}
        />
        {showMessage &&
            <Message kind='info' title='Result'>
                {evaluatedValue}
            </Message>
        }
    </form>
}

function DashboardCalculators() {
    const {calculatorLinks} = useCalculators();

    return <Panel>
        <Header as='h2'>Calculators</Header>
        <Stack>
            <EvaluateForm/>
            <div>{calculatorLinks}</div>
        </Stack>
    </Panel>
}

export function Getters() {
    const {status} = useContext(StatusContext);
    const wrolModeEnabled = useWROLMode();

    // Getters are Downloads or Uploads.
    const [selectedGetter, setSelectedGetter] = useState(null);
    const gettersDisabled = status?.flags?.refresh_complete !== true;

    // Deep-link support: the WROLPi browser extension (and anyone else) can open
    // /?downloader=<archive|video|...>&download_url=<u1>&download_url=<u2>
    // to auto-open the download modal pre-filled with a downloader and URLs.
    const [searchParams, setSearchParams] = useSearchParams();
    const initialDownloader = searchParams.get('downloader');
    const initialUrls = searchParams.getAll('download_url');

    React.useEffect(() => {
        if (initialDownloader && selectedGetter !== 'downloads') {
            setSelectedGetter('downloads');
        }
        // Run once on mount per change to query params.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [initialDownloader]);

    const handleSetGetter = (e, value) => {
        if (e) {
            e.preventDefault();
        }
        setSelectedGetter(value);
        // Closing the modal? Clear deep-link params so a refresh doesn't re-open.
        if (value === null && (initialDownloader || initialUrls.length)) {
            const next = new URLSearchParams(searchParams);
            next.delete('downloader');
            next.delete('download_url');
            setSearchParams(next, {replace: true});
        }
    }

    const getter = <Panel>
        <Group justify='center' align='stretch' gap='xl' wrap='wrap'>
            <Button role='primary' icon='download' onClick={e => handleSetGetter(e, 'downloads')}>
                Download
            </Button>
            <Divider orientation='vertical' label='Or' labelPosition='center'/>
            <Button role='save' icon='upload' onClick={e => handleSetGetter(e, 'upload')}>
                Upload
            </Button>
        </Group>
    </Panel>;

    let getterModal;
    if (selectedGetter === 'downloads') {
        getterModal = <Modal size='large' closeIcon
                             open={true}
                             centered={false}
                             onClose={() => handleSetGetter(null, null)}
        >
            <Modal.Header>Download from the Internet</Modal.Header>
            <Modal.Content>
                <DownloadMenu
                    disabled={gettersDisabled}
                    initialDownloader={initialDownloader}
                    initialUrls={initialUrls}
                />
            </Modal.Content>
        </Modal>;
    } else if (selectedGetter === 'upload') {
        getterModal = <Modal size='large' closeIcon
                             open={true}
                             centered={false}
                             onClose={() => handleSetGetter(null, null)}
        >
            <Modal.Header>Upload from your device</Modal.Header>
            <Modal.Content>
                <Upload disabled={gettersDisabled}/>
            </Modal.Content>
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


function DashboardStatus() {
    const {status} = useContext(StatusContext);

    let percent = 0;
    let load = {};
    let cores = 0;
    let pending_downloads = '?';
    if (status && status['cpu_stats']) {
        percent = status['cpu_stats']['percent'];
        load = status['load_stats'];
        cores = status['cpu_stats']['cores'];
    }

    const {downloads} = status;
    if (!_.isEmpty(downloads)) {
        pending_downloads = downloads && downloads['disabled'] ? 'x' : downloads['pending'];
    }

    let bandwidths = <ProgressPlaceholder/>;
    if (status && status['nic_bandwidth_stats']) {
        bandwidths = Object.entries(status['nic_bandwidth_stats'])
            .map(([name, bandwidth]) => <BandwidthProgressCombined key={name} bandwidth={bandwidth}/>);
    } else if (window.apiDown) { // apiDown is set in useStatus
        bandwidths = null;
    }

    return <Panel>
        <Link to='/admin/status'>
            <Header as='h2'>Status</Header>
            <CPUUsageProgress value={percent} label='CPU Usage'/>

            <StatisticGroup>
                <LoadStatistic label='1 Min. Load' value={load['minute_1']} cores={cores}/>
                <LoadStatistic label='5 Min. Load' value={load['minute_5']} cores={cores}/>
                <LoadStatistic label='15 Min. Load' value={load['minute_15']} cores={cores}/>
            </StatisticGroup>

            <Header as='h3'>Bandwidth</Header>
            {bandwidths}
        </Link>

        <Divider style={{marginTop: '3em'}}/>

        <Link to='/admin'>
            <StatisticGroup>
                <Statistic label='Downloading' value={pending_downloads}/>
            </StatisticGroup>
        </Link>

    </Panel>;
}

function DashboardRecentFiles() {
    const {searchFiles, loading, fetchFiles} = useSearchRecentFiles();

    return <Panel>
        <RefreshHeader
            header='Recently Viewed Files'
            popupContents='Fetch the most recent files again'
            onRefresh={fetchFiles}
        />
        <FileCards files={searchFiles} loading={loading}/>
    </Panel>
}

export function DashboardPage() {
    const navigate = useNavigate();
    const searchInputRef = React.useRef();

    useHotkeys('f', (e) => {
        e.preventDefault();
        if (searchInputRef.current) {
            searchInputRef.current.focus();
        }
    }, {enableOnFormTags: false});

    // The search the user submitted.
    const {searchStr, setSearchStr, activeTags, isEmpty, anyTag} = useSearch();
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
        clearDate,
    } = useSearchSuggestions(searchStr, activeTags, anyTag);

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
        <DashboardCalculators/>
        <DashboardRecentFiles/>
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
        return <SearchResultsInput clearable={!isEmpty}
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
                                   inputRef={searchInputRef}
                                   {...props}
        />;
    };

    // The search input grows to fill the row; the Filter button sits immediately after it.  Flexbox adapts
    // to the client width, so only the control size changes between mobile and larger screens.
    const searchRow = (big) => {
        const inputProps = {style: {flexGrow: 1, minWidth: 0, marginBottom: 0}};
        if (big) {
            inputProps.size = 'big';
        }
        return <div style={{display: 'flex', alignItems: 'center', gap: '0.5em', marginBottom: '2em'}}>
            {getSearchResultsInput(inputProps)}
            <SearchFilterButton fileFilterOptions={fileMimetypeFilterOptions} showDates={true} showDeep={true}
                                size={big ? 'big' : undefined}/>
        </div>;
    };

    return <PageContainer>
        <Media at='mobile'>{searchRow(false)}</Media>
        <Media greaterThanOrEqual='tablet'>{searchRow(true)}</Media>
        {!searchStr && <FlagsMessages/>}
        {!searchStr && <ExtensionInstallSuggestion/>}
        {body}
    </PageContainer>
}
