import React, {useContext} from 'react';
import {Link} from 'react-router';
import {Button, Message, Placeholder, Table} from '../ui';
import _ from 'lodash';
import {SortableTable} from '../SortableTable';
import {formatFrequency, humanFileSize} from '../Common';
import {Media} from '../../contexts/contexts';
import {TagsContext} from '../../Tags';

/**
 * Get the ID field from routes configuration.
 * @param {Object} routes - Routes configuration
 * @returns {string} The ID field name
 */
function getIdField(routes) {
    return routes?.id_field || 'id';
}

/**
 * Generate a search link for a collection based on routes configuration.
 * Supports both query parameter-based (e.g., ?domain=...) and route-based (e.g., /channel/:id/video) linking.
 *
 * @param {Object} collection - The collection object
 * @param {Object} routes - Routes configuration
 * @param {string} primaryKey - The primary column key to use for the value
 * @returns {string|null} The generated link, or null if no link can be generated
 */
function getCollectionSearchLink(collection, routes, primaryKey) {
    const searchRoute = routes?.search;
    if (!searchRoute) {
        return null;
    }

    // Check if routes specifies a query parameter to use
    if (routes.searchParam) {
        // Query parameter-based linking (e.g., /archive?domain=example.com)
        return `${searchRoute}?${routes.searchParam}=${collection[primaryKey]}`;
    } else if (searchRoute.includes(':id')) {
        // Route parameter-based linking (e.g., /videos/channel/123/video)
        const idField = getIdField(routes);
        return searchRoute.replace(':id', collection[idField]);
    }

    // No linking strategy available
    return null;
}

/**
 * Convert a relative column width (1-16, sixteenths) into a CSS percentage.
 * @param {number} width - Relative width, 1-16
 * @returns {Object|undefined} A style object, or undefined when no width is configured
 */
function widthStyle(width) {
    return width ? {width: `${(width / 16) * 100}%`} : undefined;
}

/**
 * Render a single table row for desktop view.
 *
 * @param {Object} collection - The collection data
 * @param {Array} columns - Column configurations
 * @param {Object} routes - Routes configuration
 * @param {Function} SingleTag - Tag component from context
 * @param {Function} onRowClick - Optional click handler
 */
function renderRow(collection, columns, routes, SingleTag, onRowClick) {
    const cells = columns.map((col) => {
        let value = collection[col.key];

        // Handle actions column - render action buttons
        if (col.type === 'actions') {
            const idField = getIdField(routes);
            const editRoute = routes?.edit?.replace(':id', collection[idField]);
            return <Table.Cell key={col.key} style={{textAlign: col.align || 'right', ...widthStyle(col.width)}}>
                {editRoute && <Button role='cancel' component={Link} to={editRoute} size='sm'>Edit</Button>}
            </Table.Cell>;
        }

        // Format the value based on column configuration
        if (col.format === 'bytes') {
            value = humanFileSize(value);
        } else if (col.format === 'frequency') {
            value = formatFrequency(value);
        }

        // Special handling for tag_name column - render SingleTag component
        if (col.key === 'tag_name' && value) {
            value = <SingleTag name={value}/>;
        }

        // Special handling for the primary column (usually domain/name)
        if (col.key === columns[0].key) {
            const searchLink = getCollectionSearchLink(collection, routes, col.key);
            if (searchLink) {
                value = <Link to={searchLink}>{value}</Link>;
            }
        }

        return <Table.Cell key={col.key} style={{textAlign: col.align || 'left', ...widthStyle(col.width)}}>
            {value || '-'}
        </Table.Cell>;
    });

    return <Table.Row
        key={collection.id}
        onClick={() => onRowClick && onRowClick(collection)}
        className={onRowClick ? 'clickable' : ''}
    >
        {cells}
    </Table.Row>;
}

/**
 * Mobile row component for collections - stacked layout for better wrapping of long names
 */
