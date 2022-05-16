import React from 'react';
import {
    Button,
    Checkbox,
    Confirm,
    Container,
    Divider,
    Form,
    Header,
    Icon,
    Loader,
    Modal,
    Placeholder,
    Table
} from "semantic-ui-react";
import {
    clearCompletedDownloads,
    clearFailedDownloads,
    getDownloads,
    getSettings,
    killDownload,
    postDownload,
    saveSettings
} from "../api";
import TimezoneSelect from 'react-timezone-select';
import {
    DisableDownloadsToggle,
    HotspotToggle,
    PageContainer,
    secondsToDate,
    secondsToFrequency,
    TabLinks,
    textEllipsis,
    ThrottleToggle,
    WROLModeMessage
} from "./Common";
import {Route} from "react-router-dom";
import QRCode from "react-qr-code";

class Settings extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            disabled: false,
            hotspot_encryption: 'WPA',
            qrCodeValue: '',
            qrOpen: false,
            ready: false,

            download_on_startup: null,
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
        let settings = {
            download_on_startup: this.state.download_on_startup,
            hotspot_on_startup: this.state.hotspot_on_startup,
            hotspot_password: this.state.hotspot_password,
            hotspot_ssid: this.state.hotspot_ssid,
            throttle_on_startup: this.state.throttle_on_startup,
            timezone: this.state.timezone.value,
        }
        await saveSettings(settings);
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

    render() {
        if (this.state.ready === false) {
            return <Loader active inline='centered'/>
        }

        let {
            disabled,
            download_on_startup,
            hotspot_on_startup,
            hotspot_password,
            hotspot_ssid,
            qrCodeValue,
            throttle_on_startup,
            timezone,
        } = this.state;

        return (
            <Container fluid>
                <WROLModeMessage content='Settings are disabled because WROL Mode is enabled.'/>

                <HotspotToggle/>
                <br/>
                <ThrottleToggle style={{marginTop: '0.5em'}}/>
                <Divider/>

                <Header as='h3'>
                    The settings for your WROLPi.
                </Header>
                <p className="text-muted">
                    Any changes will be written to <i>config/wrolpi.yaml</i>.
                </p>

                <Form id="settings" onSubmit={this.handleSubmit}>
                    <Checkbox toggle
                              style={{marginTop: '0.5em', marginBottom: '0.5em'}}
                              label='Download on Startup'
                              disabled={disabled || download_on_startup === null}
                              checked={download_on_startup === true}
                              onChange={(e, d) => this.handleInputChange(e, 'download_on_startup', d.checked)}
                    />

                    <br/>
                    <Checkbox toggle
                              style={{marginTop: '0.5em', marginBottom: '0.5em'}}
                              label='WiFi Hotspot on Startup'
                              disabled={disabled || hotspot_on_startup === null}
                              checked={hotspot_on_startup === true}
                              onChange={(e, d) => this.handleInputChange(e, 'hotspot_on_startup', d.checked)}
                    />

                    <br/>

                    <Checkbox toggle
                              style={{marginTop: '0.5em', marginBottom: '0.5em'}}
                              label='CPU Power-save on Startup'
                              disabled={disabled || throttle_on_startup === null}
                              checked={throttle_on_startup === true}
                              onChange={(e, d) => this.handleInputChange(e, 'throttle_on_startup', d.checked)}
                    />

                    <Form.Group inline>
                        <Form.Input
                            label='Hotspot SSID'
                            value={hotspot_ssid}
                            disabled={disabled || hotspot_ssid === null}
                            onChange={(e, d) =>
                                this.setState({hotspot_ssid: d.value}, this.handleHotspotChange)}
                        />
                        <Form.Input
                            label='Hotspot Password'
                            disabled={disabled || hotspot_password === null}
                            value={hotspot_password}
                            onChange={(e, d) =>
                                this.setState({hotspot_password: d.value}, this.handleHotspotChange)}
                        />
                        <Modal closeIcon
                               onClose={() => this.setState({qrOpen: false})}
                               onOpen={() => this.setState({qrOpen: true})}
                               open={this.state.qrOpen}
                               trigger={<Button icon><Icon name='qrcode' size='big'/></Button>}
                        >
                            <Modal.Header>
                                Scan this code to join the hotspot
                            </Modal.Header>
                            <Modal.Content>
                                <QRCode value={qrCodeValue} size={300}/>
                            </Modal.Content>
                        </Modal>
                    </Form.Group>

                    <Form.Field>
                        <label>Timezone</label>
                        <TimezoneSelect
                            value={timezone}
                            onChange={(v) => this.handleInputChange(null, 'timezone', v)}
                        />
                    </Form.Field>

                    <Button color="blue" type="submit" disabled={disabled}>
                        Save
                    </Button>

                </Form>
            </Container>
        )
    }
}

