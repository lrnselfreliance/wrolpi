import React from 'react';
import {Card as MCard, Tabs as MTabs, Accordion as MAccordion, Breadcrumbs} from '@mantine/core';

/*
 * Surfaces and structure: panels, cards, statistics, tabs, accordions,
 * breadcrumbs.  Elevation is expressed with borders and background steps —
 * never a shadow (shadows are zeroed in the Mantine bridge).
 */

// -------------------------------------------------------------------- Panels

export interface PanelProps extends React.HTMLAttributes<HTMLDivElement> {
    /** A danger zone: dashed red border, for destructive groupings. */
    danger?: boolean;
}

/** A bordered surface.  Replaces Semantic's Segment. */
export function Panel({danger, className, children, ...props}: PanelProps) {
    return <div
        className={['wrolpi-panel', danger ? 'wrolpi-panel-danger' : '', className]
            .filter(Boolean).join(' ')}
        {...props}
    >
        {children}
    </div>
}

// ---------------------------------------------------------------- Statistics

export interface StatisticProps {
    value: React.ReactNode;
    label: React.ReactNode;
    color?: string;
}

export function Statistic({value, label, color}: StatisticProps) {
    return <div>
        <div className='wrolpi-statistic-value' style={{color: color ? `var(--${color})` : undefined}}>
            {value}
        </div>
        <div className='wrolpi-statistic-label'>{label}</div>
    </div>
}

/** A row of statistics separated by hairlines, sharing one outer border. */
export function StatisticGroup({children}: {children: React.ReactNode}) {
    const items = React.Children.toArray(children);
    return <div style={{
        display: 'grid',
        gridTemplateColumns: `repeat(auto-fit, minmax(150px, 1fr))`,
        border: '1px solid var(--border)',
    }}>
        {items.map((child, index) => <div
            key={index}
            style={{
                background: 'var(--panel)',
                padding: '14px 16px',
                borderRight: index === items.length - 1 ? undefined : '1px solid var(--border)',
            }}
        >
            {child}
        </div>)}
    </div>
}

// --------------------------------------------------------------------- Cards

export interface CardProps {
    /** Image or poster area above the body. */
    media?: React.ReactNode;
    title?: React.ReactNode;
    meta?: React.ReactNode;
    children?: React.ReactNode;
    onClick?: React.MouseEventHandler<HTMLDivElement>;
    className?: string;
}

export function Card({media, title, meta, children, onClick, className}: CardProps) {
    return <MCard
        withBorder
        padding={0}
        className={className}
        onClick={onClick}
        style={{
            background: 'var(--panel)',
            borderColor: 'var(--border)',
            cursor: onClick ? 'pointer' : undefined,
            display: 'flex',
            flexDirection: 'column',
        }}
    >
        {media && <div style={{borderBottom: '1px solid var(--border)'}}>{media}</div>}
        <div style={{padding: '10px 12px 12px', display: 'flex', flexDirection: 'column', gap: 4, flex: 1}}>
            {title && <div style={{fontSize: 13, fontWeight: 600, lineHeight: 1.35}}>{title}</div>}
            {children}
            {meta && <div style={{fontSize: 12, color: 'var(--muted)', marginTop: 'auto'}}>{meta}</div>}
        </div>
    </MCard>
}

export function CardGroup({children, minWidth = 200}: {children: React.ReactNode; minWidth?: number}) {
    return <div style={{
        display: 'grid',
        gridTemplateColumns: `repeat(auto-fill, minmax(${minWidth}px, 1fr))`,
        gap: 14,
    }}>
        {children}
    </div>
}

export {MTabs as Tabs, MAccordion as Accordion, Breadcrumbs};
