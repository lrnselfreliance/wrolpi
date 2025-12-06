import React from "react";
import {ChannelEditPage, ChannelNewPage} from "./Channels";

describe('Channels Page', () => {
    beforeEach(() => {
        // Do not return directories for these tests.
        cy.intercept('POST', '**/api/files/search_directories', {
            statusCode: 200,
            body: {
                is_dir: true, channel_directories: [], domain_directories: [],
                directories: [{path: "some directory", name: "some directory"}],
            },
        }).as('searchDirectories');
    });

    it('New Channel page can be rendered', () => {
        cy.mountWithTags(
            <ChannelNewPage/>,
            {initialEntries: ['/videos/channels/new']}
        );
        cy.get('input[name="name"]').should('be.visible');
        cy.wait('@searchDirectories');
    });

    it('Edit Channel page can be rendered', () => {
        cy.intercept('GET', '**/api/videos/channels/1', {
            statusCode: 200,
            body: {
                channel: {
                    name: 'Editing Channel',
                    tag_name: 'Automotive',
                    id: 1,
                    directory: 'some directory',
                    rss_url: 'https://example.com/rss-feed',
                    downloads: [],
                    statistics: {
                        size: 1,
                        largest_video: 2,
                        video_count: 3,
                        length: 4,
                        video_tags: 5,
                    }
                }
            },
        }).as('channelFetch');

        cy.mountWithTags(
            <ChannelEditPage/>,
            {initialEntries: ['/videos/channel/1/edit']}
        );
        cy.wait('@channelFetch');
        cy.wait('@searchDirectories'); // Needed for CircleCi.
        cy.wait(500);
        cy.get('input[name="name"]').should('be.visible');
        cy.get('input[name="name"]').should('have.value', 'Editing Channel');
        cy.get('div.ui.label.large').contains('Automotive').should('be.visible');
    });
});