class WROLMode extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            WROLMode: false,
        }
    }

    async componentDidMount() {
        try {
            let settings = await getSettings();
            this.setState({ready: true, WROLMode: settings.wrol_mode});
        } catch (e) {
            console.error(e);
        }
    }

    toggleWROLMode = async () => {
        // Handle WROL Mode toggling by itself so that other settings are not modified.
        let config = {
            wrol_mode: !this.state.WROLMode,
        }
        await saveSettings(config);
        this.setState({disabled: !this.state.WROLMode, WROLMode: !this.state.WROLMode});
    }

    render() {
        if (this.state.ready === false) {
            return <Loader active inline='centered'/>
        }

        return (
            <Container fluid>

                <Header as="h1">WROL Mode</Header>
                <h4>
                    Enable read-only mode. No content can be deleted or modified. Enable this when the SHTF and you
                    want to prevent any potential loss of data.
                </h4>
                <p>
                    Note: User settings and favorites can still be modified.
                </p>
                <Checkbox toggle
                          checked={this.state.WROLMode}
                          onChange={this.toggleWROLMode}
                          label={this.state.WROLMode ? 'WROL Mode Enabled' : 'WROL Mode Disabled'}
                />

            </Container>
        )
    }
}

function ClearCompleteDownloads({callback}) {
    const [disabled, setDisabled] = React.useState(false);

    async function localClearDownloads() {
        setDisabled(true);
        try {
            await clearCompletedDownloads();
        } finally {
            setDisabled(false);
            if (callback) {
                callback()
            }
        }
    }

    return <>
        <Button
            onClick={localClearDownloads}
            disabled={disabled}
            color='yellow'
        >Clear Completed</Button>
    </>
}

function ClearFailedDownloads({callback}) {
    const [open, setOpen] = React.useState(false);
    const [disabled, setDisabled] = React.useState(false);

    async function localDeleteFailed() {
        setDisabled(true);
        try {
            await clearFailedDownloads();
        } finally {
            setDisabled(false);
            setOpen(false);
            if (callback) {
                callback()
            }
        }
    }

    return <>
        <Button
            onClick={() => setOpen(true)}
            disabled={disabled}
            color='red'
        >Clear Failed</Button>
        <Confirm
            open={open}
            content='Are you sure you want to delete failed downloads?  They will not be retried.'
            confirmButton='Delete'
            onCancel={() => setOpen(false)}
            onConfirm={localDeleteFailed}
        />
    </>
}

class DownloadRow extends React.Component {

    render() {
        let {url, frequency, last_successful_download, status, location, next_download} = this.props;
        let positive = false;
        if (status === 'pending') {
            positive = true;
        }
        return (
            <Table.Row positive={positive}>
                <Table.Cell><a href={url} target='_blank'>{textEllipsis(url, 50)}</a></Table.Cell>
                <Table.Cell>{secondsToFrequency(frequency)}</Table.Cell>
                <Table.Cell>{last_successful_download ? secondsToDate(last_successful_download) : null}</Table.Cell>
                <Table.Cell>{secondsToDate(next_download)}</Table.Cell>
                <Table.Cell>{location && <a href={location}>View</a>}</Table.Cell>
            </Table.Row>
        );
    }
}