function MobileCollectionRow({collection, mobileColumns, routes}) {
    const {SingleTag} = useContext(TagsContext);
    const primaryColumn = mobileColumns[0];
    const idField = getIdField(routes);
    const editRoute = routes?.edit?.replace(':id', collection[idField]);
    const searchLink = getCollectionSearchLink(collection, routes, primaryColumn.key);

    return <Table.Row style={{verticalAlign: 'top'}}>
        <Table.Cell>
            {searchLink ? (
                <Link to={searchLink}>
                    <strong>{collection[primaryColumn.key]}</strong>
                </Link>
            ) : (
                <strong>{collection[primaryColumn.key]}</strong>
            )}
            {collection.tag_name && <> <SingleTag name={collection.tag_name}/></>}
            {mobileColumns
                .filter(col => col.type !== 'actions' && col.key !== primaryColumn.key && col.key !== 'tag_name')
                .map(col => {
                    let value = collection[col.key];
                    if (col.format === 'bytes') {
                        value = humanFileSize(value);
                    } else if (col.format === 'frequency') {
                        value = formatFrequency(value);
                    }
                    return (
                        <div key={col.key}>
                            {col.label}: {value || '-'}
                        </div>
                    );
                })
            }
        </Table.Cell>
        <Table.Cell style={{textAlign: 'right'}}>
            {editRoute && <Button role='cancel' component={Link} to={editRoute} size='sm'>Edit</Button>}
        </Table.Cell>
    </Table.Row>;
}

/**
 * Reusable table component for displaying collections (Domains, Channels, etc).
 *
 * @param {Array} collections - Array of collection objects
 * @param {Array} columns - Column configurations for the table
 * @param {Object} routes - Routes configuration for navigation (edit, search, etc.)
 * @param {String} searchStr - Search filter string (managed by parent)
 * @param {Function} onRowClick - Optional callback when a row is clicked
 * @param {String} emptyMessage - Message to display when there are no collections
 */
export function CollectionTable({
                                    collections,
                                    columns,
                                    routes = {},
                                    searchStr = '',
                                    onRowClick,
                                    emptyMessage = 'No items yet'
                                }) {
    const {SingleTag} = useContext(TagsContext);

    // Loading state
    if (collections === null) {
        return <Placeholder lines={2}/>;
    }

    // Error state
    if (collections === undefined) {
        return <Message kind='error' title='Could not fetch collections'/>;
    }

    // Empty state
    if (collections && collections.length === 0) {
        return <Message title={emptyMessage}/>;
    }

    // No columns configured
    if (!columns || columns.length === 0) {
        return <Message kind='warning' title='No columns configured'/>;
    }

    // Filter collections by search string
    let filteredCollections = collections;
    if (searchStr) {
        const re = new RegExp(_.escapeRegExp(searchStr), 'i');
        filteredCollections = collections.filter(collection => {
            // Search across all string fields
            return Object.values(collection).some(value => {
                if (typeof value === 'string') {
                    return re.test(value);
                }
                return false;
            });
        });
    }

    // Build table headers from columns (desktop)
    const headers = columns.map((col) => ({
        key: col.key,
        text: col.label,
        sortBy: col.sortable ? col.key : null,
        width: col.width,
    }));

    // Build mobile columns (exclude hideOnMobile) and simplified 2-column headers
    const mobileColumns = columns.filter(col => !col.hideOnMobile);
    const primaryColumn = columns[0];
    const mobileHeaders = [
        {
            key: primaryColumn.key,
            text: primaryColumn.label,
            sortBy: primaryColumn.sortable ? primaryColumn.key : null
        },
        {
            key: 'manage',
            text: 'Manage'
        }
    ];

    // Get default sort column (first column key)
    const defaultSortColumn = columns[0]?.key || 'id';


    return <>
        <Media at='mobile'>
            <SortableTable
                tableProps={{striped: true, size: 'sm'}}
                data={filteredCollections}
                rowFunc={(collection) => <MobileCollectionRow key={collection.id} collection={collection}
                                                              mobileColumns={mobileColumns} routes={routes}/>}
                rowKey='id'
                tableHeaders={mobileHeaders}
                defaultSortColumn={defaultSortColumn}
            />
        </Media>
        <Media greaterThanOrEqual='tablet'>
            <SortableTable
                tableProps={{striped: true, size: 'lg', verticalSpacing: 'xs'}}
                data={filteredCollections}
                rowFunc={(collection) => renderRow(collection, columns, routes, SingleTag, onRowClick)}
                rowKey='id'
                tableHeaders={headers}
                defaultSortColumn={defaultSortColumn}
            />
        </Media>
    </>;
}
