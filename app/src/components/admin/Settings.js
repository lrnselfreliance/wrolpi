import React from "react";
import {getSettings, saveSettings} from "../../api";
import {Button, Form, FormField, FormGroup, FormInput, Header, Loader} from "../Theme";
import {Container, Dimmer, Divider, Icon, Modal} from "semantic-ui-react";
import {ThemeContext} from "../../contexts/contexts";
import {HelpPopup, HotspotToggle, ThrottleToggle, Toggle, WROLModeMessage} from "../Common";
import QRCode from "react-qr-code";
import TimezoneSelect from "react-timezone-select";

export class Settings extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            disabled: false,
            hotspot_encryption: 'WPA',
            pending: false,
            qrCodeValue: '',
            qrOpen: false,
            ready: false,

            download_on_startup: null,
            download_timeout: null,
            hotspot_device: null,
            hotspot_on_startup: null,
            hotspot_password: null,
            hotspot_ssid: null,
            hotspot_status: null,
            throttle_on_startup: null,
            throttle_status: null,
            timezone: {timezone: null},
        }

        this.handleSubmit = this.handleSubmit.bind(this);
        this.handleHotspotChange = this.handleHotspotChange.bind(this);
    }

    async componentDidMount() {
        try {
            const settings = await getSettings();
            this.setState({
                ready: true,
                disabled: settings.wrol_mode,
                download_on_startup: settings.download_on_startup,
                download_timeout: settings.download_timeout || '',
                hotspot_device: settings.hotspot_device,
                hotspot_on_startup: settings.hotspot_on_startup,
                hotspot_password: settings.hotspot_password,
                hotspot_ssid: settings.hotspot_ssid,
                hotspot_status: settings.hotspot_status,
                throttle_on_startup: settings.throttle_on_startup,
                throttle_status: settings.throttle_status,
                timezone: {value: settings.timezone, label: settings.timezone},
            }, this.handleHotspotChange);
        } catch (e) {
            console.error(e);
        }
    }

    async handleSubmit(e) {
        e.preventDefault();
        this.setState({disabled: true, pending: true});
        let settings = {
            download_on_startup: this.state.download_on_startup,
            download_timeout: this.state.download_timeout ? parseInt(this.state.download_timeout) : 0,
            hotspot_device: this.state.hotspot_device,
            hotspot_on_startup: this.state.hotspot_on_startup,
            hotspot_password: this.state.hotspot_password,
            hotspot_ssid: this.state.hotspot_ssid,
            throttle_on_startup: this.state.throttle_on_startup,
            timezone: this.state.timezone.value,
        }
        await saveSettings(settings);
        this.setState({disabled: false, pending: false});
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
        if (this.state.ready === false) {
            return <Loader active inline='centered'/>
        }

        let {
            disabled,
            download_on_startup,
            download_timeout,
            hotspot_device,
            hotspot_on_startup,
            hotspot_password,
            hotspot_ssid,
            pending,
            qrCodeValue,
            throttle_on_startup,
            timezone,
        } = this.state;

        const qrButton = <Button icon style={{marginBottom: '1em'}}><Icon name='qrcode' size='big'/></Button>;

        return <ThemeContext.Consumer>
            {({i, t}) => <Container fluid>
                <WROLModeMessage content='Settings are disabled because WROL Mode is enabled.'/>

                <HotspotToggle/>
                <ThrottleToggle/>
                <Divider/>

                <Header as='h3'>
                    The settings for your WROLPi.
                </Header>
                <p {...t}>
                    Any changes will be written to <i>config/wrolpi.yaml</i>.
                </p>

                <Form id="settings" onSubmit={this.handleSubmit}>
                    <div style={{margin: '0.5em'}}>
                        <Toggle
                            label='Download on Startup'
                            disabled={disabled || download_on_startup === null}
                            checked={download_on_startup === true}
                            onChange={(checked) => this.handleInputChange(null, 'download_on_startup', checked)}
                        />
                    </div>

                    <div style={{margin: '0.5em'}}>
                        <Toggle
                            label='WiFi Hotspot on Startup'
                            disabled={disabled || hotspot_on_startup === null}
                            checked={hotspot_on_startup === true}
                            onChange={(checked) => this.handleInputChange(null, 'hotspot_on_startup', checked)}
                        />
                    </div>

                    <div style={{margin: '0.5em'}}>
                        <Toggle
                            label='CPU Power-save on Startup'
                            disabled={disabled || throttle_on_startup === null}
                            checked={throttle_on_startup === true}
                            onChange={(checked) => this.handleInputChange(null, 'throttle_on_startup', checked)}
                        />
                    </div>

                    <FormGroup inline>
                        <FormInput
                            label={<>
                                <b {...t}>Download Timeout</b>
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
                            onChange={(e, d) =>
                                this.setState({hotspot_ssid: d.value}, this.handleHotspotChange)}
                        />
                        <FormInput
                            label='Hotspot Password'
                            disabled={disabled || hotspot_password === null}
                            value={hotspot_password}
                            onChange={(e, d) =>
                                this.setState({hotspot_password: d.value}, this.handleHotspotChange)}
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
                        <Modal.Header>
                            Scan this code to join the hotspot
                        </Modal.Header>
                        <Modal.Content>
                            <QRCode value={qrCodeValue} size={300}/>
                        </Modal.Content>
                    </Modal>

                    <FormField>
                        <label>Timezone</label>
                        <TimezoneSelect
                            value={timezone}
                            onChange={i => this.handleInputChange(null, 'timezone', i)}
                        />
                    </FormField>

                    <Button color="blue" type="submit" disabled={disabled}>
                        Save
                    </Button>

                    <Dimmer active={pending}>
                        <Loader active={pending} size='large'/>
                    </Dimmer>

                </Form>
            </Container>
            }
        </ThemeContext.Consumer>
    }
}
