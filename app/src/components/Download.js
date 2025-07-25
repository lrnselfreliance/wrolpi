import React, {useState} from "react";
import {fetchVideoDownloaderConfig, getDownloaders, postDownload, putDownload} from "../api";
import {
    APIButton,
    DirectorySearch,
    InfoHeader,
    InfoPopup,
    mergeDeep,
    RequiredAsterisk,
    useLocalStorage
} from "./Common";
import Icon from "semantic-ui-react/dist/commonjs/elements/Icon";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import {Button, Form, FormInput, Header} from "./Theme";
import {Form as SForm, FormDropdown} from "semantic-ui-react";
import {Link} from "react-router-dom";
import {TagsSelector} from "../Tags";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {
    commaSeparatedValidator,
    InputForm,
    NumberInputForm,
    ToggleForm,
    UrlInput,
    UrlsTextarea,
    useForm
} from "../hooks/useForm";
import {
    channelFrequencyOptions,
    days30Option,
    defaultVideoFormatOption,
    defaultVideoResolutionOptions,
    Downloaders,
    downloadFormatOptions,
    downloadOrderOptions,
    downloadResolutionOptions,
    extendedFrequencyOptions,
    frequencyOptions,
    weeklyOption
} from "./Vars";
import _ from "lodash";

export function DepthInputForm({form, required, name = 'depth', path = 'settings.depth'}) {
    return <NumberInputForm
        form={form}
        required={required}
        name={name}
        path={path}
        label='Depth'
        max={4}
        helpContent='Search the URLs provided, and any URLs they contain up to this depth. Warning: This can be exponential!'
    />
}

export function MaximumPagesInputForm({form, required, name = 'max_pages', path = 'settings.max_pages'}) {
    return <NumberInputForm
        form={form}
        required={required}
        name={name}
        path={path}
        label='Maximum Pages'
        max={100000}
        helpContent='Stop searching for files if this many pages have been searched.'
    />
}

export function DestinationForm({
                                    form,
                                    infoContent,
                                    label = 'Destination',
                                    name = 'destination',
                                    path = 'destination',
                                    required = false,
                                }) {
    const [inputProps, inputAttrs] = form.getCustomProps({name, path, required});
    const {disabled, value, onChange} = inputProps;
    const infoPopup = infoContent ? <InfoPopup content={infoContent}/> : null;
    return <SForm.Field>
        <label>{label} {required && <RequiredAsterisk/>}{infoPopup}</label>
        <DirectorySearch
            required={required}
            value={value}
            onSelect={onChange}
            disabled={disabled}
            id='destination_search_form'
        />
    </SForm.Field>
}

export function DownloadTagsSelector({form, limit, path = 'tag_names', name = 'tag_names'}) {
    const [inputProps, inputAttrs] = form.getCustomProps({name, path});
    const {value, onChange} = inputProps;

    return <TagsSelector
        disabled={form.disabled}
        selectedTagNames={value}
        limit={limit}
        onChange={onChange}
        closeAfterAdd={!!limit}
    />;
}

export function DownloadFrequencySelector({
                                              form,
                                              freqOptions = frequencyOptions,
                                              name = 'frequency',
                                              path = 'frequency',
                                          }) {
    const [inputProps, inputAttrs] = form.getSelectionProps({name: 'frequency', path});

    return <FormDropdown
        required
        selection
        label='Download Frequency'
        placeholder='Frequency'
        options={freqOptions}
        name={name}
        id='download_frequency_selector'
        {...inputProps}
    />
}

export function DownloaderSelector({form, name = 'sub_downloader', path = 'sub_downloader'}) {
    const [downloaders, setDownloaders] = React.useState([]);
    const [inputProps, inputAttrs] = form.getSelectionProps({name, path, required: true});

    const fetchDownloaders = async () => {
        let {downloaders: downloaders_} = await getDownloaders();
        downloaders_ = downloaders_.map((i) => {
            return {key: i.name, text: i.pretty_name || i.name, value: i.name}
        })
        setDownloaders(downloaders_);
    }

    React.useEffect(() => {
        fetchDownloaders();
    }, []);

    return <FormDropdown selection required
                         label='Downloader'
                         placeholder='Select a downloader'
                         options={downloaders}
                         id='downloader_selector'
                         {...inputProps}
    />
}

export function ExcludedUrls({form, name = 'excluded_urls', path = 'settings.excluded_urls'}) {
    return <InputForm
        form={form}
        type='text'
        name={name}
        path={path}
        helpContent="Comma-separated list of keywords that will be ignored if they are in any link's URL"
        label='Excluded URLs'
        placeholder='prize,gift'
        validator={commaSeparatedValidator}
    />
}

export function TitleInclusionInput({form, path = 'settings.title_include'}) {
    const [inputProps, inputAttrs] = form.getInputProps({
        name: 'title_include',
        path,
        validator: commaSeparatedValidator,
    });

    return <>
        <InfoHeader
            headerSize='h4'
            headerContent='Title Match Words'
            popupContent='List of words, separated by commas, that titles must contain to be downloaded.'
        />
        <FormInput
            placeholder='Shelter,Solar Power'
            error={inputProps.error}
        >
            <input {...inputProps}/>
        </FormInput>
    </>
}

