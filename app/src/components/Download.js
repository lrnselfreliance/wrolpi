import React, {useContext, useState} from "react";
import {getDownloaders, postDownload} from "../api";
import {DirectoryInput, frequencyOptions, HelpPopup, rssFrequencyOptions, WROLModeMessage} from "./Common";
import Icon from "semantic-ui-react/dist/commonjs/elements/Icon";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import {ThemeContext} from "../contexts/contexts";
import {Accordion, Button, Form, FormField, FormGroup, FormInput, Header, Loader, Segment, TextArea} from "./Theme";
import {AccordionContent, AccordionTitle, FormDropdown} from "semantic-ui-react";
import {Link} from "react-router-dom";

const validUrl = /^(http|https):\/\/[^ "]+$/;

class Downloader extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            advancedOpen: false,
            destination: '',
            disabled: this.props.disabled,
            downloader: props.downloader,
            pending: false,
            urls: '',
            valid: true,
            submitted: false,
        };
    }

    submitDownload = async () => {
        let {urls, downloader, destination} = this.state;
        if (urls) {
            this.setState({pending: true, submitted: false});
            try {
                let response = await postDownload(urls, downloader, null, null, null, destination);
                if (response.status === 204) {
                    this.setState({urls: '', pending: false, submitted: true});
                }
            } finally {
                this.setState({pending: false});
            }
        }
    }

    handleInputChange = async (event, {name, value}) => {
        this.setState({[name]: value}, this.validateUrls);
    }

    handleDestinationChange = (value) => {
        this.setState({destination: value});
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

    handleKeydown = async (e) => {
        const {valid, urls} = this.state;
        if (e.keyCode === 13 && e.ctrlKey && urls && valid) {
            await this.submitDownload();
        }
    }

    componentDidMount() {
        document.addEventListener('keydown', this.handleKeydown);
    }

    componentWillUnmount() {
        document.removeEventListener('keydown', this.handleKeydown);
    }

    render() {
        let disabled = !this.state.urls || !this.state.valid || this.state.pending || !this.state.downloader;
        const {advancedOpen, destination, submitted} = this.state;
        const {header, withDestination} = this.props;

        const advancedAccordion = <Accordion>
            <AccordionTitle onClick={() => this.setState({advancedOpen: !advancedOpen})}>
                <Icon name='dropdown'/>Advanced
            </AccordionTitle>
            <AccordionContent active={advancedOpen}>
                <Segment>
                    <FormGroup>
                        <FormField width={16}>
                            <label>Destination</label>
                            <DirectoryInput
                                isDirectory={true}
                                value={destination}
                                setInput={this.handleDestinationChange}
                                placeholder='download/into/custom/directory'
                            />
                        </FormField>
                    </FormGroup>
                </Segment>
            </AccordionContent>
        </Accordion>;

        const viewDownloads = <Link to='/admin'><Icon name='checkmark'/> View downloads</Link>;

        return <ThemeContext.Consumer>
            {({i}) => (<Form onSubmit={this.submitDownload}>
                <WROLModeMessage content='Downloading is disabled while WROL Mode is enabled'/>
                <Header as='h3'>{header}</Header>
                <TextArea required
                          placeholder={'Enter one URL per line'}
                          name='urls'
                          onChange={this.handleInputChange}
                          value={this.state.urls}
                />
                {withDestination && advancedAccordion}
                <Button content='Cancel' onClick={this.props.clearSelected}/>
                <Button primary style={{marginTop: '1em'}} disabled={disabled}>Download</Button>
                {submitted && viewDownloads}
            </Form>)}
        </ThemeContext.Consumer>
    }
}

class ChannelDownload extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            url: '', frequency: 604800, pending: false, disabled: false, ready: false, error: null, success: null,
        };
        this.freqOptions = [{key: 'once', text: 'Once', value: 0}, ...frequencyOptions.slice(1),];
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

        return <Form>
            <WROLModeMessage content='Downloading is disabled while WROL Mode is enabled'/>
            <Header as='h4'><Icon name='film'/> Channel / Playlist</Header>
            <FormInput
                required
                label='URL'
                placeholder='https://example.com/channel/videos'
                value={url}
                error={error}
                onChange={this.handleUrlChange}
            />
            <FormDropdown
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
    }
}

function ExcludedURLsLabel() {
    const {t} = useContext(ThemeContext);
    const excludedURLsHelp = <HelpPopup content='A comma-separated list of words that should not be downloaded.'/>
    return <div style={{marginBottom: '0.5em'}} {...t}>
        Excluded URLs
        {excludedURLsHelp}
    </div>
}

