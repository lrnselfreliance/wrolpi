export const API_URI = process.env && process.env.REACT_APP_API_URI ? process.env.REACT_APP_API_URI : `https://${window.location.host}/api`;
export const VIDEOS_API = `${API_URI}/videos`;
export const ARCHIVES_API = `${API_URI}/archive`;
export const OTP_API = `${API_URI}/otp`;
export const ZIM_API = `${API_URI}/zim`;
export const DEFAULT_LIMIT = 20;
export const NAME = process.env && process.env.REACT_APP_NAME ? process.env.REACT_APP_NAME : null;

// Other services on a WROLPi.
const port = window.location.port ? `${window.location.port.replace(/^/, '')}` : '';
export const FILES_MEDIA_URI = `https://${window.location.hostname}:${port}/media/`;
export const MAP_VIEWER_URI = `https://${window.location.hostname}:8084`;
export const ZIM_VIEWER_URI = `https://${window.location.hostname}:8085`;
export const HELP_VIEWER_URI = `https://${window.location.hostname}:8086`;
export const API_ARCHIVE_UPLOAD_URI = `http://${window.location.hostname}:8081/api/archive/upload`;

export let defaultFileOrder = '-published_datetime'; // Most recently published files first.
export let defaultSearchOrder = 'rank'; // Most relevant files first.

// Download frequencies.
export const nullOption = {key: null, text: '', value: null};
export const onceOption = {key: 0, text: 'Once', value: 0};
export const hourlyOption = {key: 3600, text: 'Hourly', value: 3600};
export const threeHoursOption = {key: 10800, text: '3 hours', value: 10800};
export const twelveHoursOption = {key: 43200, text: '12 hours', value: 43200};
export const dailyOption = {key: 86400, text: 'Daily', value: 86400};
export const weeklyOption = {key: 604800, text: 'Weekly', value: 604800};
export const biweeklyOption = {key: 1209600, text: 'Biweekly', value: 1209600};
export const days30Option = {key: 2592000, text: '30 Days', value: 2592000};
export const days90Option = {key: 7776000, text: '90 Days', value: 7776000};
export const days180Option = {key: 15552000, text: '180 Days', value: 15552000};

export const frequencyOptions = [
    dailyOption,
    weeklyOption,
    biweeklyOption,
    days30Option,
    days90Option,
];

export const longFrequencyOptions = [
    dailyOption,
    weeklyOption,
    biweeklyOption,
    days30Option,
    days90Option,
    days180Option,
];

export const channelFrequencyOptions = [
    onceOption, // A Channel/Playlist can be downloaded once.
    ...longFrequencyOptions,
]

export const extendedFrequencyOptions = [
    onceOption,
    hourlyOption,
    threeHoursOption,
    twelveHoursOption,
    ...longFrequencyOptions,
];

export const allFrequencyOptions = {
    [nullOption.value]: nullOption,
    [onceOption.value]: onceOption,
    [hourlyOption.value]: hourlyOption,
    [threeHoursOption.value]: threeHoursOption,
    [twelveHoursOption.value]: twelveHoursOption,
    [dailyOption.value]: dailyOption,
    [weeklyOption.value]: weeklyOption,
    [biweeklyOption.value]: biweeklyOption,
    [days30Option.value]: days30Option,
    [days90Option.value]: days90Option,
    [days180Option.value]: days180Option,
};

export const semanticUIColorMap = {
    red: '#db2828',
    orange: '#f2711c',
    yellow: '#fbbd08',
    olive: '#b5cc18',
    green: '#21ba45',
    teal: '#00b5ad',
    blue: '#2185d0',
    violet: '#6435c9',
    purple: '#a333c8',
    pink: '#e03997',
    brown: '#a5673f',
    grey: '#767676',
}

export const validUrlRegex = /^(http|https):\/\/[^ "]+$/;

export const downloadOrderOptions = [
    {key: 'newest', text: 'Newest', value: 'newest'},
    {key: 'oldest', text: 'Oldest', value: 'oldest'},
    {key: 'views', text: 'Most Views', value: 'views'},
];

export const downloadResolutionOptions = [
    {key: '360p', text: '360p', value: '360p'},
    {key: '480p', text: '480p', value: '480p'},
    {key: '720p', text: '720p', value: '720p'},
    {key: '1080p', text: '1080p', value: '1080p'},
    {key: '1440p', text: '1440p', value: '1440p'},
    {key: '2160p', text: '2160p', value: '2160p'},
    {key: 'maximum', text: 'Maximum', value: 'maximum'},
]

export const defaultVideoResolutionOptions = ['1080p', '720p', '480p', 'maximum'];

export const downloadFormatOptions = [
    {key: 'mp4', text: '.mp4', value: 'mp4'},
    {key: 'mkv', text: '.mkv', value: 'mkv'},
]

export const defaultVideoFormatOption = 'mp4';

export const Downloaders = {
    Archive: 'archive',
    File: 'file',
    KiwixCatalog: 'kiwix_catalog',
    KiwixZim: 'kiwix_zim',
    RSS: 'rss',
    ScrapeHtml: 'scrape_html',
    Video: 'video',
    VideoChannel: 'video_channel',
};