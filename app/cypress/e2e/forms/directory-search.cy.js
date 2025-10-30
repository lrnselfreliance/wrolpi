describe('DirectorySearch Integration Tests', () => {
    const mockSearchResponse = {
        is_dir: false,
        directories: [
            {path: 'videos/nature'},
            {path: 'videos/tech'},
            {path: 'videos/cooking'}
        ],
        channel_directories: [
            {path: 'videos/channels/news', name: 'News Channel'},
            {path: 'videos/channels/tech', name: 'Tech Reviews'}
        ],
        domain_directories: [
            {path: 'archive/example.com', domain: 'example.com'},
            {path: 'archive/test.org', domain: 'test.org'}
        ]
    };

    const mockEmptyResponse = {
        is_dir: false,
        directories: [],
        channel_directories: [],
        domain_directories: []
    };

    const mockExistingDirResponse = {
        is_dir: true,
        directories: [
            {path: 'videos/nature/wildlife'},
            {path: 'videos/nature/ocean'}
        ],
        channel_directories: [],
        domain_directories: []
    };

    beforeEach(() => {
        // Mock the directory search API
        cy.intercept('POST', '/api/files/search_directories', (req) => {
            const {path} = req.body;

            if (path === 'videos') {
                req.reply({statusCode: 200, body: mockSearchResponse});
            } else if (path === 'empty') {
                req.reply({statusCode: 200, body: mockEmptyResponse});
            } else if (path === 'videos/nature') {
                req.reply({statusCode: 200, body: mockExistingDirResponse});
            } else {
                req.reply({statusCode: 200, body: mockSearchResponse});
            }
        }).as('searchDirectories');
    });

    context('Standalone DirectorySearch Behavior', () => {
        beforeEach(() => {
            // Visit a page with DirectorySearch (using domain edit as example)
            cy.intercept('GET', '/api/collections/1', {
                statusCode: 200,
                body: {
                    collection: {
                        id: 1,
                        name: 'example.com',
                        kind: 'domain',
                        directory: '',
                        description: '',
                        tag_name: null
                    }
                }
            }).as('getDomain');

            cy.intercept('GET', '/api/collections?kind=domain', {
                statusCode: 200,
                body: {
                    collections: [],
                    totals: {collections: 0},
                    metadata: {
                        kind: 'domain',
                        columns: [],
                        fields: [
                            {key: 'directory', label: 'Directory', type: 'text', required: false}
                        ],
                        routes: {},
                        messages: {}
                    }
                }
            }).as('getMetadata');

            cy.visit('/archive/domain/1/edit');
            cy.wait('@getDomain');
            cy.wait('@getMetadata');
        });

        it('types in search box and sees results', () => {
            // Find the directory input
            cy.contains('label', 'Directory')
                .parent()
                .find('input')
                .type('videos');

            cy.wait('@searchDirectories');

            // Should see results in dropdown
            cy.contains('videos/nature').should('be.visible');
            cy.contains('videos/tech').should('be.visible');
        });

        it('clicks result and value updates', () => {
            cy.contains('label', 'Directory')
                .parent()
                .find('input')
                .type('videos');

            cy.wait('@searchDirectories');

            // Click a result
            cy.contains('videos/nature').click();

            // Input should show selected value
            cy.contains('label', 'Directory')
                .parent()
                .find('input')
                .should('have.value', 'videos/nature');
        });


        it('categories are visually distinct', () => {
            cy.contains('label', 'Directory')
                .parent()
                .find('input')
                .type('videos');

            cy.wait('@searchDirectories');

            // Check that categories exist
            cy.contains('Directories').should('be.visible');
            cy.contains('Channels').should('be.visible');
            cy.contains('Domains').should('be.visible');
        });

        it('result descriptions appear correctly', () => {
            cy.contains('label', 'Directory')
                .parent()
                .find('input')
                .type('videos');

            cy.wait('@searchDirectories');

            // Channel should show name as description
            cy.contains('News Channel').should('be.visible');

            // Domain should show domain as description
            cy.contains('example.com').should('be.visible');
        });

        it('shows "New Directory" for new paths', () => {
            cy.contains('label', 'Directory')
                .parent()
                .find('input')
                .type('empty');

            cy.wait('@searchDirectories');

            // Should show "New Directory" option
            cy.contains('New Directory').should('be.visible');
        });

    });

    context('DestinationForm Workflow', () => {
        beforeEach(() => {
            // Set up domain edit page as a form with DestinationForm
            cy.intercept('GET', '/api/collections/2', {
                statusCode: 200,
                body: {
                    collection: {
                        id: 2,
                        name: 'test.com',
                        kind: 'domain',
                        directory: 'archive/test.com',
                        description: '',
                        tag_name: null
                    }
                }
            }).as('getDomain');

            cy.intercept('GET', '/api/collections?kind=domain', {
                statusCode: 200,
                body: {
                    collections: [],
                    totals: {collections: 0},
                    metadata: {
                        kind: 'domain',
                        columns: [],
                        fields: [
                            {key: 'directory', label: 'Directory', type: 'text', required: true}
                        ],
                        routes: {},
                        messages: {}
                    }
                }
            }).as('getMetadata');

            cy.visit('/archive/domain/2/edit');
            cy.wait('@getDomain');
            cy.wait('@getMetadata');
        });

        it('starts with existing directory value', () => {
            cy.contains('label', 'Directory')
                .parent()
                .find('input')
                .should('have.value', 'archive/test.com');
        });

        it('types partial path and sees suggestions', () => {
            cy.contains('label', 'Directory')
                .parent()
                .find('input')
                .clear()
                .type('videos');

            cy.wait('@searchDirectories');

            // Should see suggestions
            cy.contains('videos/nature').should('be.visible');
        });

        it('selects channel directory and form updates', () => {
            cy.contains('label', 'Directory')
                .parent()
                .find('input')
                .clear()
                .type('videos');

            cy.wait('@searchDirectories');

            // Select a channel directory
            cy.contains('News Channel').click();

            // Form should update
            cy.contains('label', 'Directory')
                .parent()
                .find('input')
                .should('have.value', 'videos/channels/news');
        });


    });

    context('Real-World Scenarios', () => {
        it('handles API returning empty results', () => {
            cy.intercept('GET', '/api/collections/3', {
                statusCode: 200,
                body: {
                    collection: {
                        id: 3,
                        name: 'empty.com',
                        kind: 'domain',
                        directory: '',
                        description: '',
                        tag_name: null
                    }
                }
            }).as('getDomain');

            cy.intercept('GET', '/api/collections?kind=domain', {
                statusCode: 200,
                body: {
                    collections: [],
                    totals: {collections: 0},
                    metadata: {
                        kind: 'domain',
                        columns: [],
                        fields: [
                            {key: 'directory', label: 'Directory', type: 'text', required: false}
                        ],
                        routes: {},
                        messages: {}
                    }
                }
            }).as('getMetadata');

            cy.visit('/archive/domain/3/edit');
            cy.wait('@getDomain');
            cy.wait('@getMetadata');

            // Type path that returns empty results
            cy.contains('label', 'Directory')
                .parent()
                .find('input')
                .type('empty');

            cy.wait('@searchDirectories');

            // Should show "New Directory" option
            cy.contains('New Directory').should('be.visible');
        });

    });
});
