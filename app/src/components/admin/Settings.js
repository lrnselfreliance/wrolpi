import React from "react";
import {SettingsContext, StatusContext} from "../../contexts/contexts";
import {checkUpgrade, postRestart, postShutdown, saveSettings as saveSettingsApi, triggerUpgrade} from "../../api";
import {getServices, stopService, startService} from "../../api/controller";
import {
    Button,
    Divider,
    Form,
    Header,
    Loader,
    Modal,
    Segment
} from "../Theme";
import {ButtonGroup, Container, Dimmer, Dropdown, GridColumn, GridRow, Icon, Input} from "semantic-ui-react";
import {
    APIButton,
    ErrorMessage,
    InfoPopup,
    RefreshHeader,
    Toggle,
    useMessageDismissal,
    WROLModeMessage
} from "../Common";
import QRCode from "react-qr-code";
import {useConfigs, useDockerized} from "../../hooks/customHooks";
import {toast} from "react-semantic-toasts-2";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {ConfigsTable} from "./Configs";
import {semanticUIColorMap} from "../Vars";

export function ShutdownButton() {
    const dockerized = useDockerized();

    const handleShutdown = async () => {
        try {
            const response = await postShutdown();
            if (response && response['code'] === 'SHUTDOWN_FAILED') {
                toast({
                    title: 'Shutdown Failed',
                    description: response['error'],
                    time: 5000,
                    type: "error",
                })
            } else if (response && response['code'] === 'NATIVE_ONLY') {
                toast({
                    title: 'Shutdown Failed',
                    description: 'Cannot shutdown while running in Docker',
                    time: 5000,
                    type: "error",
                })
            } else if (response !== null) {
                toast({
                    title: 'Shutdown Failed',
                    description: 'Unknown error when attempting shutdown',
                    time: 5000,
                    type: "error",
                })
            }
        } catch (e) {
            toast({
                title: 'Shutdown Failed',
                description: 'Failed to request WROLPi shutdown',
                time: 5000,
                type: "error",
            })
            throw e;
        }
    }

    return <APIButton
        size='huge'
        color='red'
        onClick={handleShutdown}
        confirmContent='Are you sure you want to turn off your WROLPi?'
        confirmButton='Shutdown'
        disabled={dockerized}
    >
        Shutdown
    </APIButton>
}

function UpgradeSegment() {
    const {status, fetchStatus} = React.useContext(StatusContext);
    const dockerized = useDockerized();
    const [upgrading, setUpgrading] = React.useState(false);
    const [checking, setChecking] = React.useState(false);

    const handleCheckUpgrade = async () => {
        setChecking(true);
        try {
            await checkUpgrade(true);  // Force a fresh check
            toast({
                type: 'info',
                title: 'Update Check Complete',
                description: 'Checked for updates from git remote.',
                time: 3000,
            });
        } finally {
            setChecking(false);
            await fetchStatus();
        }
    };

    const handleUpgrade = async () => {
        setUpgrading(true);
        try {
            const response = await triggerUpgrade();
            if (response.ok) {
                // Redirect to Controller UI for upgrade status
                window.location.href = '/controller/?upgrade=true';
            }
        } catch (e) {
            setUpgrading(false);
        }
    };

    // Not available in Docker
    if (dockerized) {
        return <Segment id='upgrade'>
            <Header as='h3'>System Upgrade</Header>
            <p>Upgrades are not available in Docker environments. Please upgrade your Docker images manually.</p>
        </Segment>;
    }

    // No update available
    if (!status?.update_available) {
        return <Segment id='upgrade'>
            <Header as='h3'>System Upgrade</Header>
            <p>Your WROLPi is up to date.</p>
            <p>Version: <strong>v{status?.version}</strong> on branch <strong>{status?.git_branch || 'unknown'}</strong>
            </p>
            <APIButton
                color='blue'
                onClick={handleCheckUpgrade}
                disabled={checking}
            >
                {checking ? 'Checking...' : 'Check for Upgrades'}
            </APIButton>
        </Segment>;
    }

    // Update available
    return <Segment id='upgrade'>
        <Header as='h3'>
            <Icon name='arrow alternate circle up'/>
            Upgrade Available
        </Header>
        <p>Branch: <strong>{status?.git_branch}</strong></p>
        <p>Current commit: <strong>{status?.current_commit}</strong></p>
        <p>Latest commit: <strong>{status?.latest_commit}</strong></p>
        <p><strong>{status?.commits_behind}</strong> commit(s) behind</p>

        <APIButton
            color='green'
            size='big'
            onClick={handleUpgrade}
            disabled={upgrading}
            confirmContent='This will upgrade WROLPi. The system will be temporarily unavailable during the upgrade. Are you sure?'
            confirmButton='Start Upgrade'
        >
            {upgrading ? 'Starting Upgrade...' : 'Upgrade Now'}
        </APIButton>
    </Segment>;
}

