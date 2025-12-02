import React from 'react';
import {render, screen, renderInDarkMode, renderInLightMode, hasInvertedStyling} from '../../test-utils';
import {CollectionTable} from './CollectionTable';
import {createMockMetadata, createMockDomains} from '../../test-utils';

// Mock the TagsContext
jest.mock('../../Tags', () => ({
    TagsContext: {
        _currentValue: {
            SingleTag: ({name}) => <span data-testid="single-tag">{name}</span>
        }
    },
}));

// Mock the Media component to test both mobile and desktop views
jest.mock('../../contexts/contexts', () => ({
    ...jest.requireActual('../../contexts/contexts'),
    Media: ({children, at, greaterThanOrEqual}) => {
        // Default to desktop view for most tests
        if (greaterThanOrEqual === 'tablet') {
            return <div data-testid="desktop-view">{children}</div>;
        }
        if (at === 'mobile') {
            return <div data-testid="mobile-view">{children}</div>;
        }
        return children;
    },
}));

// Mock SortableTable to simplify testing
jest.mock('../SortableTable', () => ({
    SortableTable: ({data, rowFunc, tableHeaders}) => (
        <table data-testid="sortable-table">
            <thead>
                <tr>
                    {tableHeaders.map(h => (
                        <th key={h.key} data-width={h.width}>{h.text}</th>
                    ))}
                </tr>
            </thead>
            <tbody>
                {data.map(item => rowFunc(item))}
            </tbody>
        </table>
    ),
}));