export function TitleExclusionInput({form, path = 'settings.title_exclude'}) {
    const [inputProps, inputAttrs] = form.getInputProps({
        name: 'title_exclude',
        path,
        validator: commaSeparatedValidator,
    });

    return <>
        <InfoHeader
            headerSize='h4'
            headerContent='Title Exclusion Words'
            popupContent='List of words, separated by commas, that may not appear in titles to be downloaded.'
        />
        <FormInput
            placeholder='Giveaway,Prize'
            error={inputProps.error}
        >
            <input {...inputProps}/>
        </FormInput>
    </>
}

export function DownloadFormButtons({onCancel, form}) {
    return <Grid columns={2}>
        <Grid.Row>
            <Grid.Column textAlign='left'>
                <Button content='Cancel' onClick={onCancel} type='button'/>
            </Grid.Column>
            <Grid.Column textAlign='right'>
                <APIButton
                    disabled={form.disabled || !form.ready}
                    type='submit'
                    style={{marginTop: '0.5em'}}
                    onClick={form.onSubmit}
                    id='download_form_download_button'
                >Download</APIButton>
            </Grid.Column>
        </Grid.Row>
    </Grid>
}

export function EditDownloadFormButtons({onDelete, onCancel, form}) {
    return <Grid columns={2}>
        <Grid.Row>
            <Grid.Column textAlign='left'>
                <APIButton
                    confirmButton='Delete'
                    confirmContent='Delete this Download?'
                    confirmHeader='Delete'
                    color='red'
                    onClick={onDelete}
                >Delete</APIButton>
            </Grid.Column>
            <Grid.Column textAlign='right'>
                <Button content='Cancel' onClick={onCancel}/>
                <APIButton
                    disabled={form.disabled || !form.ready}
                    type='submit'
                    style={{marginTop: '0.5em'}}
                    onClick={form.onSubmit}
                >Save</APIButton>
            </Grid.Column>
        </Grid.Row>
    </Grid>
}

function VideoDownloadOrder({form, path = 'settings.download_order'}) {
    const [inputProps, inputAttrs] = form.getSelectionProps({
        name: 'download_order',
        path,
    });

    return <FormDropdown selection
                         label='Download Order'
                         options={downloadOrderOptions}
                         {...inputProps}
    />
}

function VideoDownloadCountLimit({form, name = 'video_count_limit', path = 'settings.video_count_limit'}) {
    return <NumberInputForm
        form={form}
        helpContent='Stop downloading videos from this channel/playlist when this many have been downloaded.'
        helpPosition='top right'
        name={name}
        path={path}
        label='Video Count Limit'
        placeholder='100'
    />
}

export function VideoResolutionSelectorForm({form, name = 'video_resolutions', path = 'settings.video_resolutions', onChange}) {
    const [inputProps, inputAttrs] = form.getSelectionProps({
        name,
        path,
        type: 'array',
        afterChange: onChange
    });

    return <>
        <InfoHeader
            headerSize='h5'
            headerContent='Video Resolutions'
            popupContent='Videos will be downloaded in the first available resolution from the list you select.'
            for_='video_resolutions_input'
        />
        <FormDropdown selection multiple
                      id='video_resolutions_input'
                      options={downloadResolutionOptions}
                      {...inputProps}
        />
    </>
}

function VideoFormatSelectorForm({form, name = 'video_format', path = 'settings.video_format'}) {
    const [inputProps, inputAttrs] = form.getSelectionProps({
        name,
        path,
        defaultValue: defaultVideoFormatOption,
    });

    return <>
        <InfoHeader
            headerSize='h5'
            headerContent='Video Format'
            popupContent='Videos will be downloaded in this format, or transcoded if not available.'
            for_='video_format_input'
        />
        <FormDropdown selection
                      id='video_format_input'
                      options={downloadFormatOptions}
                      {...inputProps}
        />
    </>
}

function VideoDurationLimit({form, name, path, label, helpContent, placeholder, helpPosition}) {
    return <NumberInputForm
        form={form}
        helpContent={helpContent}
        helpPosition={helpPosition}
        placeholder={placeholder}
        name={name}
        path={path}
        label={label}
    />
}

export function VideoTagsForm({form}) {
    return <>
        <InfoHeader
            headerSize='h4'
            headerContent='Videos Tags'
            popupContent='Tag all Videos with these Tags.'
        />
        <DownloadTagsSelector form={form}/>
    </>
}

export function ChannelTagNameForm({form}) {
    return <>
        <InfoHeader
            headerSize='h4'
            headerContent='Channel Tag'
            popupContent='If the Channel is new, apply this Tag.'
        />
        <DownloadTagsSelector
            form={form}
            limit={1}
            name='channel_tag_name'
            path='settings.channel_tag_name'
        />
    </>
}

