import React, {useContext} from 'react';
import {Link} from 'react-router-dom';
import {Message, Placeholder, PlaceholderHeader, PlaceholderLine, Table, TableCell, TableRow} from 'semantic-ui-react';
import _ from 'lodash';
import {SortableTable} from '../SortableTable';
import {humanFileSize} from '../Common';
import {ThemeContext, Media} from '../../contexts/contexts';
import {TagsContext} from '../../Tags';
import {allFrequencyOptions} from '../Vars';

/**
 * Format a frequency value (in seconds) to a human-readable string using allFrequencyOptions.
 * @param {number|null} frequency - Frequency in seconds
 * @returns {string} Human-readable frequency text or '-' if null/undefined
 */
function formatFrequency(frequency) {
    if (frequency === null || frequency === undefined) {
        return '-';
    }
    const option = allFrequencyOptions[frequency];
    return option ? option.text : `${frequency}s`;
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
        // Use id_field if specified (e.g., channel_id for channels), otherwise use id
        const idField = metadata.routes.id_field || 'id';
        return searchRoute.replace(':id', collection[idField]);
    }

    // No linking strategy available
    return null;
}

/**
 * Mobile row component for collections
 */
function MobileCollectionRow({collection, metadata}) {
    const {SingleTag} = useContext(TagsContext);
    const primaryColumn = metadata.columns[0];
    // Use id_field if specified (e.g., channel_id for channels), otherwise use id
    const idField = metadata.routes?.id_field || 'id';
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

    // Build row renderer based on metadata
    const renderRow = (collection) => {
        const cells = metadata.columns.map(col => {
            let value = collection[col.key];

            // Handle actions column - render action buttons
            if (col.type === 'actions') {
                // Use id_field if specified (e.g., channel_id for channels), otherwise use id
                const idField = metadata.routes?.id_field || 'id';
                const editRoute = metadata.routes?.edit?.replace(':id', collection[idField]);
                const buttonClass = `ui button secondary ${inverted}`;
                return <Table.Cell key={col.key} textAlign={col.align || 'right'}>
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

            return <Table.Cell key={col.key} textAlign={col.align || 'left'}>
                {value || '-'}
            </Table.Cell>;
        });

        return <Table.Row
            key={collection.id}
            onClick={() => onRowClick && onRowClick(collection)}
            style={onRowClick ? {cursor: 'pointer'} : {}}
        >
            {cells}
        </Table.Row>;
    };

    // Build table headers from metadata (desktop)
    const headers = metadata.columns.map((col, index) => {
        // Determine width based on column position and type
        // Widths use Semantic UI's 16-column grid system and should sum to 16
        let width = null;
        if (index === 0) {
            // First column (name/domain) - gets most space to expand
            // For 6 columns: 16 - (2+2+2+2+1) = 7
            width = 7;
        } else if (col.type === 'actions') {
            // Actions column - minimum width to shrink to fit button
            width = 1;
        } else {
            // Other columns (tags, counts, frequency, sizes)
            width = 2;
        }

        return {
            key: col.key,
            text: col.label,
            sortBy: col.sortable ? col.key : null,
            width: width,
        };
    });

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
                rowFunc={(collection) => renderRow(collection)}
                rowKey='id'
                tableHeaders={headers}
                defaultSortColumn={defaultSortColumn}
            />
        </Media>
    </>;
}
