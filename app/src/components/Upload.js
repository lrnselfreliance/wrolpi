import React, {useState} from "react";
import {Button, Form, Header, Loader, TextArea} from "semantic-ui-react";
import {getDownloaders, postDownload} from "../api";
import {frequencyOptions, rssFrequencyOptions, WROLModeMessage} from "./Common";
import Icon from "semantic-ui-react/dist/commonjs/elements/Icon";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";

const validUrl = /^(http|https):\/\/[^ "]+$/;

class Downloader extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            urls: '',
            valid: true,
            pending: false,
            downloader: props.downloader,
        };
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
        let disabled = !this.state.urls || !this.state.valid || this.state.pending || !this.state.downloader;
        const {header} = this.props;

        return (
            <Form onSubmit={this.submitDownload}>
                <WROLModeMessage content='Downloading is disabled while WROL Mode is enabled'/>
                <Header as='h3'>{header}</Header>
                <Form.Field>
                    <TextArea required
                              placeholder={'Enter one URL per line'}
                              name='urls'
                              onChange={this.handleInputChange}
                              value={this.state.urls}
                    />
                </Form.Field>
                <Button content='Cancel' onClick={this.props.clearSelected}/>
                <Button primary style={{marginTop: '1em'}} disabled={disabled}>Download</Button>
            </Form>
        )
    }
}

class ChannelDownload extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            url: '',
            frequency: 604800,
            pending: false,
            disabled: false,
            ready: false,
            error: null,
            success: null,
        };
        this.freqOptions = [
            {key: 'once', text: 'Once', value: 0},
            ...frequencyOptions,
        ];
        this.handleUrlChange = this.handleUrlChange.bind(this);
        this.handleSubmit = this.handleSubmit.bind(this);
        this.handleFrequencyChange = this.handleFrequencyChange.bind(this);
    }

    handleUrlChange = (e, {value}) => {
        e.preventDefault();
        let ready = value && validUrl.test(value);
        this.setState({url: value, ready, success: false});
    }

    handleFrequencyChange(e, {value}) {
        this.setState({frequency: value, success: false});
    }

    handleSubmit = async (e) => {
        e.preventDefault();
        this.setState({disabled: true, pending: true, success: null, error: null});
        const {url, frequency} = this.state;
        if (!url) {
            this.setState({error: 'URL is required'});
            return;
        }
        let response = await postDownload(url, 'video_channel', frequency);
        if (response.status === 204) {
            this.setState({pending: false, disabled: false, success: true, url: '', ready: false});
        } else {
            const content = await response.json();
            let error = content.message || null;
            this.setState({pending: false, disabled: false, success: false, error});
        }
    }

    render() {
        const {ready, disabled, url, error, frequency, pending, success} = this.state;
        const buttonDisabled = !ready || disabled;

        const onceMessage = (<Message>
            <Message.Header>Download Once</Message.Header>
            <Message.Content>You have selected a frequency of Once, this is useful when you want to download
                all videos in a Playlist, and when you do not want to download any videos added to the playlist
                in the future.</Message.Content>
        </Message>);

        return (
            <Form>
                <Header as='h4'><Icon name='video'/> Channel / Playlist</Header>
                <Form.Input
                    required
                    label='URL'
                    placeholder='https://example.com/channel/videos'
                    value={url}
                    error={error}
                    onChange={this.handleUrlChange}
                />
                <Form.Dropdown
                    required
                    selection
                    label='Download Frequency'
                    name='download_frequency'
                    placeholder='Frequency'
                    options={this.freqOptions}
                    value={frequency}
                    selected={frequency}
                    onChange={this.handleFrequencyChange}
                />

                {frequency === 0 && onceMessage}

                <Button content='Cancel' onClick={this.props.clearSelected}/>
                <Button
                    color='blue'
                    content='Download'
                    onClick={this.handleSubmit}
                    disabled={buttonDisabled}
                />
                <Loader active={pending}/>
                {success && <Icon name='check'/>}
            </Form>
        )
    }
}

