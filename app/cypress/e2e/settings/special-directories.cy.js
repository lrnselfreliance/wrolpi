/*
 * The five Special Directories fields on /admin/settings.
 *
 * These are the fields that shipped printing their own prefix over their own value, and the
 * ones whose visible labels were never associated with their inputs.  Both faults were
 * invisible to the jest suite: the overlap because jsdom computes no layout, and the naming
 * because the page needs enough provider and API mocking that it had no test at all.
 *
 * Intercepting the API is not mocking the component -- the page really renders, so the
 * accessible names and the real geometry are the ones a user gets.
 */
describe('Special Directories settings', () => {
    const mockSettings = {
        archive_destination: 'archive/%(domain_tag)s/%(domain)s',
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
        check_for_upgrades: true,
        ignore_outdated_zims: false,
        log_level: 'info',
        map_destination: 'map',
        nav_color: 'violet',
        media_directory: '/media/wrolpi',
        playlists_destination: 'playlists',
        tags_directory: true,
        throttle_on_startup: false,
        version: '1.0.0',
        videos_destination: 'videos/%(channel_tag)s/%(channel_name)s',
        wrol_mode: false,
        zims_destination: 'zims',
        save_ffprobe_json: true,
    };

    const directories = [
        ['Archive Directory', 'archive/%(domain_tag)s/%(domain)s'],
        ['Videos Directory', 'videos/%(channel_tag)s/%(channel_name)s'],
        ['Map Directory', 'map'],
        ['Zims Directory', 'zims'],
        ['Playlists Directory', 'playlists'],
    ];

    beforeEach(() => {
        cy.intercept('GET', '/api/status', {
            statusCode: 200,
            body: {
                version: '1.0.0',
                flags: {},
                cpu_percent: 10,
                memory_percent: 30,
                downloads: {
                    pending: 0, recurring: 0, disabled: false, stopped: false,
                    outside_download_window: false,
                },
            },
        }).as('getStatus');
        cy.intercept('GET', '/api/tags', {statusCode: 200, body: {tags: []}}).as('getTags');
        cy.intercept('GET', '/api/events', {statusCode: 200, body: {events: []}}).as('getEvents');
        cy.intercept('POST', '/api/search/suggestions', {
            statusCode: 200,
            body: {fileGroups: 0, zimsEstimates: [], channels: [], domains: []},
        }).as('getSuggestions');
        cy.intercept('GET', '/api/settings', {statusCode: 200, body: {...mockSettings}})
            .as('getSettings');

        cy.visit('/admin/settings');
        cy.wait('@getSettings');
    });

    it('names every directory field, so they can be told apart', () => {
        /*
         * All five fields sit in one grid, hold similar-looking relative paths, and share the
         * same prefix.  Without a name attached to the input, a screen reader user hears five
         * fields described only as "/media/wrolpi/" and cannot tell which one saves videos.
         */
        directories.forEach(([label, value]) => {
            cy.contains('label', label)
                .invoke('attr', 'for')
                .should('be.a', 'string')
                .then((inputId) => {
                    cy.get(`#${CSS.escape(inputId)}`)
                        .should('have.value', value)
                        .and('match', 'input');
                });
        });
    });

    it('shows the media directory beside each value, never over it', () => {
        // The reported bug: `a/media/wrolpi/hain_tag)s/%(domain)s`.
        cy.get('.wrolpi-path-input').should('have.length', directories.length);

        cy.get('.wrolpi-path-input').each(($field) => {
            const prefix = $field.find('.wrolpi-path-input-prefix')[0].getBoundingClientRect();
            const input = $field.find('input')[0].getBoundingClientRect();
            expect(prefix.right, 'prefix ends where the input begins')
                .to.be.at.most(input.left + 0.5);
            expect(input.width, 'input is wide enough to read and edit').to.be.greaterThan(60);
        });
    });

    it('keeps the prefix out of the value the user edits and saves', () => {
        cy.contains('label', 'Archive Directory').invoke('attr', 'for').then((inputId) => {
            cy.get(`#${CSS.escape(inputId)}`)
                .should('have.value', 'archive/%(domain_tag)s/%(domain)s')
                .and('not.have.value', '/media/wrolpi/archive/%(domain_tag)s/%(domain)s');
        });

        cy.get('.wrolpi-path-input-prefix').first().should('have.text', '/media/wrolpi/');
    });
});
