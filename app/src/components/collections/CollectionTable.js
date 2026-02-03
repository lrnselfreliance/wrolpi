import React, {useContext} from 'react';
import {Link} from 'react-router';
import {Message, PlaceholderHeader, PlaceholderLine, TableCell, TableRow} from 'semantic-ui-react';
import {Placeholder, Table} from '../Theme';
import _ from 'lodash';
import {SortableTable} from '../SortableTable';
import {formatFrequency, humanFileSize} from '../Common';
import {Media, ThemeContext} from '../../contexts/contexts';
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
 * Render a single table row for desktop view.
 *
 * @param {Object} collection - The collection data
 * @param {Array} columns - Column configurations
 * @param {Object} routes - Routes configuration
 * @param {string} inverted - Inverted theme class
 * @param {Function} SingleTag - Tag component from context
 * @param {Function} onRowClick - Optional click handler
 */
function renderRow(collection, columns, routes, inverted, SingleTag, onRowClick) {
    const cells = columns.map((col) => {
        let value = collection[col.key];

        // Handle actions column - render action buttons
        if (col.type === 'actions') {
            const idField = getIdField(routes);
            const editRoute = routes?.edit?.replace(':id', collection[idField]);
            const buttonClass = `ui button secondary ${inverted}`;
            return <Table.Cell key={col.key} textAlign={col.align || 'right'} width={col.width}>
                {editRoute && <Link className={buttonClass} to={editRoute}>Edit</Link>}
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

        return <Table.Cell key={col.key} textAlign={col.align || 'left'} width={col.width}>
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

    return <TableRow verticalAlign='top'>
        <TableCell>
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
        </TableCell>
        <TableCell textAlign='right'>
            {editRoute && <Link className="ui button secondary" to={editRoute}>Edit</Link>}
        </TableCell>
    </TableRow>;
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
    const {inverted} = useContext(ThemeContext);
    const {SingleTag} = useContext(TagsContext);

    // Loading state
    if (collections === null) {
        return <Placeholder>
            <PlaceholderHeader>
                <PlaceholderLine/>
                <PlaceholderLine/>
            </PlaceholderHeader>
        </Placeholder>;
    }

    // Error state
    if (collections === undefined) {
        return <Message error>
            <Message.Header>Could not fetch collections</Message.Header>
        </Message>;
    }

    // Empty state
    if (collections && collections.length === 0) {
        return <Message>
            <Message.Header>{emptyMessage}</Message.Header>
        </Message>;
    }

    // No columns configured
    if (!columns || columns.length === 0) {
        return <Message warning>
            <Message.Header>No columns configured</Message.Header>
        </Message>;
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
                tableProps={{striped: true, size: 'small', unstackable: true}}
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
                tableProps={{striped: true, size: 'large', unstackable: true, compact: true}}
                data={filteredCollections}
                rowFunc={(collection) => renderRow(collection, columns, routes, inverted, SingleTag, onRowClick)}
                rowKey='id'
                tableHeaders={headers}
                defaultSortColumn={defaultSortColumn}
            />
        </Media>
    </>;
}