export function RestartButton() {
    const dockerized = useDockerized();

    const handleRestart = async () => {
        try {
            const response = await postRestart();
            if (response && response['code'] === 'SHUTDOWN_FAILED') {
                toast({
                    title: 'Restart Failed',
                    description: response['error'],
                    time: 5000,
                    type: "error",
                })
            } else if (response && response['code'] === 'NATIVE_ONLY') {
                toast({
                    title: 'Restart Failed',
                    description: 'Cannot restart while running in Docker',
                    time: 5000,
                    type: "error",
                })
            } else if (response !== null) {
                toast({
                    title: 'Restart Failed',
                    description: 'Unknown error when attempting restart',
                    time: 5000,
                    type: "error",
                })
            }
        } catch (e) {
            toast({
                title: 'Restart Failed',
                description: 'Failed to request WROLPi restart',
                time: 5000,
                type: "error",
            })
            throw e;
        }
    }

    return <APIButton
        size='huge'
        color='yellow'
        onClick={handleRestart}
        confirmContent='Are you sure you want to reboot your WROLPi?'
        confirmButton='Restart'
        disabled={dockerized}
    >
        Restart
    </APIButton>
}

const levelNameMap = {
    5: 'Trace',
    4: 'Debug',
    3: 'Info',
    2: 'Warning',
    1: 'Critical'
}

function logLevelToName(logLevel) {
    // Convert app log level to name.
    return levelNameMap[logLevel]
}

function fromApiLogLevel(logLevel) {
    // Python API uses levels on the left.  App uses levels on the right to display <input> direction correctly.
    return {
        40: 1,
        30: 2,
        20: 3,
        10: 4,
        5: 5,
    }[logLevel]
}

function toApiLogLevel(logLevel) {
    // Reverse the above levels.
    return {
        5: 5,
        4: 10,
        3: 20,
        2: 30,
        1: 40,
    }[logLevel]
}

function WROLModeSection() {
    const {settings, fetchSettings} = React.useContext(SettingsContext);
    const wrolMode = settings?.wrol_mode || false;

    const toggleWROLMode = async (checked) => {
        try {
            await saveSettingsApi({wrol_mode: checked});
            await fetchSettings();  // Refresh context immediately
        } catch (e) {
            toast({
                type: 'error',
                title: 'Failed to toggle WROL Mode',
                description: e.message,
                time: 5000,
            });
        }
    };

    return (
        <Segment>
            <Header as='h3'>
                <Icon name='shield'/>
                WROL Mode
            </Header>
            <p>
                Enable read-only mode. No content can be deleted or modified.
                Enable this when the SHTF and you want to prevent any potential loss of data.
            </p>
            <p style={{fontSize: '0.9em', color: '#888'}}>
                Note: User settings and tags can still be modified.
            </p>
            <Toggle
                checked={wrolMode}
                onChange={toggleWROLMode}
                label={wrolMode ? 'WROL Mode Enabled' : 'WROL Mode Disabled'}
            />
        </Segment>
    );
}


