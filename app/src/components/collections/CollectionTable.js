import React, {useContext} from 'react';
import {Link} from 'react-router-dom';
import {Message, Placeholder, PlaceholderHeader, PlaceholderLine, Table, TableCell, TableRow} from 'semantic-ui-react';
import _ from 'lodash';
import {SortableTable} from '../SortableTable';
import {humanFileSize, formatFrequency} from '../Common';
import {ThemeContext, Media} from '../../contexts/contexts';
import {TagsContext} from '../../Tags';

/**
 * Get the ID field from metadata routes configuration.
 * @param {Object} metadata - Collection metadata
 * @returns {string} The ID field name
 */
function getIdField(metadata) {
    return metadata?.routes?.id_field || 'id';
}

/**
 * Calculate column widths based on column metadata.
 * Uses Semantic UI's 16-column grid system.
 *
 * @param {Array} columns - Array of column configurations
 * @returns {Array} Array of width values (1-16)
 */
function calculateColumnWidths(columns) {
    const TOTAL = 16;

    const widths = columns.map(col => {
        if (col.type === 'actions') return 1;
        if (col.format === 'bytes' || col.format === 'frequency') return 2;
        if (col.align === 'right') return 2; // numeric columns
        if (col.key === 'tag_name') return 2;
        return null; // grow column - calculate later
    });

    // Distribute remaining space to null (grow) columns
    const fixedWidth = widths.filter(w => w !== null).reduce((a, b) => a + b, 0);
    const growColumns = widths.filter(w => w === null).length;
    const growWidth = Math.floor((TOTAL - fixedWidth) / (growColumns || 1));

    return widths.map(w => w === null ? growWidth : w);
}

/**
 * Generate a search link for a collection based on metadata routing configuration.
 * Supports both query parameter-based (e.g., ?domain=...) and route-based (e.g., /channel/:id/video) linking.
 *
 * @param {Object} collection - The collection object
 * @param {Object} metadata - Collection metadata with routes configuration
 * @param {string} primaryKey - The primary column key to use for the value
 * @returns {string|null} The generated link, or null if no link can be generated
 */
function getCollectionSearchLink(collection, metadata, primaryKey) {
    const searchRoute = metadata.routes?.search;
    if (!searchRoute) {
        return null;
    }

    // Check if metadata specifies a query parameter to use
    if (metadata.routes.searchParam) {
        // Query parameter-based linking (e.g., /archive?domain=example.com)
        return `${searchRoute}?${metadata.routes.searchParam}=${collection[primaryKey]}`;
    } else if (searchRoute.includes(':id')) {
        // Route parameter-based linking (e.g., /videos/channel/123/video)
        const idField = getIdField(metadata);
        return searchRoute.replace(':id', collection[idField]);
    }

    // No linking strategy available
    return null;
}

/**
 * Render a single table row for desktop view.
 *
 * @param {Object} collection - The collection data
 * @param {Object} metadata - Collection metadata
 * @param {string} inverted - Inverted theme class
 * @param {Function} SingleTag - Tag component from context
 * @param {Function} onRowClick - Optional click handler
 * @param {Array} columnWidths - Calculated column widths
 */
