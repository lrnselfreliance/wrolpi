import React from 'react';
import {ArchiveDownloadForm, ChannelDownloadForm, EditRSSDownloadForm} from './Download';
import 'semantic-ui-offline/semantic.min.css';

describe('<ArchiveDownloadForm />', () => {
    beforeEach(() => {
        cy.mountWithTags(<ArchiveDownloadForm/>);
    });

    it('displays error for invalid URL', () => {
        cy.get('#urls_textarea').type('invalid-url').wait(500);
        cy.get('#urls_textarea').should('have.attr', 'error');
    });

    it('enables download button for valid URL', () => {
        cy.get('#urls_textarea').type('https://wrolpi.org').wait(500);
        cy.get('#urls_textarea').should('not.have.attr', 'error');
        cy.get('#download_form_download_button').should('be.visible').and('not.have.attr', 'disabled');
    });

    it('disables download button for invalid URL', () => {
        cy.get('#urls_textarea').type('invalid-url').wait(500);
        cy.get('#urls_textarea').should('have.attr', 'error');
        cy.get('#download_form_download_button').should('be.visible').and('have.attr', 'disabled');
    });

    it('initially has download button disabled', () => {
        cy.get('#download_form_download_button').should('be.visible').and('have.attr', 'disabled');
    });

    it('clears error when switching from invalid to valid URL', () => {
        cy.get('#urls_textarea').type('invalid-url').wait(500);
        cy.get('#urls_textarea').should('have.attr', 'error');

        cy.get('#urls_textarea').clear();
        cy.get('#urls_textarea').type('https://wrolpi.org').wait(500);
        cy.get('#urls_textarea').should('not.have.attr', 'error');
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
        cy.get('#url_input').should('have.attr', 'error');
    });

    it('can choose different options', () => {
        cy.get('#download_frequency_selector').click()
            .get('.item').contains('Once').click();
        cy.get('#download_frequency_selector').click()
            .get('.item').contains('Daily').click();
        cy.get('#download_frequency_selector').click()
            .get('.item').contains('180 Days').click();
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
        cy.mountWithTags(<EditRSSDownloadForm download={download}/>);
        cy.intercept('GET', '/api/downloaders', downloadersResponse).as('downloaders');
        cy.intercept('POST', '**/api/files/search_directories', {
            statusCode: 200,
            body: {
                is_dir: true, channel_directories: [], domain_directories: [],
                directories: [{path: "some directory", name: "some directory"}],
            },
        }).as('searchDirectories');

    });

    it('can edit videos download', () => {
        // Weekly frequency.
        cy.get('#url_input').should('have.value',
            'https://www.youtube.com/feeds/videos.xml?channel_id=UC4t8bw1besFTyjW7ZBCOIrw');
        cy.get('div.divider.text').contains('Weekly');
        cy.get('input[name="title_include"]').should('have.value', 'included');
        cy.get('input[name="title_exclude"]').should('have.value', 'excluded');
        cy.get('#destination_search_form').should('be.visible');
        cy.get('div.ui.large.label').contains('Automotive').should('be.visible');
    });

    it('can submit videos download', () => {
        cy.get('button[type="submit"]').should('be.visible');

        cy.intercept('PUT', '/api/download/1', (req) => {
            expect(req.body).to.deep.equal(JSON.stringify({
                "destination": "destination directory",
                "downloader": "rss",
                "frequency": 604800,
                "settings": {
                    "excluded_urls": null,
                    "title_exclude": "excluded",
                    "title_include": "included",
                    "video_resolutions": [
                        "720p",
                        "480p",
                        "maximum"
                    ],
                    "video_format": "mp4",
                    "minimum_duration": null,
                    "maximum_duration": null
                },
                "sub_downloader": "video",
                "tag_names": ["Automotive"],
                "urls": ["https://www.youtube.com/feeds/videos.xml?channel_id=UC4t8bw1besFTyjW7ZBCOIrw"]
            }));
            req.reply({statusCode: 204});
        }).as('downloadPut');

        cy.get('button[type="submit"]').click();
    });
});