export function SettingsPage() {
    const [disabled, setDisabled] = React.useState(false);
    const [editSpecialDirectories, setEditSpecialDirectories] = React.useState(false);
    const [qrCodeValue, setQrCodeValue] = React.useState('');
    const [qrOpen, setQrOpen] = React.useState(false);
    const [ready, setReady] = React.useState(false);
    const [pendingSave, setPendingSave] = React.useState(false);
    const {clearAll} = useMessageDismissal();
    const dockerized = useDockerized();

    // Trace level modal state
    const [traceModalOpen, setTraceModalOpen] = React.useState(false);
    const [traceCountdown, setTraceCountdown] = React.useState(5);
    const [traceSwitching, setTraceSwitching] = React.useState(false);
    const [isDevMode, setIsDevMode] = React.useState(false);

    // Get current settings from the API.
    const {settings, saveSettings, fetchSettings} = React.useContext(SettingsContext);
    // Used to track changes to the settings form between saves/loads.
    const [state, setState] = React.useState({});

    const {configs, loading, importConfig, saveConfig, fetchConfigs} = useConfigs();

    React.useEffect(() => {
        fetchConfigs();
    }, []);

    // Check if we're running in dev mode (wrolpi-api-dev service)
    React.useEffect(() => {
        if (!dockerized) {
            const checkDevMode = async () => {
                try {
                    const services = await getServices();
                    const apiDevService = services.find(s => s.name === 'wrolpi-api-dev');
                    setIsDevMode(apiDevService?.status === 'running');
                } catch (e) {
                    console.error('Failed to check dev mode status:', e);
                }
            };
            checkDevMode();
        }
    }, [dockerized]);

    const localFetchSettings = async () => {
        console.debug('fetching settings...');
        try {
            await fetchSettings();
            console.debug('successfully fetched settings');
        } catch (e) {
            console.error('failed to fetch settings!');
            throw e;
        }
    }

    const localSaveSettings = async (newSettings) => {
        // Check if trace level is selected (5 = trace in frontend)
        const isTraceLevel = newSettings.log_level === 5;

        // In native mode, if trace is selected and not already in dev mode, show confirmation modal
        if (isTraceLevel && !dockerized && !isDevMode) {
            setTraceModalOpen(true);
            return;
        }

        // Otherwise, save normally
        await doSaveSettings(newSettings);
    }

    const doSaveSettings = async (newSettings) => {
        setDisabled(true);
        setPendingSave(true);
        newSettings.download_timeout = parseInt(newSettings.download_timeout);
        newSettings.log_level = toApiLogLevel(newSettings.log_level);
        try {
            await saveSettings(newSettings);
            await localFetchSettings();
        } finally {
            setDisabled(false);
            setPendingSave(false);
        }
    }

    const handleTraceModalConfirm = async () => {
        setTraceSwitching(true);
        setTraceCountdown(5);

        // Start countdown
        const countdownInterval = setInterval(() => {
            setTraceCountdown(prev => {
                if (prev <= 1) {
                    clearInterval(countdownInterval);
                    return 0;
                }
                return prev - 1;
            });
        }, 1000);

        // Wait for countdown
        await new Promise(resolve => setTimeout(resolve, 5000));

        try {
            // Save settings first
            await doSaveSettings({...state});

            // Switch to dev mode: stop wrolpi-api, start wrolpi-api-dev
            toast({
                type: 'info',
                title: 'Switching to Debug Mode',
                description: 'Stopping production API and starting debug API...',
                time: 3000,
            });

            await stopService('wrolpi-api');
            await startService('wrolpi-api-dev');

            toast({
                type: 'success',
                title: 'Debug Mode Enabled',
                description: 'API is now running in debug mode with trace logging enabled.',
                time: 5000,
            });

            setIsDevMode(true);
        } catch (e) {
            console.error('Failed to switch to dev mode:', e);
            toast({
                type: 'error',
                title: 'Service Switch Failed',
                description: `Failed to switch API services: ${e.message}. You may need to manually restart services.`,
                time: 10000,
            });
        } finally {
            setTraceSwitching(false);
            setTraceModalOpen(false);
            setTraceCountdown(5);
        }
    }

    const handleTraceModalCancel = () => {
        // Reset log level to previous value and close modal
        setState({...state, log_level: fromApiLogLevel(settings.log_level)});
        setTraceModalOpen(false);
    }

    const handleHotspotChange = async () => {
        let {hotspot_ssid, hotspot_encryption, hotspot_password} = state;
        // Special string which allows a mobile device to connect to a specific Wi-Fi.
        setQrCodeValue(`WIFI:S:${hotspot_ssid};T:${hotspot_encryption};P:${hotspot_password};;`);
    }

    React.useEffect(() => {
        console.debug('settings changed, replacing state...');
        setReady(settings ? true : undefined);
        setState({
            // Only these settings can be changed on the SettingsPage.
            archive_destination: settings.archive_destination,
            download_on_startup: settings.download_on_startup,
            download_timeout: settings.download_timeout,
            hotspot_device: settings.hotspot_device,
            hotspot_on_startup: settings.hotspot_on_startup,
            hotspot_password: settings.hotspot_password,
            hotspot_ssid: settings.hotspot_ssid,
            check_for_upgrades: settings.check_for_upgrades,
            ignore_outdated_zims: settings.ignore_outdated_zims,
            log_level: fromApiLogLevel(settings.log_level),
            map_destination: settings.map_destination,
            nav_color: settings.nav_color,
            media_directory: settings.media_directory,
            tags_directory: settings.tags_directory,
            throttle_on_startup: settings.throttle_on_startup,
            videos_destination: settings.videos_destination,
            zims_destination: settings.zims_destination,
            save_ffprobe_json: settings.save_ffprobe_json,
        });
    }, [JSON.stringify(settings)]);

    React.useEffect(() => {
        handleHotspotChange();
    }, [state.hotspot_ssid, state.hotspot_password, state.hotspot_device]);

    const handleInputChange = async (e, name, value) => {
        if (e) {
            e.preventDefault()
        }
        setState({...state, [name]: value});
    }

    const handleTimeoutChange = async (e, name, value) => {
        if (e) {
            e.preventDefault()
        }
        // Restrict timeout to numbers.
        value = value.replace(/[^\d]/, '');
        setState({...state, [name]: value});
    }

    const handleQrOpen = async (e) => {
        e.preventDefault();
        setQrOpen(true);
    }

    const qrButton = <Button icon color='violet' style={{marginBottom: '1em'}}>
        <Icon name='qrcode' size='big'/>
    </Button>;

    const navColorOptions = Object.keys(semanticUIColorMap).map(i => {
        return {key: i, value: i, text: i.charAt(0).toUpperCase() + i.slice(1)}
    });

    const mediaDirectoryLabel = `${settings.media_directory}/`;

    let body;
    if (ready === true) {
        // Settings have been fetched, display form.
        body = <>
            <p>Any changes will be written to <i>{settings.media_directory}/config/wrolpi.yaml</i>.</p>

            <Form id="settings">
                <div style={{margin: '0.5em'}}>
                    <Toggle
                        label='Download on Startup'
                        disabled={disabled || state.download_on_startup === null}
                        checked={state.download_on_startup === true}
                        onChange={checked => handleInputChange(null, 'download_on_startup', checked)}
                    />
                </div>

                <div style={{margin: '0.5em'}}>
                    <Toggle
                        label='CPU Power-save on Startup'
                        disabled={disabled || state.throttle_on_startup === null}
                        checked={state.throttle_on_startup === true}
                        onChange={checked => handleInputChange(null, 'throttle_on_startup', checked)}
                    />
                </div>

                <div style={{margin: '0.5em'}}>
                    <Toggle
                        label='Ignore outdated Zims'
                        disabled={disabled || state.ignore_outdated_zims === null}
                        checked={state.ignore_outdated_zims === true}
                        onChange={checked => handleInputChange(null, 'ignore_outdated_zims', checked)}
                    />
                </div>

                <div style={{margin: '0.5em'}}>
                    <Toggle
                        label='Check for upgrades hourly'
                        disabled={disabled || dockerized || state.check_for_upgrades === null}
                        checked={!dockerized && state.check_for_upgrades === true}
                        onChange={checked => handleInputChange(null, 'check_for_upgrades', checked)}
                    />
                </div>

                <div style={{margin: '0.5em'}}>
                    <Toggle
                        label='Tags Directory'
                        disabled={disabled || state.tags_directory === null}
                        checked={state.tags_directory === true}
                        onChange={checked => handleInputChange(null, 'tags_directory', checked)}
                        info='When enabled, WROLPi creates a "tags" directory with hardlinks to all tagged files, organized by tag name.'
                    />
                </div>

                <div style={{margin: '0.5em'}}>
                    <Toggle
                        label='Save FFprobe Cache Files'
                        disabled={disabled || state.save_ffprobe_json === null}
                        checked={state.save_ffprobe_json === true}
                        onChange={checked => handleInputChange(null, 'save_ffprobe_json', checked)}
                        info='When enabled, FFprobe results are saved as .ffprobe.json files alongside videos. This speeds up reindexing but uses additional disk space (~5KB per video).'
                    />
                </div>

                <Form.Group inline>
                    <Form.Input
                        label={<>
                            <b>Download Timeout</b>
                            <InfoPopup content='Downloads will be stopped after this many seconds have elapsed.
                                Downloads will never timeout if this is empty.'/>
                        </>}
                        value={state.download_timeout}
                        disabled={disabled || state.download_timeout === null}
                        onChange={(e, i) => handleTimeoutChange(e, 'download_timeout', i.value)}
                    />
                </Form.Group>

                <Form.Group inline>
                    <Form.Input
                        label='Hotspot SSID'
                        value={state.hotspot_ssid}
                        disabled={disabled || state.hotspot_ssid === null}
                        onChange={(e, i) => setState({...state, hotspot_ssid: i.value})}
                    />
                    <Form.Input
                        label='Hotspot Password'
                        disabled={disabled || state.hotspot_password === null}
                        value={state.hotspot_password}
                        onChange={(e, i) => setState({...state, hotspot_password: i.value})}
                    />
                    <Form.Input
                        label='Hotspot Device'
                        disabled={disabled || state.hotspot_password === null}
                        value={state.hotspot_device}
                        onChange={(e, i) => handleInputChange(e, 'hotspot_device', i.value)}
                    />
                </Form.Group>

                <Modal closeIcon
                       onClose={() => setQrOpen(false)}
                       onOpen={handleQrOpen}
                       open={qrOpen}
                       trigger={qrButton}
                >
                    <Modal.Header>
                        Scan this code to join the hotspot
                    </Modal.Header>
                    <Modal.Content>
                        <div style={{display: 'inline-block', backgroundColor: '#ffffff', padding: '1em'}}>
                            <QRCode value={qrCodeValue} size={300}/>
                        </div>
                    </Modal.Content>
                </Modal>

                <br/>

                <label htmlFor='log_levels_input'>Log Level: {logLevelToName(state.log_level)}</label>
                <br/>
                <input type='range'
                       id='log_levels_input'
                       list='log_levels'
                       min='1'
                       max='5'
                       value={state.log_level}
                       onChange={e => setState({...state, log_level: parseInt(e.target.value)})}
                       style={{marginBottom: '1em'}}
                />
                <datalist id='log_levels'>
                    <option value='1'>Critical</option>
                    <option value='2'>Warning</option>
                    <option value='3'>Info</option>
                    <option value='4'>Debug</option>
                    <option value='5'>Trace</option>
                </datalist>

                <br/>

                <ButtonGroup>
                    <Button color={state.nav_color} onClick={e => e.preventDefault()}>Navbar Color</Button>
                    <Dropdown
                        id='settings_navbar_color_dropdown'
                        className='button icon'
                        floating
                        options={navColorOptions}
                        onChange={(e, {value}) => setState({...state, nav_color: value})}
                        value={state.nav_color}
                    />
                </ButtonGroup>

                <Divider/>

                <Header as='h3'>Special Directories</Header>
                <p>WROLPi will save files to these directories (any video files will be saved to
                    the <i>videos</i> by default, etc.).</p>

                <Grid stackable>
                    <GridRow columns={2}>
                        <GridColumn>
                            <Form.Field>
                                <label>Archive Directory</label>
                                <Input
                                    label={mediaDirectoryLabel}
                                    value={state.archive_destination}
                                    disabled={!editSpecialDirectories}
                                    onChange={(e, d) => handleInputChange(e, 'archive_destination', d.value)}
                                />
                            </Form.Field>
                        </GridColumn>
                        <GridColumn>
                            <Form.Field>
                                <label>Videos Directory</label>
                                <Input
                                    label={mediaDirectoryLabel}
                                    value={state.videos_destination}
                                    disabled={!editSpecialDirectories}
                                    onChange={(e, d) => handleInputChange(e, 'videos_destination', d.value)}
                                />
                            </Form.Field>
                        </GridColumn>
                    </GridRow>
                    <GridRow columns={2}>
                        <GridColumn>
                            <Form.Field>
                                <label>Map Directory</label>
                                <Input
                                    label={mediaDirectoryLabel}
                                    value={state.map_destination}
                                    disabled={!editSpecialDirectories}
                                    onChange={(e, d) => handleInputChange(e, 'map_destination', d.value)}
                                />
                            </Form.Field>
                        </GridColumn>
                        <GridColumn>
                            <Form.Field>
                                <label>Zims Directory</label>
                                <Input
                                    label={mediaDirectoryLabel}
                                    value={state.zims_destination}
                                    disabled={!editSpecialDirectories}
                                    onChange={(e, d) => handleInputChange(e, 'zims_destination', d.value)}
                                />
                            </Form.Field>
                        </GridColumn>
                    </GridRow>
                    <GridRow columns={1}>
                        <GridColumn>
                            <Toggle
                                label='Edit Directories'
                                disabled={disabled}
                                checked={editSpecialDirectories === true}
                                onChange={checked => setEditSpecialDirectories(checked)}
                            />
                        </GridColumn>
                    </GridRow>
                </Grid>

                <Divider/>

                <APIButton
                    id='settings_save_button'
                    color='violet'
                    size='big'
                    onClick={() => localSaveSettings(state)}
                    obeyWROLMode={true}
                    disabled={disabled}
                >Save</APIButton>

                <Dimmer active={pendingSave}>
                    <Loader active={pendingSave} size='large'/>
                </Dimmer>

            </Form>
        </>
    } else if (ready === false) {
        body = <Loader active inline='centered'/>
    } else {
        body = <ErrorMessage>Unable to fetch settings</ErrorMessage>
    }

    const configsSegment = <Segment>
        <RefreshHeader
            header='Configs'
            popupContents='Check if configs are valid'
            onRefresh={fetchConfigs}
        />

        <p>These configs control this WROLPi; they are the source of truth. Any changes to configs will be applied to
            the database when imported (typically at startup).</p>

        <ConfigsTable
            configs={configs}
            loading={loading}
            importConfig={importConfig}
            saveConfig={saveConfig}
            fetchConfigs={fetchConfigs}
        />
    </Segment>;

    return <Container fluid>
        <WROLModeMessage content='Settings are disabled because WROL Mode is enabled.'/>

        <Segment>
            <Header as='h2'>Settings</Header>
            {body}
        </Segment>

        {configsSegment}

        <UpgradeSegment/>

        <WROLModeSection/>

        <Segment>
            <Header as='h1'>Browser Settings</Header>
            <APIButton onClick={clearAll}>Show All Hints</APIButton>
        </Segment>

        {/* Trace Level Modal - shown when user selects trace level in native mode */}
        <Modal
            open={traceModalOpen}
            onClose={() => !traceSwitching && handleTraceModalCancel()}
            size='small'
        >
            <Modal.Header>
                <Icon name='bug'/> Enable Debug Mode for Trace Logging
            </Modal.Header>
            <Modal.Content>
                {traceSwitching ? (
                    <>
                        <p>
                            <Icon name='spinner' loading/>
                            {traceCountdown > 0
                                ? `Switching to debug mode in ${traceCountdown} seconds...`
                                : 'Switching API services...'}
                        </p>
                        <p style={{color: '#888', fontSize: '0.9em'}}>
                            The API will restart. This page may temporarily lose connection.
                        </p>
                    </>
                ) : (
                    <>
                        <p>
                            Trace logging requires running the API in debug mode, which has slightly reduced
                            performance (2 workers instead of 5).
                        </p>
                        <p>
                            This will save your settings and restart the API service. The page may temporarily
                            lose connection during the switch.
                        </p>
                        <p style={{color: '#888', fontSize: '0.9em'}}>
                            You can switch back to production mode later from the Controller page.
                        </p>
                    </>
                )}
            </Modal.Content>
            <Modal.Actions>
                <Button
                    color='grey'
                    onClick={handleTraceModalCancel}
                    disabled={traceSwitching}
                >
                    Cancel
                </Button>
                <Button
                    color='green'
                    onClick={handleTraceModalConfirm}
                    disabled={traceSwitching}
                >
                    <Icon name='check'/> Enable Debug Mode
                </Button>
            </Modal.Actions>
        </Modal>
    </Container>;
}

