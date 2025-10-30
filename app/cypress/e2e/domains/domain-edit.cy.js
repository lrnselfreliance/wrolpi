describe('Domain Editing Workflow', () => {
    beforeEach(() => {
        // Suppress uncaught exceptions from the application (API errors are thrown as unhandled rejections)
        cy.on('uncaught:exception', (err) => {
            // Return false to prevent Cypress from failing the test
            // These are expected API errors in error handling tests
            return false;
        });

        // Mock directory search endpoint - DirectorySearch component makes this call automatically
        cy.intercept('POST', '/api/files/search_directories', {
            statusCode: 200,
            body: {is_dir: true, directories: [], channel_directories: [], domain_directories: []}
        }).as('searchDirectories');

        // Mock tags endpoint - needed for TagsSelector component
        cy.intercept('GET', '/api/tags', {
            statusCode: 200,
            body: {
                tags: [
                    {id: 1, name: 'News', color: '#ff0000'},
                    {id: 2, name: 'Tech', color: '#00ff00'}
                ]
            }
        }).as('getTags');

        // Mock the collections list for domains
        cy.intercept('GET', '/api/collections?kind=domain', {
            statusCode: 200,
            body: {
                collections: [
                    {
                        id: 1,
                        domain: 'example.com',
                        archive_count: 42,
                        size: 1024000,
                        tag_name: null,
                        directory: null,
                        can_be_tagged: false,
                        description: 'Example domain'
                    }
                ],
                totals: {collections: 1},
                metadata: {
                    kind: 'domain',
                    columns: [
                        {key: 'domain', label: 'Domain', sortable: true},
                        {key: 'archive_count', label: 'Archives', sortable: true, align: 'right'},
                        {key: 'size', label: 'Size', sortable: true, align: 'right', format: 'bytes'},
                        {key: 'tag_name', label: 'Tag', sortable: true},
                        {key: 'actions', label: 'Manage', sortable: false, type: 'actions'},
                    ],
                    fields: [
                        {key: 'directory', label: 'Directory', type: 'text', placeholder: 'Optional directory path'},
                        {key: 'tag_name', label: 'Tag', type: 'tag', placeholder: 'Select or create tag', depends_on: 'directory'},
                        {key: 'description', label: 'Description', type: 'textarea', placeholder: 'Optional description'},
                    ],
                    routes: {
                        list: '/archive/domains',
                        edit: '/archive/domain/:id/edit',
                        search: '/archive',
                    },
                }
            }
        }).as('getDomains');
    });

    it('completes full edit workflow: add directory and tag', () => {
        // Mock collection details endpoint BEFORE navigation
        cy.intercept('GET', '/api/collections/1', {
            statusCode: 200,
            body: {
                collection: {
                    id: 1,
                    domain: 'example.com',
                    directory: '',
                    tag_name: null,
                    description: '',
                    can_be_tagged: false,
                    archive_count: 42,
                    size: 1024000
                }
            }
        }).as('getDomain');

        // Start at domains list
        cy.visit('/archive/domains');
        cy.wait('@getDomains');

        // Click edit on first domain
        cy.get('table tbody tr').first().within(() => {
            cy.contains('Edit').click();
        });

        // Should navigate to edit page
        cy.url().should('include', '/archive/domain/1/edit');
        cy.wait('@getDomain');

        // Page should load with domain name
        cy.contains('h1', 'example.com').should('exist');

        // Set directory - DirectorySearch component uses input inside field
        cy.contains('label', 'Directory').parent().find('input').clear().type('archive/example.com');

        // Set description - Semantic UI TextArea
        cy.contains('label', 'Description').parent().find('textarea').clear().type('Updated example domain');

        // Mock tags endpoint
        cy.intercept('GET', '/api/tags', {
            statusCode: 200,
            body: {
                tags: [
                    {id: 1, name: 'News', color: '#ff0000'},
                    {id: 2, name: 'Tech', color: '#00ff00'}
                ]
            }
        }).as('getTags');

        // Tag selector should now be enabled (because directory is set)
        // This depends on the actual implementation of CollectionEditForm

        // Mock update endpoint
        cy.intercept('PUT', '/api/collections/1', {
            statusCode: 200,
            body: {
                success: true,
                collection: {
                    id: 1,
                    name: 'example.com',
                    directory: 'archive/example.com',
                    tag_name: null,
                    description: 'Updated example domain',
                    can_be_tagged: true,
                }
            }
        }).as('updateDomain');

        // Save changes
        cy.contains('button', 'Save').click();

        cy.wait('@updateDomain');

        // Should show success toast and stay on edit page (page refreshes data after save)
        cy.contains('Domain Updated').should('be.visible');
        cy.url().should('include', '/archive/domain/1/edit');
    });

    it('shows validation errors for invalid data', () => {
        // Mock domain details
        cy.intercept('GET', '/api/collections/1', {
            statusCode: 200,
            body: {
                collection: {
                    id: 1,
                    domain: 'example.com',
                    directory: 'archive/example.com',
                    tag_name: null,
                    description: 'Example domain',
                    can_be_tagged: true,
                    archive_count: 42,
                    size: 1024000
                }
            }
        }).as('getDomain');

        cy.visit('/archive/domain/1/edit');
        cy.wait('@getDomain');

        // Try to save with invalid directory
        cy.intercept('PUT', '/api/collections/1', {
            statusCode: 400,
            body: {
                error: 'Invalid directory path',
                cause: {
                    code: 'INVALID_DIRECTORY'
                }
            }
        }).as('invalidUpdate');

        cy.contains('label', 'Directory').parent().find('input').clear().type('/invalid/absolute/path');
        cy.contains('button', 'Save').click();

        cy.wait('@invalidUpdate');

        // Should show error message
        cy.contains('Invalid directory path').should('be.visible');

        // Should stay on edit page
        cy.url().should('include', '/edit');
    });

    it('allows navigating back without saving using Back button', () => {
        cy.intercept('GET', '/api/collections/1', {
            statusCode: 200,
            body: {
                collection: {
                    id: 1,
                    domain: 'example.com',
                    directory: '',
                    tag_name: null,
                    description: 'Example domain',
                    can_be_tagged: false,
                    archive_count: 42,
                    size: 1024000
                }
            }
        }).as('getDomain');

        // Mock PUT endpoint but don't expect it to be called
        cy.intercept('PUT', '/api/collections/1', {
            statusCode: 200,
            body: {success: true, domain: {}}
        }).as('updateDomain');

        cy.visit('/archive/domain/1/edit');
        cy.wait('@getDomain');

        // Make some changes
        cy.contains('label', 'Description').parent().find('textarea').clear().type('Changed description');

        // Click Back button (the page uses BackButton, not Cancel)
        cy.contains('button', 'Back').click();

        // Should navigate back without saving
        // Note: Since we don't have browser history in test, we just verify no save was made
        cy.get('@updateDomain.all').should('have.length', 0);
    });

    it('shows form after domain data loads', () => {
        cy.intercept('GET', '/api/collections/1', {
            statusCode: 200,
            body: {
                collection: {
                    id: 1,
                    domain: 'example.com',
                    directory: null,
                    tag_name: null,
                    description: 'Example domain',
                    can_be_tagged: false
                }
            }
        }).as('getDomain');

        cy.visit('/archive/domain/1/edit');

        cy.wait('@getDomain');

        // Form should be visible with domain name in title
        cy.contains('h1', 'example.com').should('exist');

        // Form fields should be present
        cy.contains('label', 'Directory').should('exist');
        cy.contains('label', 'Description').should('exist');
    });

    it('handles 404 when domain not found', () => {
        cy.intercept('GET', '/api/collections/999', {
            statusCode: 404,
            body: {
                error: 'Domain collection with ID 999 not found'
            }
        }).as('domainNotFound');

        cy.visit('/archive/domain/999/edit');
        cy.wait('@domainNotFound');

        // Should show error message
        cy.contains('not found').should('be.visible');
    });
});
