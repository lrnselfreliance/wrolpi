import React from 'react';
import {Table as MTable, TableProps as MTableProps} from '@mantine/core';
import {Icon} from './Icon';

/*
 * Tables.
 *
 * Rows are separated by a horizontal rule and nothing else.  There are no column
 * borders: a full grid draws a line around every cell, which is a lot of ink to
 * say something the column headings already say, and it made the header row --
 * which had no surface of its own -- read as one more cell in the grid.  The
 * header now carries `--head` and a full-strength rule under it, and the rules
 * between body rows are `--table-line`, deliberately fainter.  See ui.css.
 *
 * Wide tables scroll in their own container so the page body never scrolls
 * sideways.
 *
 * Compound: Table.Header / Body / Row / Cell / HeaderCell / Footer, so the markup at
 * a call site reads the way the rendered table is structured.
 */

export interface TableProps extends MTableProps {
    /** Wrap in a horizontally scrollable container.  On by default. */
    scrollable?: boolean;
}

function TableBase({scrollable = true, ...props}: TableProps) {
    const table = <MTable
        withTableBorder
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

export type SortDirection = 'ascending' | 'descending';

export interface HeaderCellProps extends React.ComponentPropsWithoutRef<'th'> {
    /** This column's current sort, or null/undefined when it is not the sorted one. */
    sorted?: SortDirection | null;
    /** Makes the header a sort control.  Receives nothing; the caller knows its column. */
    onSort?: () => void;
}

/**
 * A header cell, optionally a sort control.
 *
 * When `onSort` is given the label becomes a real `<button>` — a click handler on
 * the `<th>` alone is unreachable by keyboard — and the cell carries `aria-sort`,
 * so the sort state is announced rather than left to the arrow glyph.
 */
function HeaderCell({sorted, onSort, children, ...props}: HeaderCellProps) {
    if (!onSort) return <MTable.Th {...props}>{children}</MTable.Th>

    return <MTable.Th
        // `none` (not omitted) on the other columns tells assistive tech they are
        // sortable but not currently sorted.
        aria-sort={sorted ? sorted : 'none'}
        {...props}
    >
        <button type='button' className='wrolpi-th-sort' onClick={onSort}>
            {children}
            <Icon
                name={sorted === 'descending' ? 'arrow down' : 'arrow up'}
                size={14}
                className={sorted ? undefined : 'wrolpi-th-sort-idle'}
            />
        </button>
    </MTable.Th>
}

export const Table = Object.assign(TableBase, {
    Header: MTable.Thead,
    Body: MTable.Tbody,
    Footer: MTable.Tfoot,
    Row,
    Cell,
    HeaderCell,
    // Mantine's own names, for new code.
    Thead: MTable.Thead,
    Tbody: MTable.Tbody,
    Tfoot: MTable.Tfoot,
    Tr: Row,
    Td: Cell,
    Th: HeaderCell,
    ScrollContainer: MTable.ScrollContainer,
});
