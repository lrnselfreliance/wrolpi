import React from 'react';
import {Table as MTable, TableProps as MTableProps} from '@mantine/core';

/*
 * Tables.
 *
 * Borders do structural work here: full 1px cell borders, a `--head` header row,
 * and zebra striping.  Wide tables scroll in their own container so the page
 * body never scrolls sideways.
 *
 * The compound names mirror Semantic's (Header/Body/Row/Cell/HeaderCell/Footer)
 * so migrating a call site is a rename, not a rewrite.
 */

export interface TableProps extends MTableProps {
    /** Wrap in a horizontally scrollable container.  On by default. */
    scrollable?: boolean;
}

function TableBase({scrollable = true, ...props}: TableProps) {
    const table = <MTable
        withTableBorder
        withColumnBorders
        striped
        highlightOnHover={false}
        verticalSpacing={7}
        horizontalSpacing={10}
        {...props}
    />;
    return scrollable ? <div className='wrolpi-table-scroll'>{table}</div> : table;
}

export interface RowProps extends React.ComponentPropsWithoutRef<'tr'> {
    /** A failed row: takes the dashed danger border, in every theme. */
    failed?: boolean;
}

function Row({failed, className, ...props}: RowProps) {
    return <MTable.Tr
        className={[failed ? 'wrolpi-row-failed' : '', className].filter(Boolean).join(' ') || undefined}
        {...props}
    />
}

export interface CellProps extends React.ComponentPropsWithoutRef<'td'> {
    /** Right-align and use tabular figures, so digits line up in the column. */
    numeric?: boolean;
}

function Cell({numeric, style, ...props}: CellProps) {
    return <MTable.Td
        style={numeric ? {textAlign: 'right', fontVariantNumeric: 'tabular-nums', ...style} : style}
        {...props}
    />
}

export const Table = Object.assign(TableBase, {
    Header: MTable.Thead,
    Body: MTable.Tbody,
    Footer: MTable.Tfoot,
    Row,
    Cell,
    HeaderCell: MTable.Th,
    // Mantine's own names, for new code.
    Thead: MTable.Thead,
    Tbody: MTable.Tbody,
    Tfoot: MTable.Tfoot,
    Tr: Row,
    Td: Cell,
    Th: MTable.Th,
    ScrollContainer: MTable.ScrollContainer,
});
