import React from 'react';
import {ArchiveDownloadForm, ChannelDownloadForm, EditRSSDownloadForm} from './Download';

/*
 * A field in the error state.
 *
 * The old form controls took `error` and put the bare word on the DOM node, so a spec could
 * assert `have.attr 'error'`.  Our fields mark an invalid control the way assistive
 * technology reads it instead -- `aria-invalid` on the input.  The old assertion did not
 * fail when the controls changed; it went on looking for an attribute that no longer
 * exists, on a field that is both styled and announced as invalid.
 *
 * Valid is `aria-invalid="false"`, not a missing attribute: the field states its validity
 * either way, which is what lets a screen reader say a control is fine rather than say
 * nothing about it.  Both are asserted by value so neither direction can pass on absence.
 */
const shouldBeInvalid = (selector) => cy.get(selector).should('have.attr', 'aria-invalid', 'true');
const shouldBeValid = (selector) => cy.get(selector).should('have.attr', 'aria-invalid', 'false');

describe('<ArchiveDownloadForm />', () => {
    beforeEach(() => {
        cy.mountWithTags(<ArchiveDownloadForm/>);
    });

    it('displays error for invalid URL', () => {
        cy.get('#urls_textarea').type('invalid-url').wait(500);
        shouldBeInvalid('#urls_textarea');
    });

    it('enables download button for valid URL', () => {
        cy.get('#urls_textarea').type('https://wrolpi.org').wait(500);
        shouldBeValid('#urls_textarea');
        cy.get('#download_form_download_button').should('be.visible').and('not.have.attr', 'disabled');
    });

    it('disables download button for invalid URL', () => {
        cy.get('#urls_textarea').type('invalid-url').wait(500);
        shouldBeInvalid('#urls_textarea');
        cy.get('#download_form_download_button').should('be.visible').and('have.attr', 'disabled');
    });

    it('initially has download button disabled', () => {
        cy.get('#download_form_download_button').should('be.visible').and('have.attr', 'disabled');
    });

    it('clears error when switching from invalid to valid URL', () => {
        cy.get('#urls_textarea').type('invalid-url').wait(500);
        shouldBeInvalid('#urls_textarea');

        cy.get('#urls_textarea').clear();
        cy.get('#urls_textarea').type('https://wrolpi.org').wait(500);
        shouldBeValid('#urls_textarea');
    });
});

describe('<ChannelDownloadForm/>', () => {
    beforeEach(() => {
        // Do not return directories for these tests.
        cy.intercept('POST', '**/api/files/search_directories', {
            statusCode: 200,
            body: {
                is_dir: true, channel_directories: [], domain_directories: [],
                directories: [{path: "some directory", name: "some directory"}],
            },
        }).as('searchDirectories');

        cy.mountWithTags(<ChannelDownloadForm/>);
    });

    it('displays error for invalid URL', () => {
        cy.get('#url_input').type('invalid-url').wait(500);
        shouldBeInvalid('#url_input');
    });

    it('can choose different options', () => {
        /*
         * `#download_frequency_selector` and `.item` named the old dropdown and its menu rows.
         * SelectField ids each control `<name>_select`, and an option carries the ARIA role
         * rather than a class -- which is what a screen reader navigates, so it is the better
         * handle of the two.
         */
        const chooseFrequency = (label) => {
            cy.get('#frequency_select').click();
            /*
             * One query, so Cypress retries the whole thing while the dropdown opens.
             * `cy.get(...).contains(...)` does not: `get` settles on whatever matched at
             * that instant, and the options are not in the DOM yet when it does.
             *
             * `:visible` because the form carries several Selects, each keeping its options
             * mounted while closed -- a bare `[role="option"]` matches a hidden one from a
             * dropdown that was never opened, and clicking that fails.
             */
            cy.get('[role="option"]:visible').should('have.length.greaterThan', 0);
            /*
             * `force` because the dropdown re-renders as its open transition settles, and
             * Cypress aborts a click whose element was replaced between locating it and
             * clicking it.  Visibility is asserted on its own above, so this is not
             * skipping a check that could hide an unreachable control.
             */
            cy.contains('[role="option"]:visible', label).should('be.visible')
                .click({force: true});
            cy.get('#frequency_select').should('have.value', label);
        };

        chooseFrequency('Once');
        chooseFrequency('Daily');
        chooseFrequency('180 Days');
    });
});

