import React, {useState} from "react";
import {fetchVideoDownloadDefaults, getDownloaders, postDownload, putDownload} from "../api";
import {
    APIButton,
    DirectorySearch,
    InfoHeader,
    InfoPopup,
    mergeDeep,
    RequiredAsterisk,
    SimpleAccordion,
    Toggle,
    useLocalStorage,
    validURL,
    validURLs,
} from "./Common";
import {Button, Group, Header, Icon, Message, MultiSelect, NumberInput, Select, Stack, TextInput, Textarea} from "./ui";
import {Link} from "react-router";
import {TagsSelector} from "../Tags";
import {
    commaSeparatedValidator,
    useForm,
} from "../hooks/useForm";
import {
    channelFrequencyOptions,
    days30Option,
    defaultAudioFormatOption,
    defaultVideoFormatOption,
    defaultVideoResolutionOptions,
    downloadAudioFormatOptions,
    Downloaders,
    downloadFormatOptions,
    downloadOrderOptions,
    downloadResolutionOptions,
    extendedFrequencyOptions,
    frequencyOptions,
    weeklyOption
} from "./Vars";

/*
 * Download.js was built around Semantic UI's <Form> family (Form.Input,
 * FormDropdown, TextArea) via `hooks/useForm.js`'s JSX helpers (InputForm,
 * NumberInputForm, ToggleForm, UrlInput, UrlsTextarea).  `hooks/useForm.js` is
 * off-limits for this migration and its JSX helpers still render through
 * `./Theme` (Semantic UI).  Rather than use those helpers, the field
 * components below call `useForm`'s plain data getters (getInputProps,
 * getSelectionProps, getCustomProps) directly and render our own markup with
 * the token-driven `./ui` library.  See the migration report for what this
 * leaves out of scope (hooks/useForm.js itself is unmigrated).
 */

function FieldLabel({htmlFor, label, required, helpContent, helpPosition = 'top'}) {
    if (!label) return null;
    return <label htmlFor={htmlFor} style={{display: 'block', marginBottom: 4}}>
        <b>{label} {required && <RequiredAsterisk/>}</b>
        {helpContent && <InfoPopup content={helpContent} position={helpPosition}/>}
    </label>
}

/** Text field backed by `form.getInputProps`.  TextInput passes a DOM event, which is exactly
 *  what `handleInputEvent` (inside useForm) expects, so the props can be spread through. */
function TextField({
                        form, name, path, type = 'text', validator, required = false,
                        placeholder = '', label, helpContent, helpPosition, disabled = false,
                    }) {
    const [inputProps] = form.getInputProps({name, path, validator, type, required});
    return <div>
        <FieldLabel htmlFor={`${name}_input`} label={label} required={required}
                    helpContent={helpContent} helpPosition={helpPosition}/>
        <TextInput
            id={`${name}_input`}
            name={name}
            type={inputProps.type}
            placeholder={placeholder}
            value={inputProps.value ?? ''}
            onChange={inputProps.onChange}
            disabled={disabled || inputProps.disabled}
            error={inputProps.error}
            data-path={inputProps['data-path']}
        />
    </div>
}

/** Number field.  Mantine's NumberInput hands back the value itself, not an event, so it is
 *  wrapped into the event shape `handleInputEvent` expects. */
function NumberField({
                         form, name, path, validator, required = false, placeholder = '',
                         label, helpContent, helpPosition, min = 1, max = 9999999999,
                     }) {
    validator = validator || ((value) => {
        value = typeof value === 'number' ? value : parseFloat(value);
        if (value < 0) {
            return 'Number must be positive';
        }
    });
    const [inputProps] = form.getInputProps({name, path, validator, type: 'number', required});
    const dataPath = inputProps['data-path'];
    return <div>
        <FieldLabel htmlFor={`${name}_input`} label={label} required={required}
                    helpContent={helpContent} helpPosition={helpPosition}/>
        <NumberInput
            id={`${name}_input`}
            placeholder={placeholder}
            min={min}
            max={max}
            value={inputProps.value ?? ''}
            onChange={(value) => inputProps.onChange({target: {value, type: 'number', dataset: {path: dataPath}}})}
            disabled={inputProps.disabled}
            error={inputProps.error}
        />
    </div>
}

/** A single-select field.  `options` are Semantic-shaped ({key, text, value}); Mantine's Select
 *  requires string data values, so values are stringified for display and mapped back on change. */
function SelectField({form, name, path, label, options, required = false, placeholder, disabled = false, afterChange}) {
    const [inputProps] = form.getSelectionProps({name, path, required, afterChange});
    const data = options.map(o => ({value: String(o.value), label: o.text}));
    const stringValue = (inputProps.value === null || inputProps.value === undefined) ? null : String(inputProps.value);

    const handleChange = (val) => {
        if (val === null || val === undefined) {
            inputProps.onChange(null, {value: null});
            return;
        }
        const match = options.find(o => String(o.value) === val);
        inputProps.onChange(null, {value: match ? match.value : val});
    };

    return <div>
        <FieldLabel htmlFor={`${name}_select`} label={label} required={required}/>
        <Select
            id={`${name}_select`}
            data={data}
            value={stringValue}
            onChange={handleChange}
            placeholder={placeholder}
            disabled={disabled || inputProps.disabled}
            error={inputProps.error}
        />
    </div>
}