export function UseBrowserProfile({form}) {
    const [config, setConfig] = useState(null);

    const localFetchConfig = async () => {
        const result = await fetchVideoDownloaderConfig();
        setConfig(result);
        if (result?.always_use_browser_profile === true) {
            // Enable the toggle if "always_use_browser_profile" is set.
            form.setValue('settings.use_browser_profile', true);
        }
    }

    React.useEffect(() => {
        localFetchConfig();
    }, []);

    const popupContent = <>Use the browser profile to download videos.
        This is useful for downloading videos that require a login. See: <i>Videos > Settings</i></>;
    const label = <InfoHeader
        headerSize='h4'
        headerContent='Use Browser Profile'
        popupContent={popupContent}
    />;
    return <ToggleForm
        form={form}
        label={label}
        disabled={!config?.browser_profile}
        name='use_browser_profile'
        path='settings.use_browser_profile'
    />
}

export function VideosDownloadForm({singleDownload = true, onCancel, onSuccess: propOnSuccess, download, submitter: propSubmitter, actions}) {
    const [showMessage, setShowMessage] = React.useState(false);
    const [userChangedResolutions, setUserChangedResolutions] = React.useState(false);
    const [config, setConfig] = React.useState(null);

    // Keep video format in session to help user start downloads consistently.
    const [defaultVideoFormat, setDefaultVideoFormat] = useLocalStorage('video_format', defaultVideoFormatOption);

    // Use config video resolutions if available, otherwise use default
    const configResolutions = config && config.video_resolutions ? config.video_resolutions : defaultVideoResolutionOptions;

    const defaultFormData = {
        urls: '', // Textarea, one URL per line.
        destination: '',
        tag_names: [],
        downloader: Downloaders.Video,
        settings: {
            use_browser_profile: false,
            video_format: defaultVideoFormat,
            video_resolutions: configResolutions,
        }
    }

    const submitter = propSubmitter || (async (formData) => {
        const downloadData = {
            destination: formData.destination,
            downloader: formData.downloader,
            settings: formData.settings,
            tag_names: formData.tag_names,
            urls: formData.urls.split(/r?\n/),
        }
        await postDownload(downloadData);
    });

    const onSuccess = () => {
        setShowMessage(true);
        if (propOnSuccess) {
            propOnSuccess();
        } else {
            form.reset();
        }
    }

    const form = useForm({
        submitter,
        defaultFormData: download ? mergeDeep(defaultFormData, download) : defaultFormData,
        onSuccess,
    });

    // Fetch video downloader config when the modal opens
    React.useEffect(() => {
        const fetchConfig = async () => {
            try {
                const result = await fetchVideoDownloaderConfig();
                setConfig(result);

                // Update form with video resolutions from config only if user hasn't changed them
                // and if no download object was provided (this is a new download, not an edit)
                if (result && result.video_resolutions && !userChangedResolutions && !download) {
                    form.setValue('settings.video_resolutions', result.video_resolutions);
                }
            } catch (error) {
                console.error('Failed to fetch video downloader config:', error);
            }
        };

        fetchConfig();
    }, []);

    React.useEffect(() => {
        const {video_format} = form.formData.settings;
        if (video_format && video_format !== defaultVideoFormat) {
            setDefaultVideoFormat(video_format);
        }
    }, [form.formData]);

    const localOnCancel = (e) => {
        if (e) e.preventDefault();
        if (onCancel) {
            onCancel();
        }
    }

    // This form can handle a single Video download, or multiple video downloads.
    const urlInput = singleDownload ?
        <UrlInput required form={form} path='urls'/>
        : <UrlsTextarea required form={form}/>;

    return <Form>
        <Header as='h3'>
            <Icon name='film' color='blue'/>
            Videos
        </Header>
        <p>Download each video at the URLs provided below.</p>

        <Grid stackable columns={1}>
            <Grid.Row>
                <Grid.Column>{urlInput}</Grid.Column>
            </Grid.Row>
            <Grid.Row>
                <Grid.Row columns={1}>
                    <Grid.Column>
                        <VideoTagsForm form={form}/>
                    </Grid.Column>
                </Grid.Row>
            </Grid.Row>
            <Grid.Row>
                <Grid.Column>
                    <DestinationForm
                        form={form}
                        helpContent="Videos download into their Channel's directory, by default.  If this is provided, then videos in this Channel/Playlist will download to this directory instead."
                    />
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={2}>
                <Grid.Column width={11}>
                    <VideoResolutionSelectorForm
                        form={form}
                        onChange={() => setUserChangedResolutions(true)}
                    />
                </Grid.Column>
                <Grid.Column width={4}>
                    <VideoFormatSelectorForm form={form}/>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row>
                <Grid.Column>
                    <UseBrowserProfile form={form}/>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={1}>
                <Grid.Column>
                    <ChannelTagNameForm form={form}/>
                </Grid.Column>
            </Grid.Row>
            {showMessage && <SuccessfulDownloadSubmitMessage/>}
            <Grid.Row>
                <Grid.Column>
                    {actions ? actions({onCancel: localOnCancel, form}) : <DownloadFormButtons onCancel={localOnCancel} form={form}/>}
                </Grid.Column>
            </Grid.Row>
        </Grid>
    </Form>
}