const downloadersResponse = {
    "downloaders": [{"name": "archive", "pretty_name": "Archive"}, {
        "name": "video",
        "pretty_name": "Videos"
    }], "manager_disabled": true
};

describe('<EditRSSDownloadForm />', () => {
    beforeEach(() => {
        const download = {
            id: 1,
            destination: "destination directory",
            downloader: "rss",
            frequency: 604800,
            next_download: "2024-11-24T16:34:21.014400+00:00",
            settings: {
                title_include: "included",
                title_exclude: "excluded",
                video_format: "mp4",
                video_resolutions: [
                    "720p",
                    "480p",
                    "maximum"
                ]
            },
            sub_downloader: "video",
            tag_names: ['Automotive'],
            url: "https://www.youtube.com/feeds/videos.xml?channel_id=UC4t8bw1besFTyjW7ZBCOIrw"
        };
        /*
         * The intercepts are declared BEFORE the mount, which is the whole reason this
         * block is ordered this way.  Mounting first lets the form's own effects fire
         * against a bare network -- `/api/downloaders` rejected with "Failed to fetch",
         * and Cypress fails a test on an unhandled rejection out of application code
         * whatever it was in the middle of asserting.
         */
        cy.intercept('GET', '**/api/downloaders', downloadersResponse).as('downloaders');
        cy.intercept('POST', '**/api/files/search_directories', {
            statusCode: 200,
            body: {
                is_dir: true, channel_directories: [], domain_directories: [],
                directories: [{path: "some directory", name: "some directory"}],
            },
        }).as('searchDirectories');

        cy.mountWithTags(<EditRSSDownloadForm download={download}/>);
    });

    it('can edit videos download', () => {
        // Weekly frequency.
        cy.get('#url_input').should('have.value',
            'https://www.youtube.com/feeds/videos.xml?channel_id=UC4t8bw1besFTyjW7ZBCOIrw');
        // The old dropdown showed its choice in a `div.divider.text`; a Select is a real input
        // holding the label, so the value can be read rather than searched for.
        cy.get('#frequency_select').should('have.value', 'Weekly');
        cy.get('input[name="title_include"]').should('have.value', 'included');
        cy.get('input[name="title_exclude"]').should('have.value', 'excluded');
        cy.get('#destination_search_form').should('be.visible');
        cy.get('.wrolpi-tag').contains('Automotive').should('be.visible');
    });

    it('can submit videos download', () => {
        cy.get('button[type="submit"]').should('be.visible');

        cy.intercept('PUT', '/api/download/1', {statusCode: 204}).as('downloadPut');

        cy.get('button[type="submit"]').click();

        /*
         * The edit form sends the download back unchanged.
         *
         * This asserted one exact JSON string, which broke the moment the video downloader
         * gained settings the form fills in with their defaults -- `compress_singlefile`,
         * `audio_only`, `user_agent` and five more.  None of that is the subject: what
         * matters is that the values the user was shown are the values that go back.
         *
         * So the envelope is still matched exactly, which catches a field appearing or
         * vanishing at the top level, while `settings` is checked for the seven the fixture
         * set.  Waiting on the alias matters as much as either -- without it the click ended
         * the test and an interceptor that never ran would have passed silently.
         */
        cy.wait('@downloadPut').its('request.body').then((body) => {
            const sent = typeof body === 'string' ? JSON.parse(body) : body;
            const {settings, ...envelope} = sent;

            expect(envelope).to.deep.equal({
                destination: 'destination directory',
                downloader: 'rss',
                frequency: 604800,
                sub_downloader: 'video',
                tag_names: ['Automotive'],
                urls: ['https://www.youtube.com/feeds/videos.xml?channel_id=UC4t8bw1besFTyjW7ZBCOIrw'],
            });

            expect(settings).to.deep.include({
                excluded_urls: null,
                title_exclude: 'excluded',
                title_include: 'included',
                video_resolutions: ['720p', '480p', 'maximum'],
                video_format: 'mp4',
                minimum_duration: null,
                maximum_duration: null,
            });
        });
    });
});