/** A multi-select field (Video Resolutions). */
function MultiSelectField({form, name, path, options, onChange: afterChange}) {
    const [inputProps] = form.getSelectionProps({name, path, type: 'array', afterChange});
    const data = options.map(o => ({value: String(o.value), label: o.text}));
    const values = (inputProps.value || []).map(String);

    const handleChange = (vals) => {
        const mapped = vals.map(v => {
            const match = options.find(o => String(o.value) === v);
            return match ? match.value : v;
        });
        inputProps.onChange(null, {value: mapped});
    };

    return <MultiSelect
        data={data}
        value={values}
        onChange={handleChange}
        error={inputProps.error}
    />
}

export function DepthInputForm({form, required, name = 'depth', path = 'settings.depth'}) {
    return <NumberField
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
    return <NumberField
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
    const [inputProps] = form.getCustomProps({name, path, required});
    const {disabled, value, onChange} = inputProps;
    const infoPopup = infoContent ? <InfoPopup content={infoContent}/> : null;
    return <div>
        <FieldLabel htmlFor='destination_search_form' label={label} required={required}/>
        {infoPopup}
        <DirectorySearch
            required={required}
            value={value}
            onSelect={onChange}
            disabled={disabled}
            id='destination_search_form'
        />
    </div>
}

export function DownloadTagsSelector({form, limit, path = 'tag_names', name = 'tag_names'}) {
    const [inputProps] = form.getCustomProps({name, path});
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
    return <SelectField
        form={form}
        name={name}
        path={path}
        required
        label='Download Frequency'
        placeholder='Frequency'
        options={freqOptions}
    />
}

export function DownloaderSelector({form, name = 'sub_downloader', path = 'sub_downloader'}) {
    const [downloaders, setDownloaders] = React.useState([]);

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

    return <SelectField
        form={form}
        name={name}
        path={path}
        required
        label='Downloader'
        placeholder='Select a downloader'
        options={downloaders}
    />
}

export function ExcludedUrls({form, name = 'excluded_urls', path = 'settings.excluded_urls'}) {
    return <TextField
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
    return <TextField
        form={form}
        name='title_include'
        path={path}
        label='Title Match Words'
        helpContent='List of words, separated by commas, that titles must contain to be downloaded.'
        placeholder='Shelter,Solar Power'
        validator={commaSeparatedValidator}
    />
}

export function TitleExclusionInput({form, path = 'settings.title_exclude'}) {
    return <TextField
        form={form}
        name='title_exclude'
        path={path}
        label='Title Exclusion Words'
        helpContent='List of words, separated by commas, that may not appear in titles to be downloaded.'
        placeholder='Giveaway,Prize'
        validator={commaSeparatedValidator}
    />
}

export function DownloadFormButtons({onCancel, form}) {
    return <Group justify='space-between' mt='sm'>
        <Button role='cancel' onClick={onCancel} type='button'>Cancel</Button>
        <APIButton
            role='primary'
            disabled={form.disabled || !form.ready}
            type='submit'
            onClick={form.onSubmit}
            id='download_form_download_button'
        >Download</APIButton>
    </Group>
}

export function EditDownloadFormButtons({onDelete, onCancel, form}) {
    return <Group justify='space-between' mt='sm'>
        <APIButton
            role='danger'
            confirmButton='Delete'
            confirmContent='Delete this Download?'
            confirmHeader='Delete'
            onClick={onDelete}
        >Delete</APIButton>
        <Group>
            <Button role='cancel' onClick={onCancel}>Cancel</Button>
            <APIButton
                role='save'
                disabled={form.disabled || !form.ready}
                type='submit'
                onClick={form.onSubmit}
            >Save</APIButton>
        </Group>
    </Group>
}

function VideoDownloadOrder({form, path = 'settings.download_order'}) {
    return <SelectField
        form={form}
        name='download_order'
        path={path}
        label='Download Order'
        options={downloadOrderOptions}
    />
}

function VideoDownloadCountLimit({form, name = 'video_count_limit', path = 'settings.video_count_limit'}) {
    return <NumberField
        form={form}
        helpContent='Stop downloading videos from this channel/playlist when this many have been downloaded.'
        helpPosition='top right'
        name={name}
        path={path}
        label='Video Count Limit'
        placeholder='100'
    />
}