describe('CollectionTable', () => {
    const mockMetadata = createMockMetadata();
    const mockCollections = createMockDomains(3);

    describe('Loading and Error States', () => {
        it('renders loading placeholder when collections is null', () => {
            const {container} = render(
                <CollectionTable
                    collections={null}
                    metadata={mockMetadata}
                />
            );

            expect(container.querySelector('.ui.placeholder')).toBeInTheDocument();
        });

        it('renders error message when collections is undefined', () => {
            render(
                <CollectionTable
                    collections={undefined}
                    metadata={mockMetadata}
                />
            );

            expect(screen.getByText(/could not fetch collections/i)).toBeInTheDocument();
        });

        it('renders empty message when collections is empty array', () => {
            render(
                <CollectionTable
                    collections={[]}
                    metadata={mockMetadata}
                />
            );

            expect(screen.getByText(/no items yet/i)).toBeInTheDocument();
        });

        it('renders custom empty message', () => {
            render(
                <CollectionTable
                    collections={[]}
                    metadata={mockMetadata}
                    emptyMessage="No domains found"
                />
            );

            expect(screen.getByText(/no domains found/i)).toBeInTheDocument();
        });

        it('renders warning when metadata is null', () => {
            render(
                <CollectionTable
                    collections={mockCollections}
                    metadata={null}
                />
            );

            expect(screen.getByText(/no metadata available/i)).toBeInTheDocument();
        });
    });

    describe('Table Rendering', () => {
        it('renders table with collection data', () => {
            render(
                <CollectionTable
                    collections={mockCollections}
                    metadata={mockMetadata}
                />
            );

            // Should render the sortable table
            expect(screen.getAllByTestId('sortable-table')).toHaveLength(2); // mobile + desktop
        });

        it('renders correct number of rows', () => {
            render(
                <CollectionTable
                    collections={mockCollections}
                    metadata={mockMetadata}
                />
            );

            // Each collection should have a row in desktop view
            const desktopView = screen.getByTestId('desktop-view');
            const rows = desktopView.querySelectorAll('tbody tr');
            expect(rows).toHaveLength(mockCollections.length);
        });

        it('renders Edit links for each collection', () => {
            render(
                <CollectionTable
                    collections={mockCollections}
                    metadata={mockMetadata}
                />
            );

            const editLinks = screen.getAllByText('Edit');
            // Should have edit links for both mobile and desktop views
            expect(editLinks.length).toBeGreaterThan(0);
        });
    });

    describe('Search Filtering', () => {
        it('filters collections by search string', () => {
            render(
                <CollectionTable
                    collections={mockCollections}
                    metadata={mockMetadata}
                    searchStr="example1"
                />
            );

            const desktopView = screen.getByTestId('desktop-view');
            const rows = desktopView.querySelectorAll('tbody tr');
            // Should only show matching collection
            expect(rows).toHaveLength(1);
        });

        it('shows all collections when search string is empty', () => {
            render(
                <CollectionTable
                    collections={mockCollections}
                    metadata={mockMetadata}
                    searchStr=""
                />
            );

            const desktopView = screen.getByTestId('desktop-view');
            const rows = desktopView.querySelectorAll('tbody tr');
            expect(rows).toHaveLength(mockCollections.length);
        });

        it('handles case-insensitive search', () => {
            render(
                <CollectionTable
                    collections={mockCollections}
                    metadata={mockMetadata}
                    searchStr="EXAMPLE1"
                />
            );

            const desktopView = screen.getByTestId('desktop-view');
            const rows = desktopView.querySelectorAll('tbody tr');
            expect(rows).toHaveLength(1);
        });
    });

    describe('Column Width Calculation', () => {
        it('calculates widths for 5-column metadata', () => {
            render(
                <CollectionTable
                    collections={mockCollections}
                    metadata={mockMetadata}
                />
            );

            const desktopView = screen.getByTestId('desktop-view');
            const headers = desktopView.querySelectorAll('th');

            // Mock metadata has 5 columns: domain, archive_count, size, tag_name, actions
            // archive_count (right-aligned)=2, size (bytes)=2, tag_name=2, actions=1
            // Total fixed = 7, remaining = 16 - 7 = 9 for domain
            expect(headers[0]).toHaveAttribute('data-width', '9');

            // Actions column should be 1
            const actionsHeader = Array.from(headers).find(h => h.textContent === 'Manage');
            expect(actionsHeader).toHaveAttribute('data-width', '1');
        });

        it('calculates widths for 4-column metadata', () => {
            const fourColumnMetadata = {
                ...mockMetadata,
                columns: [
                    {key: 'name', label: 'Name', sortable: true},
                    {key: 'count', label: 'Count', sortable: true, align: 'right'},
                    {key: 'size', label: 'Size', sortable: true, format: 'bytes'},
                    {key: 'actions', label: 'Manage', type: 'actions'},
                ]
            };

            render(
                <CollectionTable
                    collections={mockCollections}
                    metadata={fourColumnMetadata}
                />
            );

            const desktopView = screen.getByTestId('desktop-view');
            const headers = desktopView.querySelectorAll('th');

            // count (right-aligned)=2, size (bytes)=2, actions=1
            // Total fixed = 5, remaining = 16 - 5 = 11 for name
            expect(headers[0]).toHaveAttribute('data-width', '11');
        });

        it('distributes space among multiple grow columns', () => {
            const twoGrowMetadata = {
                ...mockMetadata,
                columns: [
                    {key: 'name', label: 'Name', sortable: true},
                    {key: 'description', label: 'Description', sortable: false},
                    {key: 'actions', label: 'Manage', type: 'actions'},
                ]
            };

            render(
                <CollectionTable
                    collections={mockCollections}
                    metadata={twoGrowMetadata}
                />
            );

            const desktopView = screen.getByTestId('desktop-view');
            const headers = desktopView.querySelectorAll('th');

            // actions=1, remaining = 15 / 2 grow columns = 7 each
            expect(headers[0]).toHaveAttribute('data-width', '7');
            expect(headers[1]).toHaveAttribute('data-width', '7');
        });
    });

    describe('Row Click Handler', () => {
        it('calls onRowClick when row is clicked', () => {
            const mockOnRowClick = jest.fn();

            render(
                <CollectionTable
                    collections={mockCollections}
                    metadata={mockMetadata}
                    onRowClick={mockOnRowClick}
                />
            );

            const desktopView = screen.getByTestId('desktop-view');
            const firstRow = desktopView.querySelector('tbody tr');
            firstRow.click();

            expect(mockOnRowClick).toHaveBeenCalledWith(mockCollections[0]);
        });

        it('adds clickable class when onRowClick is provided', () => {
            const mockOnRowClick = jest.fn();

            render(
                <CollectionTable
                    collections={mockCollections}
                    metadata={mockMetadata}
                    onRowClick={mockOnRowClick}
                />
            );

            const desktopView = screen.getByTestId('desktop-view');
            const firstRow = desktopView.querySelector('tbody tr');
            expect(firstRow).toHaveClass('clickable');
        });

        it('does not add clickable class when onRowClick is not provided', () => {
            render(
                <CollectionTable
                    collections={mockCollections}
                    metadata={mockMetadata}
                />
            );

            const desktopView = screen.getByTestId('desktop-view');
            const firstRow = desktopView.querySelector('tbody tr');
            expect(firstRow).not.toHaveClass('clickable');
        });
    });

    describe('Value Formatting', () => {
        it('formats bytes values using humanFileSize', () => {
            const collectionsWithSize = [{
                id: 1,
                domain: 'test.com',
                size: 1048576, // 1 MB
                archive_count: 5,
            }];

            render(
                <CollectionTable
                    collections={collectionsWithSize}
                    metadata={mockMetadata}
                />
            );

            // humanFileSize(1048576) should return "1.0 MB"
            // Multiple elements found (mobile + desktop), use getAllByText
            const sizeElements = screen.getAllByText(/1\.0 MB/i);
            expect(sizeElements.length).toBeGreaterThan(0);
        });

        it('renders SingleTag for tag_name column', () => {
            const collectionsWithTag = [{
                id: 1,
                domain: 'test.com',
                tag_name: 'News',
                size: 1000,
                archive_count: 5,
            }];

            render(
                <CollectionTable
                    collections={collectionsWithTag}
                    metadata={mockMetadata}
                />
            );

            expect(screen.getAllByTestId('single-tag')[0]).toHaveTextContent('News');
        });
    });

    describe('Links', () => {
        it('renders search link on primary column when searchParam is configured', () => {
            const metadataWithSearchParam = {
                ...mockMetadata,
                routes: {
                    ...mockMetadata.routes,
                    searchParam: 'domain'
                }
            };

            render(
                <CollectionTable
                    collections={mockCollections}
                    metadata={metadataWithSearchParam}
                />
            );

            // Domain column should link to search with domain parameter
            const desktopView = screen.getByTestId('desktop-view');
            const domainLink = desktopView.querySelector('a[href*="domain="]');
            expect(domainLink).toBeInTheDocument();
        });

        it('renders edit link in actions column', () => {
            render(
                <CollectionTable
                    collections={mockCollections}
                    metadata={mockMetadata}
                />
            );

            const editLinks = screen.getAllByRole('link', {name: /edit/i});
            expect(editLinks.length).toBeGreaterThan(0);
            expect(editLinks[0]).toHaveAttribute('href', expect.stringContaining('/edit'));
        });
    });
});
