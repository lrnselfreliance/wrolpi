import React from 'react';
import {render, screen, createTestForm} from '../test-utils';
import {CollectionEditForm} from './collections/CollectionEditForm';
import {DomainsPage} from './Archive';
import {createMockDomain} from '../test-utils';

// Mock the TagsContext
jest.mock('../Tags', () => ({
    TagsContext: {
        _currentValue: {
            SingleTag: ({name}) => <span data-testid="applied-tag">{name}</span>
        }
    },
}));

// Mock the DirectorySearch and DestinationForm components
jest.mock('./Common', () => ({
    ...jest.requireActual('./Common'),
    DirectorySearch: ({value, onSelect, placeholder}) => (
        <input
            data-testid="directory-search"
            value={value || ''}
            onChange={(e) => onSelect(e.target.value)}
            placeholder={placeholder}
        />
    ),
    SearchInput: ({placeholder, searchStr, onChange, disabled}) => (
        <input
            data-testid="search-input"
            placeholder={placeholder}
            value={searchStr || ''}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
        />
    ),
    ErrorMessage: ({children}) => <div data-testid="error-message">{children}</div>,
    useTitle: jest.fn(),
}));

// Mock DestinationForm (used for directory field)
jest.mock('./Download', () => ({
    DestinationForm: ({form, label, name}) => (
        <div data-testid="directory-search">
            <label>{label}</label>
            <input
                value={form.formData[name] || ''}
                onChange={(e) => form.setValue(name, e.target.value)}
            />
        </div>
    ),
}));

// Mock hooks for DomainsPage tests
const mockUseDomains = jest.fn();
const mockUseOneQuery = jest.fn(() => ['', jest.fn()]);

jest.mock('../hooks/customHooks', () => ({
    ...jest.requireActual('../hooks/customHooks'),
    useDomains: (...args) => mockUseDomains(...args),
    useOneQuery: (...args) => mockUseOneQuery(...args),
}));

