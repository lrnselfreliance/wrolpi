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
     * A token color name (`green`, `red`, ...) for a heading that carries meaning —
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
    /** A token color name, for a reading that carries meaning: load, temperature, IO wait. */
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
    /**
     * The card's secondary line -- author, channel, domain, date.  It sits directly under
     * the title rather than at the foot of the card: a grid stretches every card to the
     * tallest in its row, so a foot-anchored meta line strands the date a long way from
     * the title it belongs to.
     */
    meta?: React.ReactNode;
    children?: React.ReactNode;
    /**
     * Controls, rendered last and pushed to the card's foot so that a row of cards lines
     * its buttons up regardless of how many lines each title took.
     */
    actions?: React.ReactNode;
    onClick?: React.MouseEventHandler<HTMLDivElement>;
    /**
     * A token color name, drawn as an accent along the card's top edge.  File cards use
     * it to carry the mimetype's color, so a grid of results is scannable by kind before
     * any text is read.  It remaps per theme, so night gets a red accent rather than a
     * dozen hues.
     */
    color?: string;
    className?: string;
}

export function Card({media, title, meta, children, actions, onClick, color, className}: CardProps) {
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
        {/* Sizes live in ui.css, in rem: inline px would sit outside the interface scale. */}
        <div className='wrolpi-card-body'>
            {title && <div className='wrolpi-card-title'>{title}</div>}
            {meta && <div className='wrolpi-card-meta'>{meta}</div>}
            {children}
            {actions && <div className='wrolpi-card-actions'>
                {actions}
            </div>}
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
            /*
             * Converted to rem so a column grows with the interface scale.  As px it did not,
             * and a 430px phone fitted two 200px cards where the pre-migration build fitted
             * one 290px card -- the narrowest card in the app, on the smallest screen.
             *
             * The prop stays a px number: seven call sites pass one, and a caller thinking in
             * px is thinking about the unscaled design.
             */
            gridTemplateColumns: `repeat(auto-fill, minmax(${minWidth / 16}rem, 1fr))`,
            ...style,
        }}
        {...props}
    >
        {children}
    </div>
}

export {MTabs as Tabs, MAccordion as Accordion, Breadcrumbs};
