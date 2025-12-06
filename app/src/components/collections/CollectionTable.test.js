import React from 'react';
import {render, screen, renderInDarkMode, renderInLightMode, hasInvertedStyling} from '../../test-utils';
import {CollectionTable} from './CollectionTable';
import {createMockDomains} from '../../test-utils';

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

// Test column and routes configurations
const DOMAIN_COLUMNS = [
    {key: 'domain', label: 'Domain', sortable: true, width: 7},
    {key: 'archive_count', label: 'Archives', sortable: true, align: 'right', width: 2},
    {key: 'size', label: 'Size', sortable: true, align: 'right', format: 'bytes', width: 2, hideOnMobile: true},
    {key: 'tag_name', label: 'Tag', sortable: true, width: 2},
    {key: 'actions', label: 'Manage', sortable: false, type: 'actions', width: 1}
];

const DOMAIN_ROUTES = {
    list: '/archive/domains',
    edit: '/archive/domain/:id/edit',
    search: '/archive',
    searchParam: 'domain'
};

describe('CollectionTable', () => {
    const mockCollections = createMockDomains(3);

    describe('Loading and Error States', () => {
        it('renders loading placeholder when collections is null', () => {
            const {container} = render(
                <CollectionTable
                    collections={null}
                    columns={DOMAIN_COLUMNS}
                    routes={DOMAIN_ROUTES}
                />
            );

            expect(container.querySelector('.ui.placeholder')).toBeInTheDocument();
        });

        it('renders error message when collections is undefined', () => {
            render(
                <CollectionTable
                    collections={undefined}
                    columns={DOMAIN_COLUMNS}
                    routes={DOMAIN_ROUTES}
                />
            );

            expect(screen.getByText(/could not fetch collections/i)).toBeInTheDocument();
        });

        it('renders empty message when collections is empty array', () => {
            render(
                <CollectionTable
                    collections={[]}
                    columns={DOMAIN_COLUMNS}
                    routes={DOMAIN_ROUTES}
                />
            );

            expect(screen.getByText(/no items yet/i)).toBeInTheDocument();
        });

        it('renders custom empty message', () => {
            render(
                <CollectionTable
                    collections={[]}
                    columns={DOMAIN_COLUMNS}
                    routes={DOMAIN_ROUTES}
                    emptyMessage="No domains found"
                />
            );

            expect(screen.getByText(/no domains found/i)).toBeInTheDocument();
        });

        it('renders warning when columns is null', () => {
            render(
                <CollectionTable
                    collections={mockCollections}
                    columns={null}
                    routes={DOMAIN_ROUTES}
                />
            );

            expect(screen.getByText(/no columns configured/i)).toBeInTheDocument();
        });

        it('renders warning when columns is empty', () => {
            render(
                <CollectionTable
                    collections={mockCollections}
                    columns={[]}
                    routes={DOMAIN_ROUTES}
                />
            );

            expect(screen.getByText(/no columns configured/i)).toBeInTheDocument();
        });
    });

    describe('Table Rendering', () => {
        it('renders table with collection data', () => {
            render(
                <CollectionTable
                    collections={mockCollections}
                    columns={DOMAIN_COLUMNS}
                    routes={DOMAIN_ROUTES}
                />
            );

            // Should render the sortable table
            expect(screen.getAllByTestId('sortable-table')).toHaveLength(2); // mobile + desktop
        });

        it('renders correct number of rows', () => {
            render(
                <CollectionTable
                    collections={mockCollections}
                    columns={DOMAIN_COLUMNS}
                    routes={DOMAIN_ROUTES}
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
                    columns={DOMAIN_COLUMNS}
                    routes={DOMAIN_ROUTES}
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
                    columns={DOMAIN_COLUMNS}
                    routes={DOMAIN_ROUTES}
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
                    columns={DOMAIN_COLUMNS}
                    routes={DOMAIN_ROUTES}
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
                    columns={DOMAIN_COLUMNS}
                    routes={DOMAIN_ROUTES}
                    searchStr="EXAMPLE1"
                />
            );

            const desktopView = screen.getByTestId('desktop-view');
            const rows = desktopView.querySelectorAll('tbody tr');
            expect(rows).toHaveLength(1);
        });
    });

    describe('Column Widths', () => {
        it('uses explicit widths from column config', () => {
            render(
                <CollectionTable
                    collections={mockCollections}
                    columns={DOMAIN_COLUMNS}
                    routes={DOMAIN_ROUTES}
                />
            );

            const desktopView = screen.getByTestId('desktop-view');
            const headers = desktopView.querySelectorAll('th');

            // DOMAIN_COLUMNS has explicit widths: domain=7, archive_count=2, size=2, tag_name=2, actions=1
            expect(headers[0]).toHaveAttribute('data-width', '7');
            expect(headers[1]).toHaveAttribute('data-width', '2');
            expect(headers[2]).toHaveAttribute('data-width', '2');
            expect(headers[3]).toHaveAttribute('data-width', '2');
            expect(headers[4]).toHaveAttribute('data-width', '1');
        });

        it('uses widths from 4-column config', () => {
            const fourColumns = [
                {key: 'name', label: 'Name', sortable: true, width: 9},
                {key: 'count', label: 'Count', sortable: true, align: 'right', width: 2},
                {key: 'size', label: 'Size', sortable: true, format: 'bytes', width: 2},
                {key: 'actions', label: 'Manage', type: 'actions', width: 1},
            ];

            render(
                <CollectionTable
                    collections={mockCollections}
                    columns={fourColumns}
                    routes={DOMAIN_ROUTES}
                />
            );

            const desktopView = screen.getByTestId('desktop-view');
            const headers = desktopView.querySelectorAll('th');

            expect(headers[0]).toHaveAttribute('data-width', '9');
            expect(headers[1]).toHaveAttribute('data-width', '2');
            expect(headers[2]).toHaveAttribute('data-width', '2');
            expect(headers[3]).toHaveAttribute('data-width', '1');
        });
    });

    describe('Row Click Handler', () => {
        it('calls onRowClick when row is clicked', () => {
            const mockOnRowClick = jest.fn();

            render(
                <CollectionTable
                    collections={mockCollections}
                    columns={DOMAIN_COLUMNS}
                    routes={DOMAIN_ROUTES}
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
                    columns={DOMAIN_COLUMNS}
                    routes={DOMAIN_ROUTES}
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
                    columns={DOMAIN_COLUMNS}
                    routes={DOMAIN_ROUTES}
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
                    columns={DOMAIN_COLUMNS}
                    routes={DOMAIN_ROUTES}
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
                    columns={DOMAIN_COLUMNS}
                    routes={DOMAIN_ROUTES}
                />
            );

            expect(screen.getAllByTestId('single-tag')[0]).toHaveTextContent('News');
        });
    });

    describe('Mobile View', () => {
        it('hides columns with hideOnMobile in mobile view', () => {
            const collectionsWithData = [{
                id: 1,
                domain: 'test.com',
                archive_count: 5,
                size: 1048576,
                tag_name: 'News',
            }];

            render(
                <CollectionTable
                    collections={collectionsWithData}
                    columns={DOMAIN_COLUMNS}
                    routes={DOMAIN_ROUTES}
                />
            );

            const mobileView = screen.getByTestId('mobile-view');
            const mobileHeaders = mobileView.querySelectorAll('th');

            // Mobile uses simplified 2-column layout: primary column + Manage
            expect(mobileHeaders).toHaveLength(2);
            expect(mobileHeaders[0]).toHaveTextContent('Domain');
            expect(mobileHeaders[1]).toHaveTextContent('Manage');

            // Archives should be visible in row content (no hideOnMobile)
            expect(mobileView).toHaveTextContent('Archives:');

            // Size should be hidden in row content (hideOnMobile: true)
            expect(mobileView).not.toHaveTextContent('Size:');
        });
    });

    describe('Links', () => {
        it('renders search link on primary column when searchParam is configured', () => {
            render(
                <CollectionTable
                    collections={mockCollections}
                    columns={DOMAIN_COLUMNS}
                    routes={DOMAIN_ROUTES}
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
                    columns={DOMAIN_COLUMNS}
                    routes={DOMAIN_ROUTES}
                />
            );

            const editLinks = screen.getAllByRole('link', {name: /edit/i});
            expect(editLinks.length).toBeGreaterThan(0);
            expect(editLinks[0]).toHaveAttribute('href', expect.stringContaining('/edit'));
        });
    });
});
