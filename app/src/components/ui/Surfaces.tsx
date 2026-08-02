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
    /**
     * Trailing content on the heading's row — a help button, a count, a small control.
     *
     * It is a SIBLING of the heading element inside a flex row, not a child of it: a
     * control inside an `<h3>` becomes part of the heading's accessible name, so screen
     * reader heading navigation announces "Root CA Certificate Help".  The row is what
     * keeps the two on one line; a sibling placed after the block wrapper wraps instead,
     * which is what happened to every help icon in the app when these headings stopped
     * being a bare `<h3>`.
     */
    after?: React.ReactNode;
}

/**
 * A section heading.  Named and shaped like Semantic's Header (`as`, `icon`,
 * `subheader`, `dividing`) so the app's 47 call sites migrate by import.
 *
 * Sizes come from ui.css, keyed on the level, rather than each call site
 * choosing — that is what keeps the type scale a scale.
 */
export function Header({
    as = 'h3', icon, subheader, dividing, color, after, className, style, children, ...props
}: HeaderProps) {
    const Tag = as;
    const heading = <Tag
        className={`wrolpi-header-text wrolpi-header-${as}`}
        style={color ? {color: `var(--${color})`} : undefined}
        {...props}
    >
        {icon && (typeof icon === 'string'
            ? <Icon name={icon} size='medium'/>
            : <Icon component={icon} size='medium'/>)}
        <span>{children}</span>
    </Tag>;

    /*
     * `style` lands on the WRAPPER, because every layout use of it is about the header as a
     * block -- `marginBottom` on Status's "Drive Bandwidth", `marginTop` on the extension
     * page's steps.  On the inner heading those set a margin inside the wrapper and depended
     * on margin collapse to have any effect at all, which stops the moment the wrapper gains
     * padding or a border.  Text properties passed this way still reach the heading: `color`
     * and `text-align` inherit.  A `color` PROP stays on the heading, since that is about the
     * text rather than the box.
     */
    return <div
        className={['wrolpi-header', dividing ? 'wrolpi-header-dividing' : '', className]
            .filter(Boolean).join(' ')}
        style={style}
    >
        {/* The row exists only when there is something to sit beside; without it the
            markup for the other 46 call sites is unchanged. */}
        {after
            ? <div className='wrolpi-header-row'>
                {heading}
                <span className='wrolpi-header-after'>{after}</span>
            </div>
            : heading}
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

export interface StatisticProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'color'> {
    /** The number.  Rendered as given, so `0` shows as a zero rather than nothing. */
    value: React.ReactNode;
    label: React.ReactNode;
    /** A token colour name, for a reading that carries meaning: load, temperature, IO wait. */
    color?: string;
}

/**
 * One figure and its label.  The rest of the props reach the outer element, because
 * `LoadStatistic` and the four Status wrappers all end in `{...props}` and used to have
 * everything past the named five silently dropped.
 */
export function Statistic({value, label, color, className, ...props}: StatisticProps) {
    return <div className={['wrolpi-statistic', className].filter(Boolean).join(' ')} {...props}>
        <div className='wrolpi-statistic-value' style={{color: color ? `var(--${color})` : undefined}}>
            {value}
        </div>
        <div className='wrolpi-statistic-label'>{label}</div>
    </div>
}

/**
 * A row of statistics separated by hairlines, sharing one outer border.  The cells carry
 * no inline style of their own so that `.wrolpi-statistic-cell:empty` can hide the ones
 * whose statistic rendered nothing — Status omits the fan reading on the devices, most of
 * them, with no fan connector.
 */
export function StatisticGroup({children, className, ...props}: React.HTMLAttributes<HTMLDivElement>) {
    return <div className={['wrolpi-statistic-group', className].filter(Boolean).join(' ')} {...props}>
        {React.Children.toArray(children).map((child, index) =>
            <div key={index} className='wrolpi-statistic-cell'>{child}</div>)}
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
            // Along the bottom, where it does not compete with the poster's top edge.
            borderBottom: color ? `3px solid var(--${color})` : undefined,
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

export interface CardGroupProps extends React.HTMLAttributes<HTMLDivElement> {
    /**
     * The narrowest a card may be laid out.  `auto-fill` rather than `auto-fit`, so a group
     * of two cards in a wide column keeps them card-sized instead of stretching each to half
     * the page.
     */
    minWidth?: number;
}

export function CardGroup({children, minWidth = 200, className, style, ...props}: CardGroupProps) {
    return <div
        className={['wrolpi-card-group', className].filter(Boolean).join(' ')}
        style={{
            display: 'grid',
            gridTemplateColumns: `repeat(auto-fill, minmax(${minWidth}px, 1fr))`,
            gap: 14,
            ...style,
        }}
        {...props}
    >
        {children}
    </div>
}

export {MTabs as Tabs, MAccordion as Accordion, Breadcrumbs};
