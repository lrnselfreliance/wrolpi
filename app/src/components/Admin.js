import React from 'react';
import {
    Button,
    Checkbox,
    Confirm,
    Container,
    Divider,
    Form,
    Header,
    Loader,
    Placeholder,
    Tab,
    Table
} from "semantic-ui-react";
import {
    getConfig,
    getDownloaders,
    getDownloads,
    killDownload,
    killDownloads,
    postDownload,
    saveConfig,
    startDownloads
} from "../api";
import TimezoneSelect from 'react-timezone-select';
import {secondsToDate, secondsToFrequency} from "./Common";

class Settings extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            disabled: false,
            ready: false,
            validTimezone: true,
            timezone: '',
        }
        this.mediaDirectory = React.createRef();

        this.handleSubmit = this.handleSubmit.bind(this);
    }

    async componentDidMount() {
        let config = await getConfig();
        this.setState({
            ready: true,
            disabled: config.wrol_mode,
            timezone: config.timezone || '',
        });
        this.mediaDirectory.current.value = config.media_directory;
    }

    async handleSubmit(e) {
        e.preventDefault();
        let config = {
            media_directory: this.mediaDirectory.current.value,
            timezone: this.state.timezone.value,
        };
        this.setState({validTimezone: true});
        let response = await saveConfig(config);
        if (response.status !== 200) {
            let json = await response.json();
            if (json.api_error === 'Invalid timezone') {
                this.setState({validTimezone: false});
            }
        }
    }

    handleTimezoneChange = async (timezone) => {
        this.setState({timezone});
    }

    render() {
        if (this.state.ready === false) {
            return <Loader active inline='centered'/>
        }

        return (
            <Container fluid>
                <p>
                    The global settings for your server.
                </p>
                <p className="text-muted">
                    When saved, these will be written to your <i>local.yaml</i> file. Storing these settings in your
                    local configuration file (rather than the database) allows your WROLPi to be rebuilt and save your
                    settings.
                </p>
                <Divider/>
                <Form id="settings" onSubmit={this.handleSubmit}>

                    <Form.Field>
                        <label>Media Directory</label>
                        <input
                            disabled={this.state.disabled}
                            type="text"
                            placeholder="/some/absolute/path"
                            ref={this.mediaDirectory}
                        />
                    </Form.Field>

                    <p>
                        <b>This directory must already exist</b>.
                        The directory in which your media will be stored. Typically, this will be some external
                        drive like <i>/media/wrolpi</i>.
                    </p>

                    <Divider/>

                    <Form.Field>
                        <label>Timezone</label>
                        <TimezoneSelect
                            value={this.state.timezone}
                            onChange={this.handleTimezoneChange}
                        />
                    </Form.Field>

                    <Button color="blue" type="submit" disabled={this.state.disabled}>
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
        let config = await getConfig();
        this.setState({ready: true, WROLMode: config.wrol_mode});
    }

    toggleWROLMode = async () => {
        // Handle WROL Mode toggling by itself so that other settings are not modified.
        let config = {
            wrol_mode: !this.state.WROLMode,
        }
        await saveConfig(config);
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

class DownloadRow extends React.Component {

    render() {
        let {url, frequency, last_successful_download, status, next_download} = this.props;
        let positive = false;
        if (status === 'pending') {
            positive = true;
        }
        return (
            <Table.Row positive={positive}>
                <Table.Cell>{url}</Table.Cell>
                <Table.Cell>{secondsToFrequency(frequency)}</Table.Cell>
                <Table.Cell>{last_successful_download ? secondsToDate(last_successful_download) : null}</Table.Cell>
                <Table.Cell>{secondsToDate(next_download)}</Table.Cell>
                <Table.Cell>{status}</Table.Cell>
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
        let {url, last_successful_download, status} = this.props;
        let {stopOpen, startOpen} = this.state;

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
                        onClick={this.openStart}
                        color='green'
                    >Start</Button>
                    <Confirm
                        open={startOpen}
                        content='Are you sure you want to restart this download?'
                        confirmButton='Start'
                        onCancel={this.closeStart}
                        onConfirm={this.handleStart}
                    />
                </Table.Cell>
            );
        }

        return (
            <Table.Row positive={positive} negative={negative} warning={warning}>
                <Table.Cell>{url}</Table.Cell>
                <Table.Cell>{last_successful_download ? secondsToDate(last_successful_download) : null}</Table.Cell>
                <Table.Cell>{status}</Table.Cell>
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
            disabled: true,
        };
    }

    async componentDidMount() {
        await this.fetchDownloads();
        await this.fetchStatus();
    }

    killDownloads = async () => {
        await killDownloads();
        this.setState({stopOpen: false}, this.fetchStatus);
    }

    startDownloads = async () => {
        await startDownloads();
        this.setState({stopOpen: false}, this.fetchStatus);
    }

    closeStop = () => {
        this.setState({stopOpen: false});
    }

    openStop = () => {
        this.setState({stopOpen: true});
    }

    fetchDownloads = async () => {
        let data = await getDownloads();
        this.setState({
            once_downloads: data.once_downloads,
            recurring_downloads: data.recurring_downloads,
            pending_downloads: data.pending_downloads,
        });
    }

    fetchStatus = async () => {
        let data = await getDownloaders();
        this.setState({disabled: data['manager_disabled']});
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
                    <Table.HeaderCell>Completed At</Table.HeaderCell>
                    <Table.HeaderCell>Status</Table.HeaderCell>
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
                    <Table.HeaderCell>Status</Table.HeaderCell>
                </Table.Row>
            </Table.Header>
        );

        let onceTable = tablePlaceholder;
        if (this.state.once_downloads !== null && this.state.once_downloads.length === 0) {
            onceTable = <p>No downloads are scheduled to be downloaded.</p>
        } else if (this.state.once_downloads !== null) {
            onceTable = (<Table>
                {stoppableHeader}
                <Table.Body>
                    {this.state.once_downloads.map((i) => <StoppableRow {...i} fetchDownloads={this.fetchDownloads}/>)}
                </Table.Body>
            </Table>);
        }

        let recurringTable = tablePlaceholder;
        if (this.state.recurring_downloads !== null && this.state.recurring_downloads.length === 0) {
            recurringTable = <p>No downloads are scheduled to be downloaded.</p>
        } else if (this.state.recurring_downloads !== null) {
            recurringTable = (<Table>
                {nonStoppableHeader}
                <Table.Body>
                    {this.state.recurring_downloads.map((i) => <DownloadRow {...i}/>)}
                </Table.Body>
            </Table>);
        }

        let {stopOpen} = this.state;
        let allButton = (<>
                <Button
                    onClick={this.openStop}
                    color='red'
                >Stop All</Button>
                <Confirm
                    open={stopOpen}
                    content='Are you sure you want to stop all downloads?'
                    confirmButton='Stop'
                    onCancel={this.closeStop}
                    onConfirm={this.killDownloads}
                />
            </>
        );
        if (this.state.disabled) {
            allButton = (<>
                <Button
                    onClick={this.openStop}
                    color='green'
                >Start All</Button>
                <Confirm
                    open={stopOpen}
                    content='Are you sure you want to start all downloads?'
                    confirmButton='Start'
                    onCancel={this.closeStop}
                    onConfirm={this.startDownloads}
                />
            </>);
        }

        return (
            <div>
                {allButton}
                <Header as='h1'>Downloads</Header>
                {onceTable}

                <Header as='h1'>Recurring Downloads</Header>
                {recurringTable}
            </div>
        );
    }
}

class Admin extends React.Component {

    render() {

        const panes = [
            {menuItem: 'Downloads', render: () => <Tab.Pane><Downloads/></Tab.Pane>},
            {menuItem: 'Settings', render: () => <Tab.Pane><Settings/></Tab.Pane>},
            {menuItem: 'WROL Mode', render: () => <Tab.Pane><WROLMode/></Tab.Pane>},
        ];

        return (
            <Container fluid>
                <Tab panes={panes}/>
            </Container>
        )
    }

}

export default Admin;