class StoppableRow extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            stopOpen: false,
            startOpen: false,
            errorModalOpen: false,
        };
    }

    openStop = () => {
        this.setState({stopOpen: true});
    }

    closeStop = () => {
        this.setState({stopOpen: false});
    }

    openStart = () => {
        this.setState({startOpen: true});
    }

    closeStart = () => {
        this.setState({startOpen: false});
    }

    handleStop = async (e) => {
        e.preventDefault();
        await killDownload(this.props.id);
        this.closeStop();
        await this.props.fetchDownloads();
    };

    handleStart = async (e) => {
        e.preventDefault();
        let downloader = this.props.downloader || null;
        await postDownload(`${this.props.url}`, downloader);
        this.closeStart();
        await this.props.fetchDownloads();
    };

    render() {
        let {url, last_successful_download, status, location, error} = this.props;
        let {stopOpen, startOpen, errorModalOpen} = this.state;

        let completedAtCell = last_successful_download ? secondsToDate(last_successful_download) : null;
        let buttonCell = <Table.Cell/>;
        let positive = false;
        let negative = false;
        let warning = false;
        if (status === 'pending' || status === 'new') {
            positive = status === 'pending';
            buttonCell = (
                <Table.Cell>
                    <Button
                        onClick={this.openStop}
                        color='red'
                    >Stop</Button>
                    <Confirm
                        open={stopOpen}
                        content='Are you sure you want to stop this download?  It will not be retried.'
                        confirmButton='Stop'
                        onCancel={this.closeStop}
                        onConfirm={this.handleStop}
                    />
                </Table.Cell>
            );
        } else if (status === 'failed' || status === 'deferred') {
            negative = status === 'failed';
            warning = status === 'deferred';
            buttonCell = (
                <Table.Cell>
                    <Button
                        onClick={this.openStop}
                        color='red'
                    >Stop</Button>
                    <Confirm
                        open={stopOpen}
                        content='Are you sure you want to stop this download?  It will not be retried.'
                        confirmButton='Stop'
                        onCancel={this.closeStop}
                        onConfirm={this.handleStop}
                    />
                    <Button
                        onClick={this.openStart}
                        color='green'
                    >Retry</Button>
                    <Confirm
                        open={startOpen}
                        content='Are you sure you want to restart this download?'
                        confirmButton='Start'
                        onCancel={this.closeStart}
                        onConfirm={this.handleStart}
                    />
                </Table.Cell>
            );
        } else if (status === 'complete' && location) {
            buttonCell = (
                <Table.Cell>
                    <a href={location}>View</a>
                </Table.Cell>
            );
        }
        if (error) {
            completedAtCell = (
                <Modal
                    closeIcon
                    onClose={() => this.setState({errorModalOpen: false})}
                    onOpen={() => this.setState({errorModalOpen: true})}
                    open={errorModalOpen}
                    trigger={<Button icon='exclamation circle' color='red'/>}
                >
                    <Modal.Header>Download Error</Modal.Header>
                    <Modal.Content>
                        <pre>{error}</pre>
                    </Modal.Content>
                    <Modal.Actions>
                        <Button onClick={() => this.setState({errorModalOpen: false})}>Close</Button>
                    </Modal.Actions>
                </Modal>
            )
        }

        return (
            <Table.Row positive={positive} negative={negative} warning={warning}>
                <Table.Cell><a href={url} target='_blank'>{textEllipsis(url, 50)}</a></Table.Cell>
                <Table.Cell>{status}</Table.Cell>
                <Table.Cell>{completedAtCell}</Table.Cell>
                {buttonCell}
            </Table.Row>
        );
    }
}

