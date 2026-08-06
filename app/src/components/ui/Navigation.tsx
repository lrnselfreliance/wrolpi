import React from 'react';
import {Pagination as MPagination} from '@mantine/core';

/*
 * Navigation: pagination and tab bars.
 *
 * Neither knows anything about routing — the app owns its links.  The tab bar
 * takes rendered children and supplies only the strip and its house style, so
 * call sites keep using react-router's NavLink and its `isActive` render prop.
 */

// --------------------------------------------------------------- Pagination

export interface PaginationProps {
    /** 1-based. */
    activePage: number;
    totalPages?: number;
    onPageChange: (page: number) => void;
    /** Pages shown either side of the active one.  Fewer on a phone. */
    siblingRange?: number;
    /** Include jump-to-first and jump-to-last controls. */
    showFirstAndLast?: boolean;
    size?: string;
    disabled?: boolean;
}

/**
 * Page controls: `activePage`, `totalPages`, `onPageChange`.  `onPageChange` receives
 * the page number directly.
 */
export function Pagination({
    activePage,
    totalPages,
    onPageChange,
    siblingRange = 2,
    showFirstAndLast = false,
    size = 'sm',
    disabled,
}: PaginationProps) {
    return <MPagination
        className='wrolpi-pagination'
        value={activePage}
        // A single empty page still renders, so the control never collapses to nothing
        // and shift the layout when results arrive.
        total={totalPages || 1}
        onChange={onPageChange}
        siblings={siblingRange}
        withEdges={showFirstAndLast}
        size={size}
        disabled={disabled}
        radius={0}
        getItemProps={page => ({'aria-label': `Page ${page}`})}
    />
}

// ----------------------------------------------------------------- Tab bars

/** A row of tabs.  Children are the links; routing stays with the caller. */
export function TabBar({children, right}: {children: React.ReactNode; right?: React.ReactNode}) {
    return <nav className='wrolpi-tabs'>
        <div className='wrolpi-tabs-links'>{children}</div>
        {right && <div className='wrolpi-tabs-right'>{right}</div>}
    </nav>
}

/**
 * Class name for one tab.  Exported rather than baked into a component so a
 * caller can hand it straight to NavLink's `className` render prop, which is
 * how the app decides what is active.
 */
export const tabClassName = (active: boolean): string =>
    `wrolpi-tab${active ? ' wrolpi-tab-active' : ''}`;
