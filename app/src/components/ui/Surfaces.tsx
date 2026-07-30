import React from 'react';
import {Card as MCard, Tabs as MTabs, Accordion as MAccordion, Breadcrumbs} from '@mantine/core';
import {Icon} from './Icon';

/*
 * Surfaces and structure: headers, panels, cards, statistics, tabs, accordions,
 * breadcrumbs.  Elevation is expressed with borders and background steps —
 * never a shadow (shadows are zeroed in the Mantine bridge).
 */

// ------------------------------------------------------------------- Headers

export type HeaderLevel = 'h1' | 'h2' | 'h3' | 'h4' | 'h5';

export interface HeaderProps extends Omit<React.HTMLAttributes<HTMLHeadingElement>, 'color'> {
    /** Heading level.  Also the visual size — pick it for the outline, not the look. */
    as?: HeaderLevel;
    /** Semantic icon name or a Tabler component, shown before the text. */
    icon?: string | React.ComponentType<any>;
    /** Secondary line below, in muted text. */
    subheader?: React.ReactNode;
    /** Hairline rule underneath, separating the section from what follows. */
    dividing?: boolean;
    /**
     * A token colour name (`green`, `red`, ...) for a heading that carries meaning —
     * "3 items to add" against "2 items to remove".  Call sites kept reaching for an
     * inline style to do this, which is how a hex ends up in the markup.
     */
    color?: string;
}

/**
 * A section heading.  Named and shaped like Semantic's Header (`as`, `icon`,
 * `subheader`, `dividing`) so the app's 47 call sites migrate by import.
 *
 * Sizes come from ui.css, keyed on the level, rather than each call site
 * choosing — that is what keeps the type scale a scale.
 */
export function Header({
    as = 'h3', icon, subheader, dividing, color, className, style, children, ...props
}: HeaderProps) {
    const Tag = as;
    return <div className={['wrolpi-header', dividing ? 'wrolpi-header-dividing' : '', className]
        .filter(Boolean).join(' ')}>
        <Tag
            className={`wrolpi-header-text wrolpi-header-${as}`}
            style={color ? {color: `var(--${color})`, ...style} : style}
            {...props}
        >
            {icon && (typeof icon === 'string'
                ? <Icon name={icon} size='medium'/>
                : <Icon component={icon} size='medium'/>)}
            <span>{children}</span>
        </Tag>
        {subheader && <div className='wrolpi-header-sub'>{subheader}</div>}
    </div>
}

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
    className?: string;
    style?: React.CSSProperties;
}

export function Statistic({value, label, color, className, style}: StatisticProps) {
    return <div className={['wrolpi-statistic', className].filter(Boolean).join(' ')} style={style}>
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
            className='wrolpi-statistic-cell'
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
    /**
     * A token colour name, drawn as an accent along the card's top edge.  File cards use
     * it to carry the mimetype's colour, so a grid of results is scannable by kind before
     * any text is read.  It remaps per theme, so night gets a red accent rather than a
     * dozen hues.
     */
    color?: string;
    className?: string;
}

export function Card({media, title, meta, children, onClick, color, className}: CardProps) {
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
            // An accent edge rather than a tinted surface: the design rules keep surfaces
            // flat, and a 3px edge survives night mode without becoming a bright patch.
            borderTop: color ? `3px solid var(--${color})` : undefined,
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