export function VideoResolutionSelectorForm({
                                                form,
                                                name = 'video_resolutions',
                                                path = 'settings.video_resolutions',
                                                onChange
                                            }) {
    return <div>
        <InfoHeader
            headerSize='h5'
            headerContent='Video Resolutions'
            popupContent='Videos will be downloaded in the first available resolution from the list you select.'
            for_='video_resolutions_input'
        />
        <MultiSelectField
            form={form}
            name={name}
            path={path}
            options={downloadResolutionOptions}
            onChange={onChange}
        />
    </div>
}

export function VideoFormatSelectorForm({form, name = 'video_format', path = 'settings.video_format'}) {
    return <div>
        <InfoHeader
            headerSize='h5'
            headerContent='Video Format'
            popupContent='Videos will be downloaded in this format, or transcoded if not available.'
            for_='video_format_input'
        />
        <SelectField form={form} name={name} path={path} options={downloadFormatOptions}/>
    </div>
}

export function AudioOnlyToggle({form, onChange}) {
    const [inputProps] = form.getCustomProps({name: 'audio_only', path: 'settings.audio_only'});
    return <Toggle
        label='Audio only'
        checked={!!inputProps.value}
        disabled={form.disabled}
        onChange={(value) => {
            inputProps.onChange(value);
            if (onChange) onChange(value);
        }}
        info='Download only the audio track from videos.'
    />
}

export function AudioFormatSelectorForm({form, name = 'audio_format', path = 'settings.audio_format'}) {
    return <div>
        <InfoHeader
            headerSize='h5'
            headerContent='Audio Format'
            popupContent='Audio will be downloaded and converted to this format.'
            for_='audio_format_input'
        />
        <SelectField form={form} name={name} path={path} options={downloadAudioFormatOptions}/>
    </div>
}

function VideoDurationLimit({form, name, path, label, helpContent, placeholder, helpPosition}) {
    return <NumberField
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
    return <div>
        <InfoHeader
            headerSize='h4'
            headerContent='Videos Tags'
            popupContent='Tag all Videos with these Tags.'
        />
        <DownloadTagsSelector form={form}/>
    </div>
}

export function ChannelTagNameForm({form}) {
    return <div>
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
    </div>
}

function AdvancedVideoSettings({form, isVideoLevel = false, isConfigLoaded = true}) {
    if (!isConfigLoaded) return null;

    return <SimpleAccordion title='Advanced Settings'>
        <Stack gap='md'>
            <Group grow align='flex-start' wrap='wrap'>
                <AudioOnlyToggleLikeVideoSetting form={form} name='writesubtitles' path='settings.writesubtitles'
                                                 label='Download subtitles' icon='closed captioning'/>
                <AudioOnlyToggleLikeVideoSetting form={form} name='writeautomaticsub' path='settings.writeautomaticsub'
                                                 label='Download automatic subtitles' icon='closed captioning'/>
            </Group>
            <Group grow align='flex-start' wrap='wrap'>
                <AudioOnlyToggleLikeVideoSetting form={form} name='writethumbnail' path='settings.writethumbnail'
                                                 label='Download thumbnail' icon='image'/>
                <AudioOnlyToggleLikeVideoSetting form={form} name='writeinfojson' path='settings.writeinfojson'
                                                 label='Download info JSON' icon='file code'/>
            </Group>
            {isVideoLevel &&
                <Group grow align='flex-start' wrap='wrap'>
                    <AudioOnlyToggleLikeVideoSetting form={form} name='continue_dl' path='settings.continue_dl'
                                                     label='Continue partial downloads' icon='play'/>
                    <AudioOnlyToggleLikeVideoSetting form={form} name='nooverwrites' path='settings.nooverwrites'
                                                     label='Do not overwrite existing files' icon='file video'/>
                </Group>}
            <Group grow align='flex-start' wrap='wrap'>
                <NumberField
                    form={form}
                    label='Sleep between requests (seconds)'
                    name='sleep_requests'
                    path='settings.sleep_requests'
                    placeholder='0.75'
                    min={0}
                    max={60}
                />
                <TextField
                    form={form}
                    label='User agent'
                    name='user_agent'
                    path='settings.user_agent'
                    placeholder='Mozilla/5.0...'
                />
            </Group>
            <TextField
                form={form}
                label='Extra yt-dlp arguments'
                name='yt_dlp_extra_args'
                path='settings.yt_dlp_extra_args'
                placeholder='--no-playlist --geo-bypass'
            />
        </Stack>
    </SimpleAccordion>
}

/** A labeled Toggle backed by `form.getCustomProps`. */
function AudioOnlyToggleLikeVideoSetting({form, name, path, label, icon}) {
    const [inputProps] = form.getCustomProps({name, path});
    return <Toggle
        label={label}
        icon={icon}
        checked={!!inputProps.value}
        disabled={form.disabled}
        onChange={inputProps.onChange}
    />
}