class Downloads extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            once_downloads: null,
            recurring_downloads: null,
            pending_downloads: null,
            stopOpen: false,
            disabled: false,
        };
    }

    async componentDidMount() {
        await this.fetchDownloads();
        this.intervalId = setInterval(this.fetchDownloads, 1000 * 10);
    }

    componentWillUnmount() {
        clearInterval(this.intervalId);
    }

    closeStop = () => {
        this.setState({stopOpen: false});
    }

    openStop = () => {
        this.setState({stopOpen: true});
    }

    fetchDownloads = async () => {
        try {
            let data = await getDownloads();
            this.setState({
                once_downloads: data.once_downloads,
                recurring_downloads: data.recurring_downloads,
                pending_downloads: data.pending_downloads,
            });
        } catch (e) {
            console.error(e);
        }
    }

    render() {
        let tablePlaceholder = (
            <Placeholder>
                <Placeholder.Line/>
                <Placeholder.Line/>
            </Placeholder>
        );

        let stoppableHeader = (
            <Table.Header>
                <Table.Row>
                    <Table.HeaderCell>URL</Table.HeaderCell>
                    <Table.HeaderCell>Status</Table.HeaderCell>
                    <Table.HeaderCell>Completed At</Table.HeaderCell>
                    <Table.HeaderCell>Control</Table.HeaderCell>
                </Table.Row>
            </Table.Header>
        );

        let nonStoppableHeader = (
            <Table.Header>
                <Table.Row>
                    <Table.HeaderCell>URL</Table.HeaderCell>
                    <Table.HeaderCell>Download Frequency</Table.HeaderCell>
                    <Table.HeaderCell>Last Successful Download</Table.HeaderCell>
                    <Table.HeaderCell>Next Download</Table.HeaderCell>
                    <Table.HeaderCell>View</Table.HeaderCell>
                </Table.Row>
            </Table.Header>
        );

        let onceTable = tablePlaceholder;
        if (this.state.once_downloads !== null && this.state.once_downloads.length === 0) {
            onceTable = <p>No downloads are scheduled.</p>
        } else if (this.state.once_downloads !== null) {
            onceTable = (
                <>
                    <ClearCompleteDownloads callback={() => this.fetchDownloads()}/>
                    <ClearFailedDownloads callback={() => this.fetchDownloads()}/>
                    <Table>
                        {stoppableHeader}
                        <Table.Body>
                            {this.state.once_downloads.map((i) =>
                                <StoppableRow {...i} fetchDownloads={this.fetchDownloads} key={i.id}/>
                            )}
                        </Table.Body>
                    </Table>
                </>);
        }

        let recurringTable = tablePlaceholder;
        if (this.state.recurring_downloads !== null && this.state.recurring_downloads.length === 0) {
            recurringTable = <p>No recurring downloads are scheduled.</p>
        } else if (this.state.recurring_downloads !== null) {
            recurringTable = (<Table>
                {nonStoppableHeader}
                <Table.Body>
                    {this.state.recurring_downloads.map((i) => <DownloadRow {...i} key={i.id}/>)}
                </Table.Body>
            </Table>);
        }

        return (
            <div>
                <WROLModeMessage content='Downloads are disabled because WROL Mode is enabled.'/>
                <DisableDownloadsToggle/>
                <Header as='h1'>Downloads</Header>
                {onceTable}

                <Header as='h1'>Recurring Downloads</Header>
                {recurringTable}
            </div>
        );
    }
}

export default function Admin(props) {

    const links = [
        {text: 'Downloads', to: '/admin', exact: true, key: 'admin'},
        {text: 'Settings', to: '/admin/settings', key: 'settings'},
        {text: 'WROL Mode', to: '/admin/wrol', key: 'wrol'},
    ];

    return (
        <PageContainer>
            <TabLinks links={links}/>
            <Route path='/admin' exact component={Downloads}/>
            <Route path='/admin/settings' exact component={Settings}/>
            <Route path='/admin/wrol' exact component={WROLMode}/>
        </PageContainer>
    )

}
