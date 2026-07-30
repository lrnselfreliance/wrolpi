/**
 * Shared test fixtures: the data and context values the app expects, in one place.
 *
 * Two problems this exists to solve.
 *
 * The first is duplication.  A settings object was written out by hand in every spec that
 * needed one, twenty-odd keys at a time, so a spec asserting one field still had to know and
 * restate the other nineteen.  Nothing kept those copies in step with each other or with the
 * API, and adding a required field meant hunting them down.
 *
 * The second is drift, which is the worse of the two.  A fixture that no longer matches the
 * shape it stands in for makes a test *confidently* wrong: it passes while the component
 * would break in the browser.  The theme context fixture carried `i`, `s` and `t` with
 * hardcoded Semantic greys for months after ThemeProvider stopped supplying them, and one
 * component was still reading a prop that no longer existed.  test-fixtures.test.js compares
 * these against the real contexts so that class of drift fails a test rather than surviving.
 *
 * Everything here is a function taking overrides, never an exported constant: a shared mutable
 * object lets one test change what the next one sees, and that failure is miserable to find.
 *
 * Importable from jest tests, Cypress component specs, and e2e `cy.intercept` bodies alike --
 * the same fixture in all three, so they cannot disagree about what the API returns.
 */

import {defaultTheme} from './themes/names';

/* --------------------------------------------------------------------------- */
/* API shapes                                                                   */
/* --------------------------------------------------------------------------- */

/** GET /api/settings */
export const settingsFixture = (overrides = {}) => ({
    archive_destination: 'archive/%(domain_tag)s/%(domain)s',
    check_for_upgrades: true,
    download_manager_disabled: false,
    download_manager_stopped: false,
    download_on_startup: true,
    download_timeout: 0,
    download_wait: 20,
    download_window_start: null,
    download_window_end: null,
    hotspot_device: 'wlan0',
    hotspot_on_startup: true,
    hotspot_password: 'wrolpi hotspot',
    hotspot_ssid: 'WROLPi',
    ignore_outdated_zims: false,
    log_level: 'info',
    map_destination: 'map',
    // `/media/wrolpi` on a Pi, but the API is the authority on this and a test that
    // hardcodes it elsewhere is asserting its own guess.
    media_directory: '/media/wrolpi',
    nav_color: 'violet',
    playlists_destination: 'playlists',
    save_ffprobe_json: true,
    tags_directory: true,
    throttle_on_startup: false,
    version: '1.0.0',
    videos_destination: 'videos/%(channel_tag)s/%(channel_name)s',
    wrol_mode: false,
    zims_destination: 'zims',
    ...overrides,
});

/** GET /api/status */
export const statusFixture = (overrides = {}) => ({
    version: '1.0.0',
    flags: {},
    cpu_percent: 10,
    memory_percent: 30,
    downloads: {
        pending: 0,
        recurring: 0,
        disabled: false,
        stopped: false,
        outside_download_window: false,
    },
    ...overrides,
});

/** A Domain Collection, as the domains endpoints return it. */
export const domainFixture = (overrides = {}) => ({
    id: 1,
    domain: 'example.com',
    archive_count: 42,
    size: 1024000,
    tag_name: null,
    directory: '',
    can_be_tagged: false,
    description: '',
    ...overrides,
});

export const domainsFixture = (count = 3) => Array.from({length: count}, (_, i) => domainFixture({
    id: i + 1,
    domain: `example${i + 1}.com`,
    archive_count: (i + 1) * 10,
    size: (i + 1) * 1000000,
}));

export const tagFixture = (overrides = {}) => ({
    id: 1,
    name: 'Favorite',
    color: '#gray',
    file_group_count: 0,
    zim_entry_count: 0,
    channel_count: 0,
    domain_count: 0,
    ...overrides,
});

/* --------------------------------------------------------------------------- */
/* Context values                                                               */
/* --------------------------------------------------------------------------- */
/*
 * These are the values a provider carries, not mocks of a provider.  Passing one to the real
 * `Context.Provider` runs the real consumers against real data, which is why none of the
 * components using them need `jest.mock` -- see test-utils' render().
 */

export const themeContextFixture = (overrides = {}) => ({
    theme: defaultTheme,
    savedTheme: null,
    isDark: false,
    // Media filtering is off unless a test asks for it; the themes that offer a filter
    // decide their own default, and a fixture should not pre-empt that.
    mediaFilter: undefined,
    mediaFilterEnabled: false,
    setMediaFilterEnabled: () => {},
    setTheme: () => {},
    setDarkTheme: () => {},
    setLightTheme: () => {},
    cycleSavedTheme: () => {},
    ...overrides,
});

export const statusContextFixture = (overrides = {}) => ({
    status: statusFixture(),
    fetchStatus: () => Promise.resolve(),
    ...overrides,
});

export const settingsContextFixture = (overrides = {}) => ({
    settings: settingsFixture(),
    fetchSettings: () => Promise.resolve(),
    saveSettings: () => Promise.resolve(),
    pending: false,
    ...overrides,
});

export const queryContextFixture = (overrides = {}) => ({
    searchParams: new URLSearchParams(),
    setSearchParams: () => {},
    updateQuery: () => {},
    getLocationStr: () => '',
    ...overrides,
});

/**
 * The value `useTags` returns.
 *
 * The render helpers supply the real `TagsProvider` when a test does not pass tags, so this
 * is for the cases that need particular tags without an API round trip.  The component
 * members are rendered as plain text: a test asserting on tag chips wants to find the name,
 * not to re-test how Tags.js draws one.
 */
export const tagsContextFixture = (overrides = {}) => {
    const tags = overrides.tags ?? [];
    const findTagByName = (name) => tags.find(tag => tag.name === name);
    return {
        tags,
        tagNames: tags.map(tag => tag.name),
        NameToTagLabel: ({name}) => name ?? null,
        TagsGroup: ({tagNames: names}) => (names || []).join(', '),
        TagsLinkGroup: ({tagNames: names}) => (names || []).join(', '),
        fetchTags: () => Promise.resolve(),
        findTagByName,
        SingleTag: ({name}) => name ?? null,
        fuzzyMatchTagsByName: (name) => tags.filter(tag => tag.name.includes(name)),
        ...overrides,
    };
};

/** The value FileWorkerStatusContext carries; no file worker is running by default. */
export const fileWorkerStatusFixture = (overrides = {}) => ({
    status: null,
    error: null,
    refresh: () => Promise.resolve(),
    setFastPolling: () => {},
    ...overrides,
});
