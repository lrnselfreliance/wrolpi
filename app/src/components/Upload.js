import React from "react";
import {Button, Form, Header, Segment, TextArea} from "semantic-ui-react";
import {postDownload} from "../api";

const validUrl = /^(http|https):\/\/[^ "]+$/;

class Downloader extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            urls: '',
            valid: true,
        };
    }

    submitDownload = async () => {
        if (this.state.urls) {
            let response = await postDownload(this.state.urls);
            if (response.status === 204) {
                this.setState({urls: ''});
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
        let disabled = !this.state.urls || !this.state.valid;

        return (
            <Form onSubmit={this.submitDownload}>
                <Header as='h4'>Enter the URLs you wish to bring offline.</Header>
                <TextArea
                    placeholder={textareaPlaceholder}
                    name='urls'
                    onChange={this.handleInputChange}
                    value={this.state.urls}
                    error={!this.state.valid}
                />
                <Button primary style={{marginTop: '1em'}} disabled={disabled}>Download</Button>
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
