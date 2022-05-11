import React from "react";
import {Button, Dropdown, Form, Header, Segment, TextArea} from "semantic-ui-react";
import {getDownloaders, postDownload} from "../api";
import {WROLModeMessage} from "./Common";
import {Link} from "react-router-dom";

const validUrl = /^(http|https):\/\/[^ "]+$/;

class Downloader extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            urls: '',
            valid: true,
            pending: false,
            downloaders: [],
            downloader: null,
        };
    }

    async componentDidMount() {
        await this.fetchDownloaders();
    }

    fetchDownloaders = async () => {
        let {downloaders} = await getDownloaders();
        downloaders = downloaders.map((i) => {
            return {key: i.name, text: i.pretty_name || i.name, value: i.name}
        })
        this.setState({downloaders});
    }

    submitDownload = async () => {
        let {urls, downloader} = this.state;
        if (urls) {
            this.setState({pending: true});
            try {
                let response = await postDownload(urls, downloader);
                if (response.status === 204) {
                    this.setState({urls: '', pending: false});
                }
            } finally {
                this.setState({pending: false});
            }
        }
    }

    handleInputChange = async (event, {name, value}) => {
        this.setState({[name]: value}, this.validateUrls);
    }

    validateUrls = async () => {
        // Validate that all URLs in state are valid.
        if (this.state.urls) {
            let urls = this.state.urls.split(/\r?\n/);
            let valid = true;
            urls.forEach((url) => {
                if (valid && url && !validUrl.test(url)) {
                    valid = false;
                }
            })
            this.setState({valid});
        }
    }

    render() {
        let textareaPlaceholder = 'Enter one URL per line';
        let disabled = !this.state.urls || !this.state.valid || this.state.pending || !this.state.downloader;

        return (
            <Form onSubmit={this.submitDownload}>
                <WROLModeMessage content='Downloading is disabled while WROL Mode is enabled'/>
                <Header as='h4'>Enter the URLs you wish to save offline.</Header>
                <Form.Field>
                    <TextArea
                        placeholder={textareaPlaceholder}
                        name='urls'
                        onChange={this.handleInputChange}
                        value={this.state.urls}
                        error={!this.state.valid}
                    />
                </Form.Field>
                <Form.Field>
                    <Dropdown selection
                              name='downloader'
                              options={this.state.downloaders}
                              placeholder='Select a downloader'
                              onChange={this.handleInputChange}
                    />
                </Form.Field>
                <Button primary style={{marginTop: '1em'}} disabled={disabled}>Download</Button>
                <Link to={'/admin'}>View Downloads</Link>
            </Form>
        )
    }
}

export class Saver extends React.Component {

    render() {
        return (
            <>
                <Segment>
                    <Downloader/>
                </Segment>
            </>
        )
    }
}
