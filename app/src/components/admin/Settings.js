import React from "react";
import {getSettings, postRestart, postShutdown, saveSettings} from "../../api";
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
    HelpPopup,
    HotspotToggle,
    semanticUIColorMap,
    ThrottleToggle,
    Toggle,
    WROLModeMessage
} from "../Common";
import QRCode from "react-qr-code";
import {useDockerized} from "../../hooks/customHooks";
import {toast} from "react-semantic-toasts-2";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {SettingsContext} from "../../contexts/contexts";

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
    5: 'All',
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
        0: 5,
    }[logLevel]
}

function toApiLogLevel(logLevel) {
    // Reverse the above levels.
    return {
        5: 0,
        4: 10,
        3: 20,
        2: 30,
        1: 40,
    }[logLevel]
}

export class SettingsPage extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            disabled: false,
            hotspot_encryption: 'WPA',
            edit_special_directories: false,
            pending: false,
            qrCodeValue: '',
            qrOpen: false,
            ready: false,

            archive_destination: null,
            download_on_startup: null,
            download_timeout: null,
            hotspot_device: null,
            hotspot_password: null,
            hotspot_ssid: null,
            hotspot_status: null,
            ignore_outdated_zims: null,
            log_level: null,
            map_destination: null,
            navColor: null,
            throttle_on_startup: null,
            throttle_status: null,
            videos_destination: null,
            zims_destination: null,
        }

        this.handleSubmit = this.handleSubmit.bind(this);
        this.handleHotspotChange = this.handleHotspotChange.bind(this);
    }

    async componentDidMount() {
        try {
            const settings = await getSettings();
            this.setState({
                ready: true,
                archive_destination: settings.archive_destination,
                disabled: settings.wrol_mode,
                download_on_startup: settings.download_on_startup,
                download_timeout: settings.download_timeout || '',
                hotspot_device: settings.hotspot_device,
                hotspot_password: settings.hotspot_password,
                hotspot_ssid: settings.hotspot_ssid,
                hotspot_status: settings.hotspot_status,
                ignore_outdated_zims: settings.ignore_outdated_zims,
                log_level: fromApiLogLevel(settings.log_level),
                map_destination: settings.map_destination,
                navColor: settings.nav_color || 'violet',
                throttle_on_startup: settings.throttle_on_startup,
                throttle_status: settings.throttle_status,
                videos_destination: settings.videos_destination,
                zims_destination: settings.zims_destination,
            }, this.handleHotspotChange);
        } catch (e) {
            console.error(e);
            this.setState({ready: undefined});
        }
    }

    async handleSubmit(callback) {
        this.setState({disabled: true, pending: true});
        let settings = {
            archive_destination: this.state.archive_destination,
            download_on_startup: this.state.download_on_startup,
            download_timeout: this.state.download_timeout ? parseInt(this.state.download_timeout) : 0,
            hotspot_device: this.state.hotspot_device,
            hotspot_password: this.state.hotspot_password,
            hotspot_ssid: this.state.hotspot_ssid,
            ignore_outdated_zims: this.state.ignore_outdated_zims,
            log_level: toApiLogLevel(this.state.log_level),
            map_destination: this.state.map_destination,
            nav_color: this.state.navColor,
            throttle_on_startup: this.state.throttle_on_startup,
            videos_destination: this.state.videos_destination,
            zims_destination: this.state.zims_destination,
        }
        try {
            const response = await saveSettings(settings);
            if (response.status !== 204) {
                throw Error('Failed to save settings');
            }
        } catch (e) {
            toast({
                type: 'error',
                title: 'Failed',
                description: 'Failed to save settings.',
                time: 5000,
            });
            throw e;
        } finally {
            this.setState({disabled: false, pending: false});
            if (callback) {
                callback();
            }
        }
    }

    handleInputChange = async (e, name, value) => {
        if (e) {
            e.preventDefault()
        }
        this.setState({[name]: value});
    }

    handleHotspotChange = async () => {
        let {hotspot_ssid, hotspot_encryption, hotspot_password} = this.state;
        // Special string which allows a mobile device to connect to a specific Wi-Fi.
        let qrCodeValue = `WIFI:S:${hotspot_ssid};T:${hotspot_encryption};P:${hotspot_password};;`;
        this.setState({qrCodeValue});
    }

    handleTimeoutChange = async (e, name, value) => {
        if (e) {
            e.preventDefault()
        }
        // Restrict timeout to numbers.
        value = value.replace(/[^\d]/, '');
        this.setState({[name]: value});
    }

    handleQrOpen = async (e) => {
        e.preventDefault();
        this.setState({qrOpen: true});
    }

    render() {
        const controlSegment = <Segment>
            <Header as='h3'>Control WROLPi</Header>
            <RestartButton/>
            <ShutdownButton/>
        </Segment>;

        if (this.state.ready === false) {
            return <>
                <Loader active inline='centered'/>
                {controlSegment}
            </>
        } else if (this.state.ready === undefined) {
            return <ErrorMessage>Unable to fetch settings</ErrorMessage>
        }

        const {
            archive_destination,
            disabled,
            download_on_startup,
            download_timeout,
            edit_special_directories,
            hotspot_device,
            hotspot_password,
            hotspot_ssid,
            ignore_outdated_zims,
            log_level,
            map_destination,
            navColor,
            pending,
            qrCodeValue,
            throttle_on_startup,
            videos_destination,
            zims_destination,
        } = this.state;

        const qrButton = <Button icon style={{marginBottom: '1em'}}><Icon name='qrcode' size='big'/></Button>;

        const navColorOptions = Object.keys(semanticUIColorMap).map(i => {
            return {key: i, value: i, text: i.charAt(0).toUpperCase() + i.slice(1)}
        });

        return <SettingsContext.Consumer>{({settings, fetchSettings}) => {
            const mediaDirectoryLabel = `${settings.media_directory}/`;
            return <Container fluid>
                <WROLModeMessage content='Settings are disabled because WROL Mode is enabled.'/>

                <Segment>
                    <HotspotToggle/>
                    <ThrottleToggle/>
                </Segment>

                <Segment>
                    <Header as='h2'>Settings</Header>
                    <p>Any changes will be written to <i>{settings.media_directory}/config/wrolpi.yaml</i>.</p>

                    <Form id="settings">
                        <div style={{margin: '0.5em'}}>
                            <Toggle
                                label='Download on Startup'
                                disabled={disabled || download_on_startup === null}
                                checked={download_on_startup === true}
                                onChange={checked => this.handleInputChange(null, 'download_on_startup', checked)}
                            />
                        </div>

                        <div style={{margin: '0.5em'}}>
                            <Toggle
                                label='CPU Power-save on Startup'
                                disabled={disabled || throttle_on_startup === null}
                                checked={throttle_on_startup === true}
                                onChange={checked => this.handleInputChange(null, 'throttle_on_startup', checked)}
                            />
                        </div>

                        <div style={{margin: '0.5em'}}>
                            <Toggle
                                label='Ignore outdated Zims'
                                disabled={disabled || ignore_outdated_zims === null}
                                checked={ignore_outdated_zims === true}
                                onChange={checked => this.handleInputChange(null, 'ignore_outdated_zims', checked)}
                            />
                        </div>

                        <FormGroup inline>
                            <FormInput
                                label={<>
                                    <b>Download Timeout</b>
                                    <HelpPopup content='Downloads will be stopped after this many seconds have elapsed.
                                Downloads will never timeout if this is empty.'/>
                                </>}
                                value={download_timeout}
                                disabled={disabled || download_timeout === null}
                                onChange={(e, d) => this.handleTimeoutChange(e, 'download_timeout', d.value)}
                            />
                        </FormGroup>

                        <FormGroup inline>
                            <FormInput
                                label='Hotspot SSID'
                                value={hotspot_ssid}
                                disabled={disabled || hotspot_ssid === null}
                                onChange={(e, d) => this.setState({hotspot_ssid: d.value}, this.handleHotspotChange)}
                            />
                            <FormInput
                                label='Hotspot Password'
                                disabled={disabled || hotspot_password === null}
                                value={hotspot_password}
                                onChange={(e, d) => this.setState({hotspot_password: d.value}, this.handleHotspotChange)}
                            />
                            <FormInput
                                label='Hotspot Device'
                                disabled={disabled || hotspot_password === null}
                                value={hotspot_device}
                                onChange={(e, d) => this.handleInputChange(e, 'hotspot_device', d.value)}
                            />
                        </FormGroup>

                        <Modal closeIcon
                               onClose={() => this.setState({qrOpen: false})}
                               onOpen={this.handleQrOpen}
                               open={this.state.qrOpen}
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

                        <label htmlFor='log_levels_input'>Log Level: {logLevelToName(log_level)}</label>
                        <br/>
                        <input type='range'
                               id='log_levels_input'
                               list='log_levels'
                               min='1'
                               max='5'
                               value={log_level}
                               onChange={e => this.setState({'log_level': parseInt(e.target.value)})}
                               style={{marginBottom: '1em'}}
                        />
                        <datalist id='log_levels'>
                            <option value='1'>Critical</option>
                            <option value='2'>Warning</option>
                            <option value='3'>Info</option>
                            <option value='4'>Debug</option>
                            <option value='5'>All</option>
                        </datalist>

                        <br/>

                        <ButtonGroup>
                            <Button color={navColor} onClick={e => e.preventDefault()}>Navbar Color</Button>
                            <Dropdown
                                className='button icon'
                                floating
                                options={navColorOptions}
                                onChange={(e, {value}) => this.setState({navColor: value})}
                                value={navColor}
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
                                            value={archive_destination}
                                            disabled={!edit_special_directories}
                                            onChange={(e, d) => this.handleInputChange(e, 'archive_destination', d.value)}
                                        />
                                    </FormField>
                                </GridColumn>
                                <GridColumn>
                                    <FormField>
                                        <label>Videos Directory</label>
                                        <Input
                                            label={mediaDirectoryLabel}
                                            value={videos_destination}
                                            disabled={!edit_special_directories}
                                            onChange={(e, d) => this.handleInputChange(e, 'videos_destination', d.value)}
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
                                            value={map_destination}
                                            disabled={!edit_special_directories}
                                            onChange={(e, d) => this.handleInputChange(e, 'map_destination', d.value)}
                                        />
                                    </FormField>
                                </GridColumn>
                                <GridColumn>
                                    <FormField>
                                        <label>Zims Directory</label>
                                        <Input
                                            label={mediaDirectoryLabel}
                                            value={zims_destination}
                                            disabled={!edit_special_directories}
                                            onChange={(e, d) => this.handleInputChange(e, 'zims_destination', d.value)}
                                        />
                                    </FormField>
                                </GridColumn>
                            </GridRow>
                            <GridRow columns={1}>
                                <GridColumn>
                                    <Toggle
                                        label='Edit Directories'
                                        disabled={disabled}
                                        checked={edit_special_directories === true}
                                        onChange={checked => this.handleInputChange(null, 'edit_special_directories', checked)}
                                    />
                                </GridColumn>
                            </GridRow>
                        </Grid>

                        <Divider/>

                        <APIButton
                            color='violet'
                            size='big'
                            onClick={() => this.handleSubmit(fetchSettings)}
                            obeyWROLMode={true}
                            disabled={disabled}
                        >Save</APIButton>

                        <Dimmer active={pending}>
                            <Loader active={pending} size='large'/>
                        </Dimmer>

                    </Form>
                </Segment>

                {controlSegment}
            </Container>;
        }
        }</SettingsContext.Consumer>
    }
}