export function VideoMinimumDurationForm({form}) {
    return <VideoDurationLimit
        form={form}
        path='settings.minimum_duration'
        label='Minimum Duration'
        name='minimum_duration'
        helpContent='Download only Videos this many seconds long, or greater.'
        placeholder='60'
    />
}

export function EditVideosDownloadForm({
    download,
    onCancel,
    onSuccess,
    onDelete,
    actions = EditDownloadFormButtons,
}) {
    const submitter = async (formData) => {
        // Create a copy of settings without channel_url and channel_id
        const settings = {...formData.settings};
        // These settings are created when downloading the video, we can't submit them again.
        delete settings.channel_url;
        delete settings.channel_id;

        const downloadData = {
            destination: formData.destination,
            downloader: formData.downloader,
            settings: settings,
            tag_names: formData.tag_names,
            urls: formData.urls.split(/r?\n/),
        }
        await putDownload(download.id, downloadData);
    }

    return <VideosDownloadForm
        singleDownload={true}
        onCancel={onCancel}
        onSuccess={onSuccess}
        download={download}
        submitter={submitter}
        actions={(props) => actions({...props, onDelete})}
    />
}

export function VideoMaximumDurationForm({form}) {
    return <VideoDurationLimit
        form={form}
        path='settings.maximum_duration'
        label='Maximum Duration'
        name='maximum_duration'
        helpContent='Do not download videos longer than this many seconds.'
        placeholder='3600'
    />
}


export function ChannelDownloadForm({
                                        download,
                                        onCancel,
                                        onSuccess,
                                        onDelete = async () => {
                                        },
                                        submitter,
                                        actions = null,
                                        clearOnSuccess = true,
                                        channel_id = null,
                                    }) {
    const [showMessage, setShowMessage] = React.useState(false);
    const [config, setConfig] = React.useState(null);
    const [isConfigLoaded, setIsConfigLoaded] = React.useState(false);
    const [userChangedResolutions, setUserChangedResolutions] = React.useState(false);

    // May have received submitter from EditChannelDownloadForm.
    submitter = submitter || (async (formData) => {
        const downloadData = {
            destination: formData.destination,
            downloader: formData.downloader,
            frequency: formData.frequency,
            settings: formData.settings,
            sub_downloader: formData.sub_downloader,
            tag_names: formData.tag_names || [],
            urls: [formData.url,],
        }
        await postDownload(downloadData);
    });

    const localOnSuccess = async () => {
        setShowMessage(true);
        if (onSuccess) {
            onSuccess();
        }
    }

    // Keep video format in session to help user start downloads consistently.
    const [defaultVideoFormat, setDefaultVideoFormat] = useLocalStorage('video_format', defaultVideoFormatOption);

    // Use config video resolutions if available, otherwise use default
    const configResolutions = config && config.video_resolutions ? config.video_resolutions : defaultVideoResolutionOptions;

    const emptyFormData = {
        destination: '',
        downloader: Downloaders.VideoChannel,
        frequency: days30Option.value,
        url: '',
        settings: {
            channel_id,
            channel_tag_name: [],
            download_order: 'newest',
            maximum_duration: null,
            minimum_duration: null,
            title_exclude: null,
            title_include: null,
            use_browser_profile: false,
            video_count_limit: null,
            video_format: defaultVideoFormat,
            video_resolutions: configResolutions,
        },
        sub_downloader: Downloaders.Video,
        tag_names: [],
    };

    const form = useForm({
        submitter,
        defaultFormData: mergeDeep(emptyFormData, download),
        emptyFormData,
        onSuccess: localOnSuccess,
        clearOnSuccess,
    });

    // Fetch video downloader config when the modal opens
    React.useEffect(() => {
        const fetchConfig = async () => {
            try {
                const result = await fetchVideoDownloaderConfig();
                setConfig(result);
                setIsConfigLoaded(true);

                // Update form with video resolutions from config only if user hasn't changed them
                // and if no download object was provided (this is a new download, not an edit)
                if (result && result.video_resolutions && !userChangedResolutions && !download) {
                    form.setValue('settings.video_resolutions', result.video_resolutions);
                }
            } catch (error) {
                console.error('Failed to fetch video downloader config:', error);
                setIsConfigLoaded(true);
            }
        };

        fetchConfig();
    }, []);

    React.useEffect(() => {
        const {video_format} = form.formData.settings;
        if (video_format && video_format !== defaultVideoFormat) {
            setDefaultVideoFormat(video_format);
        }
    }, [form.formData]);

    const onceMessage = <Message>
        <Message.Header>Download Once</Message.Header>
        <Message.Content>You have selected a frequency of Once, this is useful when you want to download
            all videos in a Playlist, and when you do not want to download any videos added to the playlist
            in the future.</Message.Content>
    </Message>;

    // Default to "new" download buttons.
    actions = actions || DownloadFormButtons;
    const actionsElm = actions({onDelete, onCancel, form});

    return <Form>
        <Header as='h3'><Icon name='film' color='blue'/> Channel / Playlist</Header>

        <Grid stackable columns={1}>
            <Grid.Row>
                <Grid.Column>
                    <UrlInput required form={form}/>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={1}>
                <Grid.Column>
                    <VideoTagsForm form={form}/>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={2}>
                <Grid.Column mobile={4} tablet={4}>
                    <DownloadFrequencySelector form={form} freqOptions={channelFrequencyOptions}/>
                </Grid.Column>
                <Grid.Column mobile={4} tablet={12}>
                    <DestinationForm
                        form={form}
                        helpContent='Destination is not required.  Videos will download into the automatically created Channel directory.'
                    />
                </Grid.Column>
            </Grid.Row>
            {form.formData.frequency === 0 && <Grid.Row><Grid.Column>{onceMessage}</Grid.Column></Grid.Row>}
            <Grid.Row columns={2}>
                <Grid.Column>
                    <TitleInclusionInput form={form}/>
                </Grid.Column>
                <Grid.Column>
                    <TitleExclusionInput form={form}/>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={2}>
                <Grid.Column mobile={4} tablet={5}>
                    <VideoDownloadOrder form={form}/>
                </Grid.Column>
                <Grid.Column mobile={4} tablet={5}>
                    <VideoDownloadCountLimit form={form}/>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={2}>
                <Grid.Column width={11}>
                    <VideoResolutionSelectorForm
                        form={form}
                        onChange={() => setUserChangedResolutions(true)}
                    />
                </Grid.Column>
                <Grid.Column width={4}>
                    <VideoFormatSelectorForm form={form}/>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={2}>
                <Grid.Column tablet={8} computer={4}>
                    <VideoMinimumDurationForm form={form}/>
                </Grid.Column>
                <Grid.Column tablet={8} computer={4}>
                    <VideoMaximumDurationForm form={form}/>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={1}>
                <Grid.Column>
                    <ChannelTagNameForm form={form}/>
                </Grid.Column>
            </Grid.Row>
            {showMessage && <SuccessfulDownloadSubmitMessage/>}
            <Grid.Row>
                <Grid.Column textAlign='right'>
                    {actionsElm}
                </Grid.Column>
            </Grid.Row>
        </Grid>
    </Form>
}

