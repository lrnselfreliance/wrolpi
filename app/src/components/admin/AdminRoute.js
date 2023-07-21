import React from 'react';
import {Container} from "semantic-ui-react";
import {getStatus, saveSettings} from "../../api";
import {PageContainer, TabLinks, Toggle} from "../Common";
import {Route, Routes} from "react-router-dom";
import {ThemeContext} from "../../contexts/contexts";
import {Header, Loader, Segment} from "../Theme";
import {DownloadsPage} from "./Downloads";
import {Settings} from "./Settings";
import {Status} from "./Status";

class WROLMode extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            WROLMode: false,
        }
    }

    async componentDidMount() {
        try {
            const {wrol_mode} = await getStatus();
            this.setState({ready: true, WROLMode: wrol_mode});
        } catch (e) {
            console.error(e);
        }
    }

    toggleWROLMode = async (checked) => {
        // Handle WROL Mode toggling by itself so that other settings are not modified.
        let config = {
            wrol_mode: checked,
        }
        await saveSettings(config);
        this.setState({disabled: !this.state.WROLMode, WROLMode: checked});
    }

    render() {
        if (this.state.ready === false) {
            return <Loader active inline='centered'/>
        }

        return <ThemeContext.Consumer>
            {({t}) => <Container fluid>

                <Segment>
                    <Header as="h1">WROL Mode</Header>
                    <Header as='h4'>
                        Enable read-only mode. No content can be deleted or modified. Enable this when the SHTF and you
                        want to prevent any potential loss of data.
                    </Header>
                    <p {...t}>
                        Note: User settings and tags can still be modified.
                    </p>
                    <Toggle
                        checked={this.state.WROLMode}
                        onChange={this.toggleWROLMode}
                        label={this.state.WROLMode ? 'WROL Mode Enabled' : 'WROL Mode Disabled'}
                    />
                </Segment>

            </Container>}
        </ThemeContext.Consumer>
    }
}

export default function AdminRoute() {

    const links = [
        {text: 'Downloads', to: '/admin', key: 'admin', end: true},
        {text: 'Settings', to: '/admin/settings', key: 'settings'},
        {text: 'Status', to: '/admin/status', key: 'status'},
        {text: 'WROL Mode', to: '/admin/wrol', key: 'wrol'},
    ];

    return <PageContainer>
        <TabLinks links={links}/>
        <Routes>
            <Route path='/' exact element={<DownloadsPage/>}/>
            <Route path='settings' exact element={<Settings/>}/>
            <Route path='status' exact element={<Status/>}/>
            <Route path='wrol' exact element={<WROLMode/>}/>
        </Routes>
    </PageContainer>
}