export function CompressSinglefileToggle({form}) {
    const [inputProps] = form.getCustomProps({name: 'compress_singlefile', path: 'settings.compress_singlefile'});
    return <div>
        <InfoHeader
            headerSize='h4'
            headerContent='Compress'
            popupContent='Create a compressed, self-extracting (SingleFileZ) archive.  The HTML file is smaller, but not
             human-readable.  Readability files are never compressed.'
        />
        <Toggle checked={!!inputProps.value} disabled={form.disabled} onChange={inputProps.onChange}/>
    </div>
}

function AdvancedDownloadSettings({form}) {
    const [inputProps] = form.getCustomProps({
        name: 'skip_already_downloaded',
        path: 'settings.skip_already_downloaded'
    });

    return <SimpleAccordion title='Advanced Settings'>
        <Toggle
            label='Skip URLs already downloaded'
            checked={!!inputProps.value}
            disabled={form.disabled}
            onChange={inputProps.onChange}
        />
    </SimpleAccordion>
}

export function VideosDownloadForm({
                                       singleDownload = true,
                                       onCancel,
                                       onSuccess: propOnSuccess,
                                       download,
                                       submitter: propSubmitter,
                                       actions
                                   }) {
    const [showMessage, setShowMessage] = React.useState(false);
    const [userChangedResolutions, setUserChangedResolutions] = React.useState(false);
    const [config, setConfig] = React.useState(null);
    const [isConfigLoaded, setIsConfigLoaded] = React.useState(false);

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
            video_format: defaultVideoFormat,
            video_resolutions: configResolutions,
            audio_only: false,
            audio_format: defaultAudioFormatOption,
            writesubtitles: false,
            writeautomaticsub: false,
            writethumbnail: false,
            writeinfojson: false,
            yt_dlp_extra_args: '',
            sleep_requests: null,
            user_agent: '',
            continue_dl: false,
            nooverwrites: false,
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

    // Fetch global defaults to pre-fill the form
    React.useEffect(() => {
        const fetchDefaults = async () => {
            try {
                const defaults = await fetchVideoDownloadDefaults();
                setConfig(defaults);

                if (defaults && download) {
                    // Edit mode: only fill settings not already in the download
                    for (const [key, value] of Object.entries(defaults)) {
                        if (download.settings?.[key] === undefined || download.settings?.[key] === null) {
                            form.setValue(`settings.${key}`, value);
                        }
                    }
                } else if (defaults) {
                    // New download: pre-fill all settings from global defaults
                    const downloadHasResolutions = download?.settings?.video_resolutions?.length > 0;
                    for (const [key, value] of Object.entries(defaults)) {
                        if (key === 'video_resolutions' && (userChangedResolutions || downloadHasResolutions)) {
                            continue;
                        }
                        if (key === 'video_format') {
                            continue; // Handled by localStorage default
                        }
                        form.setValue(`settings.${key}`, value);
                    }
                    if (!userChangedResolutions && !downloadHasResolutions && defaults.video_resolutions) {
                        form.setValue('settings.video_resolutions', defaults.video_resolutions);
                    }
                }
            } catch (error) {
                console.error('Failed to fetch video download defaults:', error);
            }
            setIsConfigLoaded(true);
        };

        fetchDefaults();
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
        <UrlField required form={form} path='urls'/>
        : <UrlsField required form={form}/>;

    return <form onSubmit={(e) => e.preventDefault()}>
        <Header as='h3' icon='film'>Videos</Header>
        <p>Download each video at the URLs provided below.</p>

        <Stack gap='md'>
            {urlInput}
            <VideoTagsForm form={form}/>
            <DestinationForm
                form={form}
                infoContent="Videos download into their Channel's directory, by default.  If this is provided, then videos in this Channel/Playlist will download to this directory instead."
            />
            <AudioOnlyToggle form={form}/>
            {form.formData?.settings?.audio_only
                ? <AudioFormatSelectorForm form={form}/>
                : <Group align='flex-start' wrap='wrap'>
                    <div style={{flex: 3, minWidth: 240}}>
                        <VideoResolutionSelectorForm
                            form={form}
                            onChange={() => setUserChangedResolutions(true)}
                        />
                    </div>
                    <div style={{flex: 1, minWidth: 140}}>
                        <VideoFormatSelectorForm form={form}/>
                    </div>
                </Group>
            }
            <ChannelTagNameForm form={form}/>
            <AdvancedVideoSettings form={form} isVideoLevel={true} isConfigLoaded={isConfigLoaded}/>
            {showMessage && <SuccessfulDownloadSubmitMessage/>}
            {actions ? actions({onCancel: localOnCancel, form}) :
                <DownloadFormButtons onCancel={localOnCancel} form={form}/>}
        </Stack>
    </form>
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
            collection_id: download.collection_id,
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
            video_count_limit: null,
            video_format: defaultVideoFormat,
            video_resolutions: configResolutions,
            audio_only: false,
            audio_format: defaultAudioFormatOption,
            writesubtitles: false,
            writeautomaticsub: false,
            writethumbnail: false,
            writeinfojson: false,
            yt_dlp_extra_args: '',
            sleep_requests: null,
            user_agent: '',
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

    // Fetch global defaults to pre-fill the form
    React.useEffect(() => {
        const fetchDefaults = async () => {
            try {
                const defaults = await fetchVideoDownloadDefaults();
                setConfig(defaults);
                setIsConfigLoaded(true);

                if (defaults && download) {
                    // Edit mode: only fill settings not already in the download
                    for (const [key, value] of Object.entries(defaults)) {
                        if (key === 'continue_dl' || key === 'nooverwrites') continue;
                        if (download.settings?.[key] === undefined || download.settings?.[key] === null) {
                            form.setValue(`settings.${key}`, value);
                        }
                    }
                } else if (defaults) {
                    // New download: pre-fill all inheritable settings from global defaults
                    const downloadHasResolutions = download?.settings?.video_resolutions?.length > 0;
                    for (const [key, value] of Object.entries(defaults)) {
                        if (key === 'continue_dl' || key === 'nooverwrites') continue;
                        if (key === 'video_resolutions' && (userChangedResolutions || downloadHasResolutions)) continue;
                        if (key === 'video_format') continue;
                        form.setValue(`settings.${key}`, value);
                    }
                    if (!userChangedResolutions && !downloadHasResolutions && defaults.video_resolutions) {
                        form.setValue('settings.video_resolutions', defaults.video_resolutions);
                    }
                }
            } catch (error) {
                console.error('Failed to fetch video download defaults:', error);
                setIsConfigLoaded(true);
            }
        };

        fetchDefaults();
    }, []);

    React.useEffect(() => {
        const {video_format} = form.formData.settings;
        if (video_format && video_format !== defaultVideoFormat) {
            setDefaultVideoFormat(video_format);
        }
    }, [form.formData]);

    const onceMessage = <Message kind='info' title='Download Once'>
        You have selected a frequency of Once, this is useful when you want to download
        all videos in a Playlist, and when you do not want to download any videos added to the playlist
        in the future.
    </Message>;

    // Default to "new" download buttons.
    actions = actions || DownloadFormButtons;
    const actionsElm = actions({onDelete, onCancel, form});

    return <form onSubmit={(e) => e.preventDefault()}>
        <Header as='h3' icon='film'>Channel / Playlist</Header>

        <Stack gap='md'>
            <UrlField required form={form}/>
            <VideoTagsForm form={form}/>
            <Group align='flex-start' wrap='wrap'>
                <div style={{flex: 1, minWidth: 200}}>
                    <DownloadFrequencySelector form={form} freqOptions={channelFrequencyOptions}/>
                </div>
                <div style={{flex: 3, minWidth: 240}}>
                    <DestinationForm
                        form={form}
                        infoContent='Destination is not required.  Videos will download into the automatically created Channel directory.'
                    />
                </div>
            </Group>
            {form.formData.frequency === 0 && onceMessage}
            <Group grow align='flex-start' wrap='wrap'>
                <TitleInclusionInput form={form}/>
                <TitleExclusionInput form={form}/>
            </Group>
            <Group grow align='flex-start' wrap='wrap'>
                <VideoDownloadOrder form={form}/>
                <VideoDownloadCountLimit form={form}/>
            </Group>
            <AudioOnlyToggle form={form}/>
            {form.formData?.settings?.audio_only
                ? <AudioFormatSelectorForm form={form}/>
                : <Group align='flex-start' wrap='wrap'>
                    <div style={{flex: 3, minWidth: 240}}>
                        <VideoResolutionSelectorForm
                            form={form}
                            onChange={() => setUserChangedResolutions(true)}
                        />
                    </div>
                    <div style={{flex: 1, minWidth: 140}}>
                        <VideoFormatSelectorForm form={form}/>
                    </div>
                </Group>
            }
            <Group grow align='flex-start' wrap='wrap'>
                <VideoMinimumDurationForm form={form}/>
                <VideoMaximumDurationForm form={form}/>
            </Group>
            <ChannelTagNameForm form={form}/>
            <AdvancedVideoSettings form={form} isConfigLoaded={isConfigLoaded}/>
            {showMessage && <SuccessfulDownloadSubmitMessage/>}
            {actionsElm}
        </Stack>
    </form>
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
            collection_id: download.collection_id,
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
    return <Message kind='success' title='Download Submitted'>
        <Link to='/admin'><Icon name='checkmark'/> View downloads</Link>
    </Message>
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
            collection_id: download.collection_id,
            downloader: formData.downloader,
            tag_names: formData.tag_names,
            urls: formData.urls.split(/\r?\n/),
        }
        await putDownload(download.id, downloadData);
    }

    return <ArchiveDownloadForm
        singleDownload={true}
        download={download}
        onCancel={onCancel}
        onSuccess={onSuccess}
        submitter={submitter}
        actions={(props) => actions({...props, onDelete})}
    />
}