export function EditChannelDownloadForm({
                                            download,
                                            onCancel,
                                            onSuccess,
                                            onDelete,
                                            withTags = true,
                                            actions = EditDownloadFormButtons,
                                        }) {

    const submitter = async (formData) => {
        const downloadData = {
            destination: formData.destination,
            downloader: formData.downloader,
            frequency: formData.frequency,
            settings: formData.settings,
            tag_names: formData.tag_names || [],
            urls: [formData.url,],
        }
        await putDownload(download.id, downloadData);
    }

    return <ChannelDownloadForm
        download={download}
        submitter={submitter}
        onCancel={onCancel}
        onSuccess={onSuccess}
        onDelete={onDelete}
        withTags={withTags}
        actions={actions}
        clearOnSuccess={false}
    />
}

function SuccessfulDownloadSubmitMessage() {
    return <Grid.Row>
        <Grid.Column><Message positive>
            <Message.Header>Download Submitted</Message.Header>
            <Message.Content>
                <Link to='/admin'><Icon name='checkmark'/> View downloads</Link>
            </Message.Content>
        </Message>
        </Grid.Column>
    </Grid.Row>
}

export function EditArchiveDownloadForm({
    download,
    onCancel,
    onSuccess,
    onDelete,
    actions = EditDownloadFormButtons,
}) {
    const submitter = async (formData) => {
        const downloadData = {
            downloader: formData.downloader,
            tag_names: formData.tag_names,
            urls: formData.urls.split(/\r?\n/),
        }
        await putDownload(download.id, downloadData);
    }

    return <ArchiveDownloadForm
        download={download}
        onCancel={onCancel}
        onSuccess={onSuccess}
        submitter={submitter}
        actions={(props) => actions({...props, onDelete})}
    />
}

export function ArchiveDownloadForm({download, onCancel, onSuccess: propOnSuccess, submitter: propSubmitter, actions}) {
    const [showMessage, setShowMessage] = React.useState(false);

    const submitter = propSubmitter || (async (formData) => {
        const downloadData = {
            downloader: formData.downloader,
            tag_names: formData.tag_names,
            urls: formData.urls.split(/\r?\n/),
        }
        await postDownload(downloadData);
    });

    const emptyFormData = {
        downloader: Downloaders.Archive,
        urls: '',
        tag_names: [],
    };

    const onSuccess = () => {
        setShowMessage(true);
        if (propOnSuccess) {
            propOnSuccess();
        }
    }

    const form = useForm({
        submitter,
        defaultFormData: mergeDeep(emptyFormData, download),
        emptyFormData,
        clearOnSuccess: !propOnSuccess,
        onSuccess,
    });

    const localOnCancel = (e) => {
        if (e) e.preventDefault();
        if (onCancel) {
            onCancel();
        }
    }

    return <Form>
        <Header as='h3'><Icon name='file text' color='green'/> Archives</Header>
        <p>Create a Singlefile Archive for each of the URLs provided below.</p>

        <Grid stackable columns={1}>
            <Grid.Row>
                <Grid.Column>
                    <UrlsTextarea required form={form}/>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row>
                <Grid.Column>
                    <DownloadTagsSelector form={form}/>
                </Grid.Column>
            </Grid.Row>
            {showMessage && <SuccessfulDownloadSubmitMessage/>}
            <Grid.Row>
                <Grid.Column textAlign='right'>
                    {actions ? actions({onCancel: localOnCancel, form}) : <DownloadFormButtons onCancel={localOnCancel} form={form}/>}
                </Grid.Column>
            </Grid.Row>
        </Grid>
    </Form>
}

