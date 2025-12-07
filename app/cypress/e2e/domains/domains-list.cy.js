describe('Domains List Page', () => {
    beforeEach(() => {
        // Mock the collections API response for domains
        cy.intercept('GET', '/api/collections?kind=domain', {
            statusCode: 200,
            body: {
                collections: [
                    {
                        id: 1,
                        domain: 'example.com',
                        archive_count: 42,
                        size: 1024000,
                        tag_name: 'News',
                        directory: '/media/archives/example.com',
                        can_be_tagged: true,
                        description: 'Example domain'
                    },
                    {
                        id: 2,
                        domain: 'test.org',
                        archive_count: 15,
                        size: 512000,
                        tag_name: null,
                        directory: null,
                        can_be_tagged: false,
                        description: null
                    }
                ],
                totals: {collections: 2},
                metadata: {
                    kind: 'domain',
                    columns: [
                        {key: 'domain', label: 'Domain', sortable: true},
                        {key: 'archive_count', label: 'Archives', sortable: true, align: 'right'},
                        {key: 'size', label: 'Size', sortable: true, align: 'right', format: 'bytes'},
                        {key: 'tag_name', label: 'Tag', sortable: true},
                        {key: 'actions', label: 'Manage', sortable: false, type: 'actions'}
                    ],
                    fields: [
                        {key: 'directory', label: 'Directory', type: 'text', placeholder: 'Optional directory path'},
                        {key: 'tag_name', label: 'Tag', type: 'tag', placeholder: 'Select or create tag', depends_on: 'directory'},
                        {key: 'description', label: 'Description', type: 'textarea', placeholder: 'Optional description'}
                    ],
                    routes: {
                        list: '/archive/domains',
                        edit: '/archive/domain/:id/edit',
                        search: '/archive'
                    },
                    messages: {
                        no_directory: 'Set a directory to enable tagging',
                        tag_will_move: 'Tagging will move files to a new directory'
                    }
                }
            }
        }).as('getDomains');

        // Visit the domains page
        cy.visit('/archive/domains');
        cy.wait('@getDomains');
    });

    it('displays domains page without errors', () => {
        // DomainsPage doesn't have h1, check for the search input instead
        cy.get('input[placeholder="Domain filter..."]').should('exist');
    });

    it('renders CollectionTable component', () => {
        // Check that the table exists
        cy.get('table').should('exist');
    });

    it('shows search input', () => {
        cy.get('input[placeholder="Domain filter..."]').should('exist');
    });

    it('shows all domains from API', () => {
        cy.get('table tbody tr').should('have.length', 2);
    });

    it('displays domain names', () => {
        cy.get('table tbody tr').first().should('contain', 'example.com');
        cy.get('table tbody tr').last().should('contain', 'test.org');
    });

    it('displays Edit buttons in Manage column', () => {
        cy.get('table tbody tr').first().within(() => {
            cy.get('a').contains('Edit').should('exist');
        });
    });

    it('Edit button has correct styling', () => {
        cy.get('table tbody tr').first().within(() => {
            cy.get('a').contains('Edit').should('have.class', 'ui');
            cy.get('a').contains('Edit').should('have.class', 'button');
            cy.get('a').contains('Edit').should('have.class', 'secondary');
        });
    });

    it('navigates to domain edit page when edit clicked', () => {
        // Mock the edit page's API calls to prevent "Failed to fetch" errors
        cy.intercept('GET', '/api/collections/1', {
            statusCode: 200,
            body: {
                collection: {
                    id: 1,
                    domain: 'example.com',
                    directory: '/media/archives/example.com',
                    tag_name: 'News',
                    description: 'Example domain'
                }
            }
        }).as('getDomain');

        // Mock directory search to prevent errors
        cy.intercept('POST', '/api/files/search_directories', {
            statusCode: 200,
            body: {is_dir: true, directories: [], channel_directories: [], domain_directories: []}
        }).as('searchDirs');

        cy.get('table tbody tr').first().within(() => {
            cy.get('a').contains('Edit').click();
        });
        cy.url().should('include', '/archive/domain/1/edit');
    });

    it('filters domains with search', () => {
        cy.get('input[placeholder="Domain filter..."]').type('example');
        // Increase timeout to handle slower CI environments where React state updates may take longer
        cy.get('table tbody tr', {timeout: 10000}).should('have.length', 1);
        cy.get('table tbody tr').should('contain', 'example.com');
    });

    it('shows empty message when no domains', () => {
        cy.intercept('GET', '/api/collections?kind=domain', {
            statusCode: 200,
            body: {
                collections: [],
                totals: {collections: 0},
                metadata: {
                    kind: 'domain',
                    columns: []
                }
            }
        }).as('getEmptyDomains');

        cy.visit('/archive/domains');
        cy.wait('@getEmptyDomains');

        cy.contains('No domains yet').should('exist');
    });

    it('does not show "New Domain" button (domains are auto-created)', () => {
        cy.contains('button', 'New Domain').should('not.exist');
    });
});
