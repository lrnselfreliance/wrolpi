describe('Download Window Settings', () => {
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
        tags_directory: true,
        throttle_on_startup: false,
        version: '1.0.0',
        videos_destination: 'videos/%(channel_tag)s/%(channel_name)s',
        wrol_mode: false,
        zims_destination: 'zims',
        save_ffprobe_json: true,
    };

    beforeEach(() => {
        cy.intercept('GET', '/api/status', {
            statusCode: 200,
            body: {
                version: '1.0.0',
                flags: {},
                cpu_percent: 10,
                memory_percent: 30,
                downloads: {pending: 0, recurring: 0, disabled: false, stopped: false, outside_download_window: false},
            }
        }).as('getStatus');

        cy.intercept('GET', '/api/tags', {
            statusCode: 200,
            body: {tags: []}
        }).as('getTags');

        cy.intercept('GET', '/api/events', {
            statusCode: 200,
            body: {events: []}
        }).as('getEvents');

        cy.intercept('POST', '/api/search/suggestions', {
            statusCode: 200,
            body: {fileGroups: 0, zimsEstimates: [], channels: [], domains: []}
        }).as('getSuggestions');
    });

    it('time inputs are empty when no window is configured', () => {
        cy.intercept('GET', '/api/settings', {
            statusCode: 200,
            body: {...mockSettings},
        }).as('getSettings');

        cy.visit('/admin/settings');
        cy.wait('@getSettings');

        cy.get('input[type="time"]').should('have.length', 2);
        cy.get('input[type="time"]').first().should('have.value', '');
        cy.get('input[type="time"]').last().should('have.value', '');
    });

    it('displays saved download window values from API', () => {
        cy.intercept('GET', '/api/settings', {
            statusCode: 200,
            body: {
                ...mockSettings,
                download_window_start: '08:00',
                download_window_end: '17:00',
            },
        }).as('getSettings');

        cy.visit('/admin/settings');
        cy.wait('@getSettings');

        cy.get('input[type="time"]').should('have.length', 2);
        cy.get('input[type="time"]').first().should('have.value', '08:00');
        cy.get('input[type="time"]').last().should('have.value', '17:00');
    });

    it('can set download window values', () => {
        cy.intercept('GET', '/api/settings', {
            statusCode: 200,
            body: {...mockSettings},
        }).as('getSettings');

        cy.visit('/admin/settings');
        cy.wait('@getSettings');

        cy.get('input[type="time"]').first().type('08:00');
        cy.get('input[type="time"]').first().should('have.value', '08:00');

        cy.get('input[type="time"]').last().type('17:00');
        cy.get('input[type="time"]').last().should('have.value', '17:00');
    });

    it('displays overnight window values from API', () => {
        cy.intercept('GET', '/api/settings', {
            statusCode: 200,
            body: {
                ...mockSettings,
                download_window_start: '22:00',
                download_window_end: '06:00',
            },
        }).as('getSettings');

        cy.visit('/admin/settings');
        cy.wait('@getSettings');

        cy.get('input[type="time"]').first().should('have.value', '22:00');
        cy.get('input[type="time"]').last().should('have.value', '06:00');
    });
});