class RSSDownload extends ChannelDownload {
    constructor(props) {
        super(props);
        this.state = {
            disabled: false,
            downloader: null,
            downloaders: [],
            error: null,
            excludedURLs: '',
            frequency: 604800,
            pending: false,
            ready: false,
            sub_downloader: null,
            success: null,
            url: '',
            activeIndex: -1,
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
        const {url, frequency, sub_downloader, excludedURLs} = this.state;
        if (!url) {
            this.setState({error: 'URL is required'});
            return;
        }
        let response = await postDownload(url, 'rss', frequency, sub_downloader, excludedURLs);
        if (response.status === 204) {
            this.setState({pending: false, disabled: false, success: true, url: '', ready: false});
        } else {
            const content = await response.json();
            let error = content.message || null;
            this.setState({pending: false, disabled: false, success: false, error});
        }
    }

    handleAdvancedClick = async (e, {index}) => {
        const {activeIndex} = this.state;
        const newIndex = activeIndex === index ? -1 : index;
        this.setState({activeIndex: newIndex});
    }

    handleExcludedURLsChange = async (e, {value}) => {
        e.preventDefault();
        this.setState({excludedURLs: value});
    }

    render() {
        const {ready, disabled, url, error, frequency, pending, success, activeIndex, excludedURLs} = this.state;
        const buttonDisabled = !ready || disabled;

        const onceMessage = (<Message>
            <Message.Header>Download Once</Message.Header>
            <Message.Content>You have selected a frequency of Once, this is useful when you want to download
                all videos in a Playlist, but you do not want to download any videos added to the playlist
                in the future.</Message.Content>
        </Message>);

        return <Form>
            <WROLModeMessage content='Downloading is disabled while WROL Mode is enabled'/>
            <Header as='h4'><Icon name='rss'/> RSS Feed</Header>
            <FormInput
                required
                label='URL'
                placeholder='https://example.com/feed'
                value={url}
                error={error}
                onChange={this.handleUrlChange}
            />
            <FormDropdown
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
            <FormDropdown selection required
                          name='sub_downloader'
                          label='Downloader'
                          options={this.state.downloaders}
                          placeholder='Select a downloader'
                          onChange={this.handleInputChange}
            />
            <Accordion style={{paddingBottom: '1em'}}>
                <AccordionTitle
                    active={activeIndex === 0}
                    index={0}
                    onClick={this.handleAdvancedClick}
                >
                    <Icon name='dropdown'/>
                    Advanced
                </AccordionTitle>
                <AccordionContent active={activeIndex === 0}>
                    <FormInput
                        label={<ExcludedURLsLabel/>}
                        placeholder='example.com,example.org'
                        value={excludedURLs}
                        error={error}
                        onChange={this.handleExcludedURLsChange}
                    />
                </AccordionContent>
            </Accordion>

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
    }
}

export function DownloadMenu({onOpen, disabled}) {
    const [downloader, setDownloader] = useState();

    const localOnOpen = (name) => {
        setDownloader(name);
        onOpen(name)
    }

    let body = (<>
        <Button
            color='blue'
            content='Videos'
            disabled={disabled}
            onClick={() => localOnOpen('video')}
            style={{marginBottom: '1em'}}
        />
        <Button
            color='green'
            content='Archive'
            disabled={disabled}
            onClick={() => localOnOpen('archive')}
            style={{marginBottom: '1em'}}
        />
        <Button
            color='blue'
            content='Channel/Playlist'
            disabled={disabled}
            onClick={() => localOnOpen('video_channel')}
            style={{marginBottom: '1em'}}
        />
        <Button
            content='RSS Feed'
            disabled={disabled}
            onClick={() => localOnOpen('rss')}
            style={{marginBottom: '1em'}}
        />
    </>);

    function clearSelected() {
        localOnOpen(null);
        body = null;
    }

    const downloaders = {
        archive: <Downloader
            clearSelected={clearSelected}
            header={<><Icon name='file alternate'/> Archive</>}
            downloader='archive'/>,
        video: <Downloader
            clearSelected={clearSelected}
            header={<><Icon name='film'/> Videos</>}
            downloader='video'
            withDestination={true}/>,
        video_channel: <ChannelDownload clearSelected={clearSelected}/>,
        rss: <RSSDownload
            clearSelected={clearSelected}
            header={<><Icon name='rss square'/> RSS</>}/>,
    };

    body = downloader in downloaders ? downloaders[downloader] : body;

    return <>
        <Header as='h2'>Download</Header>
        {body}
    </>
}