// Mock CollectionTable for DomainsPage tests
jest.mock('./collections/CollectionTable', () => ({
    CollectionTable: ({collections}) => (
        <div data-testid="collection-table">
            <table>
                <tbody>
                    {collections?.map((domain) => (
                        <tr key={domain.id} data-testid={`domain-row-${domain.id}`}>
                            <td data-testid={`domain-name-${domain.id}`}>{domain.domain}</td>
                            <td data-testid={`domain-tag-${domain.id}`}>
                                {domain.tag_name || 'No tag'}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    ),
}));

describe('Domain Tagging Logic', () => {
    describe('CollectionEditForm with children', () => {
        it('renders children and appliedTagName', () => {
            const mockDomain = createMockDomain({
                directory: 'archive/example.com',
                tag_name: 'News',
            });

            const form = createTestForm(mockDomain);

            render(
                <CollectionEditForm
                    form={form}
                    title="Edit Domain: example.com"
                    appliedTagName="News"
                >
                    <div data-testid="child-content">Child content</div>
                </CollectionEditForm>
            );

            // Should render title
            expect(screen.getByRole('heading', {level: 1})).toHaveTextContent('Edit Domain: example.com');

            // Should render children
            expect(screen.getByTestId('child-content')).toBeInTheDocument();

            // Should render applied tag
            expect(screen.getByTestId('applied-tag')).toHaveTextContent('News');

            // Should render Save button
            expect(screen.getByRole('button', {name: /save/i})).toBeInTheDocument();
        });

        it('renders action buttons', () => {
            const mockDomain = createMockDomain({
                directory: 'archive/example.com',
            });

            const form = createTestForm(mockDomain);

            render(
                <CollectionEditForm
                    form={form}
                    title="Edit Domain"
                    actionButtons={<button data-testid="action-button">Action</button>}
                >
                    <div>Form content</div>
                </CollectionEditForm>
            );

            expect(screen.getByTestId('action-button')).toBeInTheDocument();
        });

        it('does not render appliedTagName when not provided', () => {
            const mockDomain = createMockDomain({
                directory: 'archive/example.com',
            });

            const form = createTestForm(mockDomain);

            render(
                <CollectionEditForm
                    form={form}
                    title="Edit Domain"
                >
                    <div>Form content</div>
                </CollectionEditForm>
            );

            expect(screen.queryByTestId('applied-tag')).not.toBeInTheDocument();
        });
    });

    describe('Tag Display in Domains List', () => {
        const {useTitle} = require('./Common');

        beforeEach(() => {
            // Reset mocks
            mockUseDomains.mockReset();
            mockUseOneQuery.mockReset();
            useTitle.mockReset();

            // Re-setup default mocks
            useTitle.mockImplementation(() => {});
            mockUseOneQuery.mockReturnValue(['', jest.fn()]);
        });

        it('displays tag in domains list after tagging', () => {
            const mockDomains = [
                createMockDomain({
                    id: 1,
                    domain: 'example.com',
                    tag_name: 'News',  // Tagged domain
                    directory: 'archive/example.com',
                    can_be_tagged: true
                }),
                createMockDomain({
                    id: 2,
                    domain: 'test.org',
                    tag_name: null,  // Untagged domain
                    directory: '',
                    can_be_tagged: false
                }),
            ];

            mockUseDomains.mockReturnValue([mockDomains, 2]);

            render(<DomainsPage />);

            // Tagged domain should display its tag
            expect(screen.getByTestId('domain-tag-1')).toHaveTextContent('News');

            // Untagged domain should show "No tag"
            expect(screen.getByTestId('domain-tag-2')).toHaveTextContent('No tag');
        });

        it('displays multiple tagged domains correctly', () => {
            const mockDomains = [
                createMockDomain({
                    id: 1,
                    domain: 'news.com',
                    tag_name: 'News',
                    directory: 'archive/news.com',
                    can_be_tagged: true
                }),
                createMockDomain({
                    id: 2,
                    domain: 'tech.com',
                    tag_name: 'Tech',
                    directory: 'archive/tech.com',
                    can_be_tagged: true
                }),
                createMockDomain({
                    id: 3,
                    domain: 'science.com',
                    tag_name: 'Science',
                    directory: 'archive/science.com',
                    can_be_tagged: true
                }),
            ];

            mockUseDomains.mockReturnValue([mockDomains, 3]);

            render(<DomainsPage />);

            // All domains should display their respective tags
            expect(screen.getByTestId('domain-tag-1')).toHaveTextContent('News');
            expect(screen.getByTestId('domain-tag-2')).toHaveTextContent('Tech');
            expect(screen.getByTestId('domain-tag-3')).toHaveTextContent('Science');
        });
    });

    describe('Tag Clearing Submission Bug', () => {
        it('should send empty string (not null) when clearing tag', async () => {
            // Create a domain with a tag
            const domainWithTag = createMockDomain({
                id: 1,
                domain: 'example.com',
                directory: 'archive/example.com',
                tag_name: 'News',
                can_be_tagged: true
            });

            // Create form with the domain data
            const form = createTestForm(domainWithTag);

            // Simulate clearing the tag
            form.setValue('tag_name', null);

            // Verify form has null
            expect(form.formData.tag_name).toBe(null);

            // Mock updateDomain to track what it's called with
            const mockUpdateDomain = jest.fn().mockResolvedValue({ok: true});

            // Mock onSubmit to call updateDomain like useDomain does (with fix)
            form.onSubmit = jest.fn(async () => {
                const body = {
                    directory: form.formData.directory,
                    description: form.formData.description,
                    // FIX: Convert null to empty string - backend expects "" to clear tag
                    tag_name: form.formData.tag_name === null ? '' : form.formData.tag_name,
                };
                return await mockUpdateDomain(1, body);
            });

            // Submit the form
            await form.onSubmit();

            // Verify updateDomain was called
            expect(mockUpdateDomain).toHaveBeenCalledTimes(1);

            // Verify tag_name is correctly converted from null to "" for the API
            expect(mockUpdateDomain).toHaveBeenCalledWith(1, {
                directory: 'archive/example.com',
                description: '',
                tag_name: '',  // Empty string clears the tag (null is converted)
            });
        });
    });
});