export function RSSDownloadForm({download, submitter, onDelete, onCancel, actions, clearOnSuccess = true}) {
    const [showMessage, setShowMessage] = React.useState(false);
    const [config, setConfig] = React.useState(null);
    const [isConfigLoaded, setIsConfigLoaded] = React.useState(false);
    const [userChangedResolutions, setUserChangedResolutions] = React.useState(false);

    const [defaultVideoFormat, setDefaultVideoFormat] = useLocalStorage('video_format', defaultVideoFormatOption);

    submitter = submitter || (async (formData) => {
        const downloadData = {
            destination: formData.destination,
            downloader: formData.downloader,
            frequency: formData.frequency,
            settings: formData.settings,
            sub_downloader: formData.sub_downloader,
            tag_names: formData.tag_names || [],
            urls: [formData.url],
        }
        await postDownload(downloadData);
    });

    // Use config video resolutions if available, otherwise use default
    const configResolutions = config && config.video_resolutions ? config.video_resolutions : defaultVideoResolutionOptions;

    const emptyFormData = {
        destination: null,
        downloader: Downloaders.RSS,
        frequency: weeklyOption.value,
        sub_downloader: null,
        settings: {
            excluded_urls: null,
            title_exclude: null,
            title_include: null,
            video_resolutions: configResolutions,
            video_format: defaultVideoFormat,
        },
        tag_names: [],
        url: '',
    };

    const form = useForm({
        submitter,
        defaultFormData: mergeDeep(emptyFormData, download),
        emptyFormData,
        clearOnSuccess,
        onSuccess: async () => setShowMessage(true),
    });

    // Fetch video downloader config when the modal opens
    React.useEffect(() => {
        const fetchConfig = async () => {
            try {
                const result = await fetchVideoDownloaderConfig();
                setConfig(result);
                setIsConfigLoaded(true);

                // Update form with video resolutions from config only if user hasn't changed them
                // and if no download object was provided (this is a new download, not an edit)
                if (result && result.video_resolutions && !userChangedResolutions && !download) {
                    form.setValue('settings.video_resolutions', result.video_resolutions);
                }
            } catch (error) {
                console.error('Failed to fetch video downloader config:', error);
                setIsConfigLoaded(true);
            }
        };

        fetchConfig();
    }, []);

    React.useEffect(() => {
        const {video_format} = form.formData.settings;
        if (video_format && video_format !== defaultVideoFormat) {
            setDefaultVideoFormat(video_format);
        }
    }, [form.formData]);

    // Default to "new" download buttons.
    actions = actions || DownloadFormButtons;
    const actionsElm = actions({onDelete, onCancel, form});

    let downloaderRows;
    if (form.formData.sub_downloader === Downloaders.Video) {
        downloaderRows = <>
            <Grid.Row columns={1}>
                <Grid.Column>
                    <DestinationForm
                        form={form}
                        helpContent="Videos download into their Channel's directory, by default.  If this is provided, then videos in this feed will download to this directory instead."
                    />
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={2}>
                <Grid.Column mobile={16} computer={8}>
                    <TitleInclusionInput form={form}/>
                </Grid.Column>
                <Grid.Column mobile={16} computer={8}>
                    <TitleExclusionInput form={form}/>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={2}>
                <Grid.Column mobile={16} computer={11}>
                    <VideoResolutionSelectorForm
                        form={form}
                        onChange={() => setUserChangedResolutions(true)}
                    />
                </Grid.Column>
                <Grid.Column mobile={8} computer={3}>
                    <VideoFormatSelectorForm form={form}/>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={2}>
                <Grid.Column tablet={8} computer={4}>
                    <VideoMinimumDurationForm form={form}/>
                </Grid.Column>
                <Grid.Column tablet={8} computer={4}>
                    <VideoMaximumDurationForm form={form}/>
                </Grid.Column>
            </Grid.Row>
        </>;
    } else if (form.formData.sub_downloader === Downloaders.Archive) {
        downloaderRows = <Grid.Row>
            <Grid.Column>
                <ExcludedUrls form={form}/>
            </Grid.Column>
        </Grid.Row>;
    }

    return <Form>
        <Header as='h3'><Icon name='rss' color='orange'/> RSS Feed</Header>
        <p>Download each link provided by this RSS feed using the selected downloader.</p>

        <Grid columns={1}>
            <Grid.Row>
                <Grid.Column>
                    <UrlInput required form={form}/>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row>
                <Grid.Column>
                    <DownloadTagsSelector form={form}/>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={2}>
                <Grid.Column width={8}>
                    <DownloadFrequencySelector form={form} freqOptions={extendedFrequencyOptions}/>
                </Grid.Column>
                <Grid.Column width={8}>
                    <DownloaderSelector form={form}/>
                </Grid.Column>
            </Grid.Row>
            {downloaderRows}
            {showMessage && <SuccessfulDownloadSubmitMessage/>}
            <Grid.Row>
                <Grid.Column textAlign='right'>
                    {actionsElm}
                </Grid.Column>
            </Grid.Row>
        </Grid>
    </Form>
}