export function ArchiveDownloadForm({
                                        singleDownload = false,
                                        download,
                                        onCancel,
                                        onSuccess: propOnSuccess,
                                        submitter: propSubmitter,
                                        actions
                                    }) {
    const [showMessage, setShowMessage] = React.useState(false);

    // Remember the user's compression choice between downloads.
    const [defaultCompressSinglefile, setDefaultCompressSinglefile] = useLocalStorage('compress_singlefile', false);

    const submitter = propSubmitter || (async (formData) => {
        const downloadData = {
            downloader: formData.downloader,
            tag_names: formData.tag_names,
            urls: formData.urls.split(/\r?\n/),
            settings: formData.settings,
        }
        await postDownload(downloadData);
    });

    const emptyFormData = {
        downloader: Downloaders.Archive,
        urls: '',
        tag_names: [],
        settings: {
            skip_already_downloaded: false,
            compress_singlefile: defaultCompressSinglefile,
        },
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

    // Persist the user's compression choice in local storage.
    React.useEffect(() => {
        const {compress_singlefile} = form.formData.settings;
        if (compress_singlefile !== undefined && compress_singlefile !== defaultCompressSinglefile) {
            setDefaultCompressSinglefile(compress_singlefile);
        }
    }, [form.formData, defaultCompressSinglefile]);

    const localOnCancel = (e) => {
        if (e) e.preventDefault();
        if (onCancel) {
            onCancel();
        }
    }

    const urlInput = singleDownload ?
        <UrlField required form={form} path='urls'/>
        : <UrlsField required form={form}/>;

    return <form onSubmit={(e) => e.preventDefault()}>
        <Header as='h3' icon='file text'>Archives</Header>
        <p>Create a Singlefile Archive for each of the URLs provided below.</p>

        <Stack gap='md'>
            {urlInput}
            <DownloadTagsSelector form={form}/>
            <CompressSinglefileToggle form={form}/>
            <AdvancedDownloadSettings form={form}/>
            {showMessage && <SuccessfulDownloadSubmitMessage/>}
            {actions ? actions({onCancel: localOnCancel, form}) :
                <DownloadFormButtons onCancel={localOnCancel} form={form}/>}
        </Stack>
    </form>
}

export function RSSDownloadForm({download, submitter, onDelete, onCancel, actions, clearOnSuccess = true}) {
    const [showMessage, setShowMessage] = React.useState(false);
    const [config, setConfig] = React.useState(null);
    const [isConfigLoaded, setIsConfigLoaded] = React.useState(false);
    const [userChangedResolutions, setUserChangedResolutions] = React.useState(false);

    const [defaultVideoFormat, setDefaultVideoFormat] = useLocalStorage('video_format', defaultVideoFormatOption);
    // Remember the user's compression choice between downloads.
    const [defaultCompressSinglefile, setDefaultCompressSinglefile] = useLocalStorage('compress_singlefile', false);

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
            compress_singlefile: defaultCompressSinglefile,
            excluded_urls: null,
            title_exclude: null,
            title_include: null,
            video_resolutions: configResolutions,
            video_format: defaultVideoFormat,
            audio_only: false,
            audio_format: defaultAudioFormatOption,
            writesubtitles: false,
            writeautomaticsub: false,
            writethumbnail: false,
            writeinfojson: false,
            yt_dlp_extra_args: '',
            sleep_requests: null,
            user_agent: '',
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

    // Fetch global defaults to pre-fill the form
    React.useEffect(() => {
        const fetchDefaults = async () => {
            try {
                const defaults = await fetchVideoDownloadDefaults();
                setConfig(defaults);
                setIsConfigLoaded(true);

                if (defaults && download) {
                    for (const [key, value] of Object.entries(defaults)) {
                        if (key === 'continue_dl' || key === 'nooverwrites') continue;
                        if (download.settings?.[key] === undefined || download.settings?.[key] === null) {
                            form.setValue(`settings.${key}`, value);
                        }
                    }
                } else if (defaults) {
                    const downloadHasResolutions = download?.settings?.video_resolutions?.length > 0;
                    for (const [key, value] of Object.entries(defaults)) {
                        if (key === 'continue_dl' || key === 'nooverwrites') continue;
                        if (key === 'video_resolutions' && (userChangedResolutions || downloadHasResolutions)) continue;
                        if (key === 'video_format') continue;
                        form.setValue(`settings.${key}`, value);
                    }
                    if (!userChangedResolutions && !downloadHasResolutions && defaults.video_resolutions) {
                        form.setValue('settings.video_resolutions', defaults.video_resolutions);
                    }
                }
            } catch (error) {
                console.error('Failed to fetch video download defaults:', error);
                setIsConfigLoaded(true);
            }
        };

        fetchDefaults();
    }, []);

    React.useEffect(() => {
        const {video_format} = form.formData.settings;
        if (video_format && video_format !== defaultVideoFormat) {
            setDefaultVideoFormat(video_format);
        }
    }, [form.formData]);

    // Persist the user's compression choice in local storage.
    React.useEffect(() => {
        const {compress_singlefile} = form.formData.settings;
        if (compress_singlefile !== undefined && compress_singlefile !== defaultCompressSinglefile) {
            setDefaultCompressSinglefile(compress_singlefile);
        }
    }, [form.formData, defaultCompressSinglefile]);

    // Default to "new" download buttons.
    actions = actions || DownloadFormButtons;
    const actionsElm = actions({onDelete, onCancel, form});

    let downloaderRows;
    if (form.formData.sub_downloader === Downloaders.Video) {
        downloaderRows = <>
            <DestinationForm
                form={form}
                infoContent="Videos download into their Channel's directory, by default.  If this is provided, then videos in this feed will download to this directory instead."
            />
            <Group grow align='flex-start' wrap='wrap'>
                <TitleInclusionInput form={form}/>
                <TitleExclusionInput form={form}/>
            </Group>
            <AudioOnlyToggle form={form}/>
            {form.formData?.settings?.audio_only
                ? <AudioFormatSelectorForm form={form}/>
                : <Group align='flex-start' wrap='wrap'>
                    <div style={{flex: 3, minWidth: 240}}>
                        <VideoResolutionSelectorForm
                            form={form}
                            onChange={() => setUserChangedResolutions(true)}
                        />
                    </div>
                    <div style={{flex: 1, minWidth: 140}}>
                        <VideoFormatSelectorForm form={form}/>
                    </div>
                </Group>
            }
            <Group grow align='flex-start' wrap='wrap'>
                <VideoMinimumDurationForm form={form}/>
                <VideoMaximumDurationForm form={form}/>
            </Group>
            <AdvancedVideoSettings form={form} isConfigLoaded={isConfigLoaded}/>
        </>;
    } else if (form.formData.sub_downloader === Downloaders.Archive) {
        downloaderRows = <>
            <ExcludedUrls form={form}/>
            <CompressSinglefileToggle form={form}/>
        </>;
    }

    return <form onSubmit={(e) => e.preventDefault()}>
        <Header as='h3' icon='rss'>RSS Feed</Header>
        <p>Download each link provided by this RSS feed using the selected downloader.</p>

        <Stack gap='md'>
            <UrlField required form={form}/>
            <DownloadTagsSelector form={form}/>
            <Group grow align='flex-start' wrap='wrap'>
                <DownloadFrequencySelector form={form} freqOptions={extendedFrequencyOptions}/>
                <DownloaderSelector form={form}/>
            </Group>
            {downloaderRows}
            {showMessage && <SuccessfulDownloadSubmitMessage/>}
            {actionsElm}
        </Stack>
    </form>
}

export function EditRSSDownloadForm({download, onDelete, onCancel, actions = EditDownloadFormButtons}) {

    const submitter = async (formData) => {
        const downloadData = {
            collection_id: download.collection_id,
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
            collection_id: download.collection_id,
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

    return <form onSubmit={(e) => e.preventDefault()}>
        <Header as='h3'>Zim File</Header>

        <Stack gap='md'>
            <UrlField required form={form} disabled={true}/>
            <DownloadFrequencySelector form={form} freqOptions={extendedFrequencyOptions}/>
            {showMessage && <SuccessfulDownloadSubmitMessage/>}
            {actionsElm}
        </Stack>
    </form>
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
            settings: formData.settings,
        }
        await postDownload(downloadData);
    });

    const emptyFormData = {
        destination: null,
        tag_names: [],
        urls: '',
        settings: {
            skip_already_downloaded: false,
        },
    };

    const form = useForm({
        submitter,
        defaultFormData: mergeDeep(emptyFormData, download),
        emptyFormData,
        clearOnSuccess,
        onSuccess: async () => setShowMessage(true),
    });

    const actionsElm = actions({onCancel, form});

    return <form onSubmit={(e) => e.preventDefault()}>
        <Header as='h3' icon='file'>Files</Header>
        <p>Download each file at the URLs provided below.</p>

        <Stack gap='md'>
            <UrlsField form={form}/>
            <DownloadTagsSelector form={form}/>
            <DestinationForm required form={form}/>
            <AdvancedDownloadSettings form={form}/>
            {showMessage && <SuccessfulDownloadSubmitMessage/>}
            {actionsElm}
        </Stack>
    </form>
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
    return <TextField
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
        <UrlField required form={form} path='url'/>
        : <UrlsField required form={form}/>;

    // Default to "new" download buttons.
    actions = actions || DownloadFormButtons;
    const actionsElm = actions({onDelete, onCancel, form});

    return <form onSubmit={(e) => e.preventDefault()}>
        <Header as='h3' icon='file alternate'>Scrape Files</Header>
        <p>Search each of the URLs for files matching the suffix (.pdf, etc.).</p>

        <Stack gap='md'>
            {urlInput}
            <Group align='flex-start' wrap='wrap'>
                <div style={{flex: 3, minWidth: 240}}>
                    <DestinationForm required={true} form={form}/>
                </div>
                <div style={{flex: 2, minWidth: 200}}>
                    <SuffixFormInput required={true} form={form}/>
                </div>
            </Group>
            <Group grow align='flex-start' wrap='wrap'>
                <DepthInputForm form={form} required={true}/>
                <MaximumPagesInputForm form={form} required={true}/>
            </Group>
            {showMessage && <SuccessfulDownloadSubmitMessage/>}
            {actionsElm}
        </Stack>
    </form>
}