class RSSDownload extends ChannelDownload {
    constructor(props) {
        super(props);
        this.state = {
            url: '',
            frequency: 604800,
            pending: false,
            disabled: false,
            ready: false,
            error: null,
            success: null,
            downloaders: [],
            downloader: null,
            sub_downloader: null,
        };
        this.freqOptions = rssFrequencyOptions;
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

    handleInputChange = async (event, {name, value}) => {
        this.setState({[name]: value});
    }

    handleSubmit = async (e) => {
        e.preventDefault();
        this.setState({disabled: true, pending: true, success: null, error: null});
        const {url, frequency, sub_downloader} = this.state;
        if (!url) {
            this.setState({error: 'URL is required'});
            return;
        }
        let response = await postDownload(url, 'rss', frequency, sub_downloader);
        if (response.status === 204) {
            this.setState({pending: false, disabled: false, success: true, url: '', ready: false});
        } else {
            const content = await response.json();
            let error = content.message || null;
            this.setState({pending: false, disabled: false, success: false, error});
        }
    }

    render() {
        const {ready, disabled, url, error, frequency, pending, success} = this.state;
        const buttonDisabled = !ready || disabled;

        const onceMessage = (<Message>
            <Message.Header>Download Once</Message.Header>
            <Message.Content>You have selected a frequency of Once, this is useful when you want to download
                all videos in a Playlist, but you do not want to download any videos added to the playlist
                in the future.</Message.Content>
        </Message>);

        return (
            <Form>
                <Header as='h4'><Icon name='rss'/> RSS Feed</Header>
                <Form.Input
                    required
                    label='URL'
                    placeholder='https://example.com/feed'
                    value={url}
                    error={error}
                    onChange={this.handleUrlChange}
                />
                <Form.Dropdown
                    required
                    selection
                    label='Download Frequency'
                    name='download_frequency'
                    placeholder='Frequency'
                    options={this.freqOptions}
                    value={frequency}
                    selected={frequency}
                    onChange={this.handleFrequencyChange}
                />
                {frequency === 0 && onceMessage}
                <Form.Dropdown selection required
                               name='sub_downloader'
                               label='Downloader'
                               options={this.state.downloaders}
                               placeholder='Select a downloader'
                               onChange={this.handleInputChange}
                />

                <Button content='Cancel' onClick={this.props.clearSelected}/>
                <Button
                    color='blue'
                    content='Download'
                    onClick={this.handleSubmit}
                    disabled={buttonDisabled}
                />
                <Loader active={pending}/>
                {success && <Icon name='check'/>}
            </Form>
        )
    }
}

export function Downloads() {
    const [downloader, setDownloader] = useState();

    let body = (<>
        <Button content='Videos' onClick={() => setDownloader('video')}/>
        <Button content='Archive' onClick={() => setDownloader('archive')}/>
        <Button content='Channel/Playlist' onClick={() => setDownloader('video_channel')}/>
        <Button content='RSS Feed' onClick={() => setDownloader('rss')}/>
    </>);

    function clearSelected() {
        setDownloader(null);
        body = null;
    }

    const downloaders = {
        'archive': <Downloader clearSelected={clearSelected} header={<><Icon name='file alternate'/> Archive</>}
                               downloader='archive'/>,
        'video': <Downloader clearSelected={clearSelected} header={<><Icon name='video'/> Videos</>}
                             downloader='video'/>,
        'video_channel': <ChannelDownload clearSelected={clearSelected}/>,
        'rss': <RSSDownload clearSelected={clearSelected} header={<><Icon name='rss square'/> RSS</>}/>,
    };

    body = downloader in downloaders ? downloaders[downloader] : body;

    return (
        <>
            <Header as='h2'>Download</Header>
            {body}
        </>
    )
}