export function EditRSSDownloadForm({download, onDelete, onCancel, actions = EditDownloadFormButtons}) {

    const submitter = async (formData) => {
        const downloadData = {
            destination: formData.destination,
            downloader: formData.downloader,
            frequency: formData.frequency,
            settings: formData.settings,
            sub_downloader: formData.sub_downloader,
            tag_names: formData.tag_names || [],
            urls: [formData.url,],
        }
        await putDownload(download.id, downloadData);
    }

    return <RSSDownloadForm
        submitter={submitter}
        onDelete={onDelete}
        onCancel={onCancel}
        download={download}
        actions={actions}
        clearOnSuccess={false}
    />
}

export function EditZimDownloadForm({download, onDelete, onCancel, actions = EditDownloadFormButtons}) {

    const submitter = async (formData) => {
        const downloadData = {
            downloader: formData.downloader,
            frequency: formData.frequency,
            settings: formData.settings,
            sub_downloader: formData.sub_downloader,
            tag_names: formData.tag_names,
            urls: [formData.url,],
        }
        await putDownload(download.id, downloadData);
    }
    const [showMessage, setShowMessage] = React.useState(false);

    const emptyFormData = {
        downloader: Downloaders.RSS,
        frequency: weeklyOption.value,
        sub_downloader: null,
        tag_names: [],
        url: '',
    };

    const form = useForm({
        submitter,
        defaultFormData: mergeDeep(emptyFormData, download),
        emptyFormData,
        onSuccess: async () => setShowMessage(true),
    });

    // Default to "new" download buttons.
    actions = actions || DownloadFormButtons;
    const actionsElm = actions({onDelete, onCancel, form});

    return <Form>
        <Header as='h3'>Zim File</Header>

        <Grid stackable columns={1}>
            <Grid.Row>
                <Grid.Column>
                    <UrlInput required form={form} disabled={true}/>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={2}>
                <Grid.Column width={8}>
                    <DownloadFrequencySelector form={form} longFrequenciesAvailable={true}/>
                </Grid.Column>
            </Grid.Row>
            {showMessage && <SuccessfulDownloadSubmitMessage/>}
            <Grid.Row>
                <Grid.Column textAlign='right'>
                    {actionsElm}
                </Grid.Column>
            </Grid.Row>
        </Grid>
    </Form>
}

export function FilesDownloadForm({
                                      download,
                                      submitter,
                                      onCancel,
                                      actions = DownloadFormButtons,
                                      clearOnSuccess = true,
                                  }) {
    const [showMessage, setShowMessage] = React.useState(false);

    submitter = submitter || (async (formData) => {
        const downloadData = {
            downloader: Downloaders.File,
            tag_names: formData.tag_names,
            destination: formData.destination,
            urls: formData.urls.split(/\r?\n/),
        }
        await postDownload(downloadData);
    });

    const emptyFormData = {
        destination: null,
        tag_names: [],
        urls: '',
    };

    const form = useForm({
        submitter,
        defaultFormData: mergeDeep(emptyFormData, download),
        emptyFormData,
        clearOnSuccess,
        onSuccess: async () => setShowMessage(true),
    });

    const actionsElm = actions({onCancel, form});

    return <Form>
        <Header as='h3'><Icon name='file'/> Files</Header>
        <p>Download each file at the URLs provided below.</p>

        <Grid>
            <Grid.Row>
                <Grid.Column>
                    <UrlsTextarea form={form}/>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row>
                <Grid.Column>
                    <DownloadTagsSelector form={form}/>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row>
                <Grid.Column>
                    <DestinationForm required form={form}/>
                </Grid.Column>
            </Grid.Row>
            {showMessage && <SuccessfulDownloadSubmitMessage/>}
            <Grid.Row>
                <Grid.Column textAlign='right'>
                    {actionsElm}
                </Grid.Column>
            </Grid.Row>
        </Grid>
    </Form>
}

const suffixValidator = (value) => {
    const error = commaSeparatedValidator(value);
    if (error) {
        return error;
    }

    const suffixes = value.split(',');
    for (const suffix of suffixes) {
        if (!suffix.startsWith('.')) {
            return 'Suffix must start with .';
        }
        if (suffix.length === 1) {
            return 'Suffix must have characters after .';
        }
    }
}