export function EditScrapeFilesDownloadForm({download, onDelete, onCancel, onSuccess}) {
    const submitter = async (formData) => {
        const downloadData = {
            collection_id: download.collection_id,
            downloader: Downloaders.ScrapeHtml,
            sub_downloader: Downloaders.File,
            tag_names: formData.tag_names || [],
            destination: formData.destination,
            urls: [formData.url],
            settings: formData.settings,
        }
        await putDownload(download.id, downloadData);
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

/** URL field for a single URL (Semantic's `UrlInput`). */
function UrlField({form, required = true, name = 'url', path = 'url', disabled = false}) {
    const validator = (i) => validURL(i) ? null : 'Invalid URL';
    return <TextField
        form={form}
        type='url'
        label='URL'
        required={required}
        name={name}
        path={path}
        validator={validator}
        disabled={disabled}
    />
}

/** Multiline URLs field (Semantic's `UrlsTextarea`). */
function UrlsField({name = 'urls', required, form}) {
    required = required !== undefined;

    const validator = (value) => {
        if (!validURLs(value)) {
            return 'Invalid URLs';
        }
    };

    const [inputProps, inputAttrs] = form.getInputProps({name, validator, required});

    const handleDrop = (e) => {
        if (e) e.preventDefault();
        const droppedUrl = e.dataTransfer.getData('text');
        let urls = (inputProps.value || '').split('\n');
        urls = [...urls, droppedUrl];
        urls = urls.filter(i => !!i).join('\n');
        inputAttrs.localSetValue(`${urls}\n`);
    };

    const handleKeyDown = (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
            event.preventDefault();
            form.onSubmit();
        }
    };

    return <div>
        <FieldLabel htmlFor='urls_textarea' label='URLs' required={required}/>
        <Textarea
            id='urls_textarea'
            placeholder='Enter one URL per line'
            name='urls'
            minRows={4}
            autosize
            value={inputProps.value ?? ''}
            onChange={inputProps.onChange}
            onDrop={handleDrop}
            onKeyDown={handleKeyDown}
            error={inputProps.error}
            data-path={inputProps['data-path']}
        />
    </div>
}

export function DownloadMenu({onOpen, disabled, initialDownloader, initialUrls}) {
    // initialDownloader and initialUrls support the deep-link flow used by the
    // WROLPi browser extension's "Configure Download" button: visiting
    // `/?downloader=archive&download_url=...` pre-selects a form and pre-fills
    // its URLs textarea via DashboardPage.Getters.
    const [downloader, setDownloader] = useState(initialDownloader || undefined);

    const localOnOpen = (name) => {
        setDownloader(name);
        if (onOpen) {
            onOpen(name);
        }
    }

    let body = (<Stack gap='xs'>
        <Button color='blue' disabled={disabled} onClick={() => localOnOpen('video')}>Videos</Button>
        <Button color='green' disabled={disabled} onClick={() => localOnOpen('archive')}>Archives</Button>
        <Button color='blue' disabled={disabled} onClick={() => localOnOpen('video_channel')}>Channel/Playlist</Button>
        <Button disabled={disabled} onClick={() => localOnOpen('rss')}>RSS Feed</Button>
        <Button color='grey' disabled={disabled} onClick={() => localOnOpen('file')}>Files</Button>
        <Button role='danger' disabled={disabled} onClick={() => localOnOpen('scrape')}>Scrape</Button>
    </Stack>);

    function clearSelected() {
        localOnOpen(null);
        body = null;
    }

    // Synthesize a partial `download` prop that seeds the form's URL field(s).
    // Multi-URL forms read `urls` (newline-separated string); the single-URL
    // ChannelDownloadForm reads `url`. Setting both is harmless — each form's
    // emptyFormData defines which field actually exists.
    const seed = (initialUrls && initialUrls.length)
        ? {urls: initialUrls.join('\n'), url: initialUrls[0]}
        : undefined;

    const downloaders = {
        archive: <ArchiveDownloadForm onCancel={clearSelected} download={seed}/>,
        video: <VideosDownloadForm singleDownload={false} onCancel={clearSelected} download={seed}/>,
        video_channel: <ChannelDownloadForm onCancel={clearSelected} download={seed}/>,
        rss: <RSSDownloadForm onCancel={clearSelected} download={seed}/>,
        file: <FilesDownloadForm onCancel={clearSelected} download={seed}/>,
        scrape: <ScrapeFilesDownloadForm onCancel={clearSelected} download={seed}/>
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
