import React from 'react';
import {render, screen, waitFor} from '../test-utils';
import {DomainsPage} from './Archive';
import {createMockDomains, createMockMetadata} from '../test-utils';

// Mock the custom hooks
jest.mock('../hooks/customHooks', () => ({
    ...jest.requireActual('../hooks/customHooks'),
    useDomains: jest.fn(),
    useOneQuery: jest.fn(),
}));

// Mock CollectionTable component
jest.mock('./collections/CollectionTable', () => ({
    CollectionTable: ({collections, metadata, searchStr}) => (
        <div data-testid="collection-table">
            <div data-testid="collection-count">{collections?.length || 0}</div>
            <div data-testid="search-filter">{searchStr}</div>
            {collections?.map((domain) => (
                <div key={domain.id} data-testid={`domain-${domain.id}`}>
                    <span data-testid={`domain-name-${domain.id}`}>{domain.domain}</span>
                    <button className="ui mini primary button" data-testid={`edit-button-${domain.id}`}>
                        Edit
                    </button>
                </div>
            ))}
        </div>
    ),
}));

// Mock SearchInput component and useTitle
jest.mock('./Common', () => ({
    ...jest.requireActual('./Common'),
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

describe('DomainsPage', () => {
    const {useDomains, useOneQuery} = require('../hooks/customHooks');
    const {useTitle} = require('./Common');
    const mockMetadata = createMockMetadata();

    beforeEach(() => {
        // Reset mocks before each test
        jest.clearAllMocks();

        // Default mock implementations
        useTitle.mockImplementation(() => {});
        useOneQuery.mockReturnValue(['', jest.fn()]);
    });

    describe('Page Rendering', () => {
        it('displays domains page without errors', () => {
            const mockDomains = createMockDomains(3);
            useDomains.mockReturnValue([mockDomains, 3, mockMetadata]);

            render(<DomainsPage />);

            // Page should render without crashing
            expect(screen.getByTestId('search-input')).toBeInTheDocument();
            expect(screen.getByTestId('collection-table')).toBeInTheDocument();
        });

        it('renders CollectionTable component', () => {
            const mockDomains = createMockDomains(2);
            useDomains.mockReturnValue([mockDomains, 2, mockMetadata]);

            render(<DomainsPage />);

            expect(screen.getByTestId('collection-table')).toBeInTheDocument();
        });

        it('shows search input', () => {
            const mockDomains = createMockDomains(1);
            useDomains.mockReturnValue([mockDomains, 1, mockMetadata]);

            render(<DomainsPage />);

            const searchInput = screen.getByTestId('search-input');
            expect(searchInput).toBeInTheDocument();
            expect(searchInput).toHaveAttribute('placeholder', 'Domain filter...');
        });
    });

    describe('Domain Display', () => {
        it('shows all domains from API', () => {
            const mockDomains = createMockDomains(5);
            useDomains.mockReturnValue([mockDomains, 5, mockMetadata]);

            render(<DomainsPage />);

            // Should render all 5 domains
            expect(screen.getByTestId('collection-count')).toHaveTextContent('5');

            mockDomains.forEach((domain) => {
                expect(screen.getByTestId(`domain-${domain.id}`)).toBeInTheDocument();
            });
        });

        it('displays domain names', () => {
            const mockDomains = [
                {id: 1, domain: 'example1.com', archive_count: 10, size: 1000},
                {id: 2, domain: 'example2.com', archive_count: 20, size: 2000},
                {id: 3, domain: 'example3.com', archive_count: 30, size: 3000},
            ];
            useDomains.mockReturnValue([mockDomains, 3, mockMetadata]);

            render(<DomainsPage />);

            expect(screen.getByTestId('domain-name-1')).toHaveTextContent('example1.com');
            expect(screen.getByTestId('domain-name-2')).toHaveTextContent('example2.com');
            expect(screen.getByTestId('domain-name-3')).toHaveTextContent('example3.com');
        });

        it('displays Edit buttons in Manage column', () => {
            const mockDomains = createMockDomains(3);
            useDomains.mockReturnValue([mockDomains, 3, mockMetadata]);

            render(<DomainsPage />);

            // Each domain should have an Edit button
            mockDomains.forEach((domain) => {
                expect(screen.getByTestId(`edit-button-${domain.id}`)).toBeInTheDocument();
            });
        });

        it('Edit button has correct styling', () => {
            const mockDomains = createMockDomains(1);
            useDomains.mockReturnValue([mockDomains, 1, mockMetadata]);

            render(<DomainsPage />);

            const editButton = screen.getByTestId('edit-button-1');
            expect(editButton).toHaveClass('ui');
            expect(editButton).toHaveClass('mini');
            expect(editButton).toHaveClass('primary');
            expect(editButton).toHaveClass('button');
        });
    });

    describe('Empty and Error States', () => {
        it('shows "No items yet" message when no domains', () => {
            // Empty array indicates no domains
            useDomains.mockReturnValue([[], 0, mockMetadata]);

            render(<DomainsPage />);

            // Should show empty state message
            expect(screen.getByText(/no domains yet/i)).toBeInTheDocument();
            expect(screen.getByText(/archive some webpages/i)).toBeInTheDocument();

            // Should not show table
            expect(screen.queryByTestId('collection-table')).not.toBeInTheDocument();
        });

        it('shows error message when fetch fails', () => {
            // undefined indicates error state
            useDomains.mockReturnValue([undefined, 0, mockMetadata]);

            render(<DomainsPage />);

            // Should show error message
            expect(screen.getByTestId('error-message')).toBeInTheDocument();
            expect(screen.getByText(/could not fetch domains/i)).toBeInTheDocument();

            // Should not show table
            expect(screen.queryByTestId('collection-table')).not.toBeInTheDocument();
        });

        it('does not show "New Domain" button', () => {
            const mockDomains = createMockDomains(2);
            useDomains.mockReturnValue([mockDomains, 2, mockMetadata]);

            render(<DomainsPage />);

            // Domains are auto-created, so there should be no "New" button
            expect(screen.queryByRole('button', {name: /new/i})).not.toBeInTheDocument();
            expect(screen.queryByRole('button', {name: /create/i})).not.toBeInTheDocument();
            expect(screen.queryByRole('button', {name: /add/i})).not.toBeInTheDocument();
        });
    });

    describe('Search Integration', () => {
        it('disables search when no domains', () => {
            useDomains.mockReturnValue([[], 0, mockMetadata]);

            render(<DomainsPage />);

            const searchInput = screen.getByTestId('search-input');
            expect(searchInput).toBeDisabled();
        });

        it('enables search when domains exist', () => {
            const mockDomains = createMockDomains(3);
            useDomains.mockReturnValue([mockDomains, 3, mockMetadata]);

            render(<DomainsPage />);

            const searchInput = screen.getByTestId('search-input');
            expect(searchInput).not.toBeDisabled();
        });

        it('passes search string to CollectionTable', () => {
            const mockDomains = createMockDomains(2);
            useDomains.mockReturnValue([mockDomains, 2, mockMetadata]);

            const mockSetSearchStr = jest.fn();
            useOneQuery.mockReturnValue(['example', mockSetSearchStr]);

            render(<DomainsPage />);

            // Search string should be passed to table
            expect(screen.getByTestId('search-filter')).toHaveTextContent('example');
        });
    });

    describe('Page Title', () => {
        it('sets page title correctly', () => {
            const mockDomains = createMockDomains(1);
            useDomains.mockReturnValue([mockDomains, 1, mockMetadata]);

            render(<DomainsPage />);

            expect(useTitle).toHaveBeenCalledWith('Archive Domains');
        });
    });
});