export function SuffixFormInput({form, name = 'suffix', path = 'settings.suffix'}) {
    return <InputForm
        form={form}
        label='File Suffixes'
        helpContent='Comma-separated list of file suffixes that should be downloaded'
        required={true}
        placeholder='.pdf,.mp4'
        name={name}
        path={path}
        validator={suffixValidator}
    />
}

export function ScrapeFilesDownloadForm({
                                            download,
                                            submitter,
                                            clearOnSuccess,
                                            onDelete,
                                            onCancel,
                                            onSuccess,
                                            actions = DownloadFormButtons,
                                            singleDownload = false,
                                        }) {
    const [showMessage, setShowMessage] = React.useState(false);

    submitter = submitter || (async (formData) => {
        const downloadData = {
            downloader: Downloaders.ScrapeHtml,
            sub_downloader: Downloaders.File,
            tag_names: formData.tag_names || [],
            destination: formData.destination,
            urls: formData.urls.split(/\r?\n/),
            settings: formData.settings,
        }
        await postDownload(downloadData);
    });

    const emptyFormData = {
        destination: null,
        tag_names: [],
        urls: '',
        settings: {
            depth: 1,
            max_pages: 1,
            suffix: '',
        }
    };

    const localOnSuccess = async () => {
        setShowMessage(true);
        if (onSuccess) {
            onSuccess();
        }
    }

    const form = useForm({
        submitter,
        defaultFormData: mergeDeep(emptyFormData, download),
        emptyFormData,
        clearOnSuccess,
        onSuccess: localOnSuccess,
    });

    const urlInput = singleDownload ?
        <UrlInput required form={form} path='url'/>
        : <UrlsTextarea required form={form}/>;

    // Default to "new" download buttons.
    actions = actions || DownloadFormButtons;
    const actionsElm = actions({onDelete, onCancel, form});

    return <Form>
        <Header as='h3'><Icon name='file alternate' color='red'/> Scrape Files</Header>
        <p>Search each of the URLs for files matching the suffix (.pdf, etc.).</p>

        <Grid>
            <Grid.Row>
                <Grid.Column>
                    {urlInput}
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={2}>
                <Grid.Column width={10}>
                    <DestinationForm required={true} form={form}/>
                </Grid.Column>
                <Grid.Column width={6}>
                    <SuffixFormInput required={true} form={form}/>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={2}>
                <Grid.Column width={4}>
                    <DepthInputForm form={form} required={true}/>
                </Grid.Column>
                <Grid.Column width={4}>
                    <MaximumPagesInputForm form={form} required={true}/>
                </Grid.Column>
            </Grid.Row>
            {showMessage && <SuccessfulDownloadSubmitMessage/>}
            <Grid.Row>
                <Grid.Column>
                    {actionsElm}
                </Grid.Column>
            </Grid.Row>
        </Grid>
    </Form>
}

export function EditScrapeFilesDownloadForm({download, onDelete, onCancel, onSuccess}) {
    const submitter = async (formData) => {
        const downloadData = {
            downloader: Downloaders.ScrapeHtml,
            sub_downloader: Downloaders.File,
            tag_names: formData.tag_names || [],
            destination: formData.destination,
            urls: [formData.url],
            settings: formData.settings,
        }
        await postDownload(downloadData);
    };

    return <ScrapeFilesDownloadForm
        download={download}
        submitter={submitter}
        onDelete={onDelete}
        onCancel={onCancel}
        onSuccess={onSuccess}
        actions={EditDownloadFormButtons}
        singleDownload={true}
    />
}

export function DownloadMenu({onOpen, disabled}) {
    const [downloader, setDownloader] = useState();

    const localOnOpen = (name) => {
        setDownloader(name);
        if (onOpen) {
            onOpen(name);
        }
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
            content='Archives'
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
        <Button
            color='black'
            content='Files'
            disabled={disabled}
            onClick={() => localOnOpen('file')}
            style={{marginBottom: '1em'}}
        />
        <Button
            color='red'
            content='Scrape'
            disabled={disabled}
            onClick={() => localOnOpen('scrape')}
            style={{marginBottom: '1em'}}
        />
    </>);

    function clearSelected() {
        localOnOpen(null);
        body = null;
    }

    const downloaders = {
        archive: <ArchiveDownloadForm onCancel={clearSelected}/>,
        video: <VideosDownloadForm singleDownload={false} onCancel={clearSelected}/>,
        video_channel: <ChannelDownloadForm onCancel={clearSelected}/>,
        rss: <RSSDownloadForm onCancel={clearSelected}/>,
        file: <FilesDownloadForm onCancel={clearSelected}/>,
        scrape: <ScrapeFilesDownloadForm onCancel={clearSelected}/>
    };

    if (downloader in downloaders) {
        const downloaderForm = downloaders[downloader];
        body = <>
            {downloaderForm}
        </>
    }

    return <>
        {body}
    </>
}
