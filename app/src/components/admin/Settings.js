import React from "react";
import {postRestart, postShutdown} from "../../api";
import {
    Button,
    Divider,
    Form,
    FormField,
    FormGroup,
    FormInput,
    Header,
    Loader,
    Modal,
    ModalContent,
    ModalHeader,
    Segment
} from "../Theme";
import {ButtonGroup, Container, Dimmer, Dropdown, GridColumn, GridRow, Icon, Input} from "semantic-ui-react";
import {
    APIButton,
    ErrorMessage,
    HotspotToggle,
    InfoPopup,
    RefreshHeader,
    ThrottleToggle,
    Toggle,
    useMessageDismissal,
    WROLModeMessage
} from "../Common";
import QRCode from "react-qr-code";
import {useConfigs, useDockerized} from "../../hooks/customHooks";
import {toast} from "react-semantic-toasts-2";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {SettingsContext} from "../../contexts/contexts";
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

export function SettingsPage() {
    const [disabled, setDisabled] = React.useState(false);
    const [editSpecialDirectories, setEditSpecialDirectories] = React.useState(false);
    const [qrCodeValue, setQrCodeValue] = React.useState('');
    const [qrOpen, setQrOpen] = React.useState(false);
    const [ready, setReady] = React.useState(false);
    const [pendingSave, setPendingSave] = React.useState(false);
    const {clearAll} = useMessageDismissal();

    // Get current settings from the API.
    const {settings, saveSettings, fetchSettings} = React.useContext(SettingsContext);
    // Used to track changes to the settings form between saves/loads.
    const [state, setState] = React.useState({});

    const {configs, loading, importConfig, saveConfig, fetchConfigs} = useConfigs();

    React.useEffect(() => {
        fetchConfigs();
    }, []);

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
            ignore_outdated_zims: settings.ignore_outdated_zims,
            log_level: fromApiLogLevel(settings.log_level),
            map_destination: settings.map_destination,
            nav_color: settings.nav_color,
            media_directory: settings.media_directory,
            throttle_on_startup: settings.throttle_on_startup,
            videos_destination: settings.videos_destination,
            zims_destination: settings.zims_destination,
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

                <FormGroup inline>
                    <FormInput
                        label={<>
                            <b>Download Timeout</b>
                            <InfoPopup content='Downloads will be stopped after this many seconds have elapsed.
                                Downloads will never timeout if this is empty.'/>
                        </>}
                        value={state.download_timeout}
                        disabled={disabled || state.download_timeout === null}
                        onChange={(e, i) => handleTimeoutChange(e, 'download_timeout', i.value)}
                    />
                </FormGroup>

                <FormGroup inline>
                    <FormInput
                        label='Hotspot SSID'
                        value={state.hotspot_ssid}
                        disabled={disabled || state.hotspot_ssid === null}
                        onChange={(e, i) => setState({...state, hotspot_ssid: i.value})}
                    />
                    <FormInput
                        label='Hotspot Password'
                        disabled={disabled || state.hotspot_password === null}
                        value={state.hotspot_password}
                        onChange={(e, i) => setState({...state, hotspot_password: i.value})}
                    />
                    <FormInput
                        label='Hotspot Device'
                        disabled={disabled || state.hotspot_password === null}
                        value={state.hotspot_device}
                        onChange={(e, i) => handleInputChange(e, 'hotspot_device', i.value)}
                    />
                </FormGroup>

                <Modal closeIcon
                       onClose={() => setQrOpen(false)}
                       onOpen={handleQrOpen}
                       open={qrOpen}
                       trigger={qrButton}
                >
                    <ModalHeader>
                        Scan this code to join the hotspot
                    </ModalHeader>
                    <ModalContent>
                        <div style={{display: 'inline-block', backgroundColor: '#ffffff', padding: '1em'}}>
                            <QRCode value={qrCodeValue} size={300}/>
                        </div>
                    </ModalContent>
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
                            <FormField>
                                <label>Archive Directory</label>
                                <Input
                                    label={mediaDirectoryLabel}
                                    value={state.archive_destination}
                                    disabled={!editSpecialDirectories}
                                    onChange={(e, d) => handleInputChange(e, 'archive_destination', d.value)}
                                />
                            </FormField>
                        </GridColumn>
                        <GridColumn>
                            <FormField>
                                <label>Videos Directory</label>
                                <Input
                                    label={mediaDirectoryLabel}
                                    value={state.videos_destination}
                                    disabled={!editSpecialDirectories}
                                    onChange={(e, d) => handleInputChange(e, 'videos_destination', d.value)}
                                />
                            </FormField>
                        </GridColumn>
                    </GridRow>
                    <GridRow columns={2}>
                        <GridColumn>
                            <FormField>
                                <label>Map Directory</label>
                                <Input
                                    label={mediaDirectoryLabel}
                                    value={state.map_destination}
                                    disabled={!editSpecialDirectories}
                                    onChange={(e, d) => handleInputChange(e, 'map_destination', d.value)}
                                />
                            </FormField>
                        </GridColumn>
                        <GridColumn>
                            <FormField>
                                <label>Zims Directory</label>
                                <Input
                                    label={mediaDirectoryLabel}
                                    value={state.zims_destination}
                                    disabled={!editSpecialDirectories}
                                    onChange={(e, d) => handleInputChange(e, 'zims_destination', d.value)}
                                />
                            </FormField>
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

    const controlSegment = <Segment>
        <Header as='h3'>Control WROLPi</Header>
        <HotspotToggle/>
        <ThrottleToggle/>

        <RestartButton/>
        <ShutdownButton/>
    </Segment>;

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

        {controlSegment}

        <Segment>
            <Header as='h2'>Settings</Header>
            {body}
        </Segment>

        {configsSegment}

        <Segment>
            <Header as='h1'>Browser Settings</Header>
            <APIButton onClick={clearAll}>Show All Hints</APIButton>
        </Segment>
    </Container>;
}