function renderRow(collection, metadata, inverted, SingleTag, onRowClick, columnWidths) {
    const cells = metadata.columns.map((col, index) => {
        let value = collection[col.key];

        // Handle actions column - render action buttons
        if (col.type === 'actions') {
            const idField = getIdField(metadata);
            const editRoute = metadata.routes?.edit?.replace(':id', collection[idField]);
            const buttonClass = `ui button secondary ${inverted}`;
            return <Table.Cell key={col.key} textAlign={col.align || 'right'} width={columnWidths[index]}>
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
            value = <SingleTag name={value} />;
        }

        // Special handling for the primary column (usually domain/name)
        if (col.key === metadata.columns[0].key) {
            const searchLink = getCollectionSearchLink(collection, metadata, col.key);
            if (searchLink) {
                value = <Link to={searchLink}>{value}</Link>;
            }
        }

        return <Table.Cell key={col.key} textAlign={col.align || 'left'} width={columnWidths[index]}>
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
 * Mobile row component for collections
 */
function MobileCollectionRow({collection, metadata}) {
    const {SingleTag} = useContext(TagsContext);
    const primaryColumn = metadata.columns[0];
    const idField = getIdField(metadata);
    const editRoute = metadata.routes?.edit?.replace(':id', collection[idField]);
    const searchLink = getCollectionSearchLink(collection, metadata, primaryColumn.key);

    return <TableRow verticalAlign='top'>
        <TableCell width={10} colSpan={2}>
            {searchLink ? (
                <Link as='h3' to={searchLink}>
                    <h3>
                        {collection[primaryColumn.key]}
                    </h3>
                    {collection.tag_name && <SingleTag name={collection.tag_name}/>}
                </Link>
            ) : (
                <>
                    <h3>{collection[primaryColumn.key]}</h3>
                    {collection.tag_name && <SingleTag name={collection.tag_name}/>}
                </>
            )}
            {metadata.columns
                .filter(col => col.type !== 'actions' && col.key !== primaryColumn.key && col.key !== 'tag_name')
                .map(col => {
                    let value = collection[col.key];
                    if (col.format === 'bytes') {
                        value = humanFileSize(value);
                    } else if (col.format === 'frequency') {
                        value = formatFrequency(value);
                    }
                    return (
                        <p key={col.key}>
                            {col.label}: {value || '-'}
                        </p>
                    );
                })
            }
        </TableCell>
        <TableCell width={6} colSpan={2} textAlign='right'>
            <p>
                {editRoute && <Link className="ui button secondary" to={editRoute}>Edit</Link>}
            </p>
        </TableCell>
    </TableRow>;
}

/**
 * Reusable table component for displaying collections (Domains, Channels, etc).
 *
 * @param {Array} collections - Array of collection objects
 * @param {Object} metadata - Backend-provided metadata containing columns, routes, etc.
 * @param {String} searchStr - Search filter string (managed by parent)
 * @param {Function} onRowClick - Optional callback when a row is clicked
 * @param {String} emptyMessage - Message to display when there are no collections
 */
export function CollectionTable({collections, metadata, searchStr = '', onRowClick, emptyMessage = 'No items yet'}) {
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

    // No metadata available (backward compatibility)
    if (!metadata) {
        return <Message warning>
            <Message.Header>No metadata available</Message.Header>
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

    // Calculate column widths dynamically
    const columnWidths = calculateColumnWidths(metadata.columns);

    // Build table headers from metadata (desktop)
    const headers = metadata.columns.map((col, index) => ({
        key: col.key,
        text: col.label,
        sortBy: col.sortable ? col.key : null,
        width: columnWidths[index],
    }));

    // Build mobile headers - simplified columns
    const primaryColumn = metadata.columns[0];
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

    // Get default sort column from metadata (first column key)
    const defaultSortColumn = metadata.columns[0]?.key || 'id';


    return <>
        <Media at='mobile'>
            <SortableTable
                tableProps={{striped: true, size: 'small', unstackable: true}}
                data={filteredCollections}
                rowFunc={(collection) => <MobileCollectionRow key={collection.id} collection={collection} metadata={metadata}/>}
                rowKey='id'
                tableHeaders={mobileHeaders}
                defaultSortColumn={defaultSortColumn}
            />
        </Media>
        <Media greaterThanOrEqual='tablet'>
            <SortableTable
                tableProps={{striped: true, size: 'large', unstackable: true, compact: true}}
                data={filteredCollections}
                rowFunc={(collection) => renderRow(collection, metadata, inverted, SingleTag, onRowClick, columnWidths)}
                rowKey='id'
                tableHeaders={headers}
                defaultSortColumn={defaultSortColumn}
            />
        </Media>
    </>;
}
