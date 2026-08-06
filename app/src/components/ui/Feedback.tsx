import React from 'react';
import {Loader as MLoader, Skeleton} from '@mantine/core';
import {Icon} from './Icon';
import {pxToRem} from './scale';
import {RoleName, PaletteColorName} from '../../themes/mantine';

/*
 * Feedback: messages, labels, progress, status text, loaders.
 *
 * These carry the design rules that change form (not just color) between
 * themes, so their markup is ours and their values come from tokens.
 */

// ------------------------------------------------------------------ Messages

/*
 * `error` is the original spelling and stays: 26 call sites use it, and renaming those
 * is app-level churn for no behaviour change.  `danger` is the same thing under the
 * name the token uses, and is what new code should write.
 */
export type MessageKind = 'info' | 'success' | 'warning' | 'error' | 'danger';

/** The role each kind means.  Never a hue -- see the note on roles in tokens.css. */
const messageRoles: Record<MessageKind, RoleName> = {
    info: 'info',
    success: 'success',
    warning: 'warning',
    error: 'danger',
    danger: 'danger',
};

export interface MessageProps {
    kind?: MessageKind;
    title?: React.ReactNode;
    children?: React.ReactNode;
    /** An icon name (see Icon.tsx) or a Tabler component, shown to the left of the text. */
    icon?: string | React.ComponentType<any>;
    /** Renders a dismiss button.  Omit for messages the user cannot clear. */
    onDismiss?: () => void;
    className?: string;
}

export function Message({kind = 'info', title, children, icon, onDismiss, className}: MessageProps) {
    return <div
        // Errors and warnings interrupt; info and success are announced politely.
        role={messageRoles[kind] === 'danger' ? 'alert' : 'status'}
        className={['wrolpi-message', messageRoles[kind] === 'danger' ? 'wrolpi-message-error' : '', className]
            .filter(Boolean).join(' ')}
        style={{['--message-color' as string]: `var(--${messageRoles[kind]})`}}
    >
        {icon && <div className='wrolpi-message-icon'>
            {typeof icon === 'string' ? <Icon name={icon} size={20}/> : <Icon component={icon} size={20}/>}
        </div>}
        <div className='wrolpi-message-content'>
            {title && <div className='wrolpi-message-title'>{title}</div>}
            {children && <div className='wrolpi-message-body'>{children}</div>}
        </div>
        {onDismiss && <button
            type='button'
            className='wrolpi-message-dismiss'
            aria-label='Dismiss'
            onClick={onDismiss}
        >
            <Icon name='close' size={16}/>
        </button>}
    </div>
}

// -------------------------------------------------------------------- Labels

export interface LabelProps {
    color?: PaletteColorName | RoleName | 'black' | 'white';
    icon?: string | React.ComponentType<any>;
    /**
     * Draw it as a physical tag — pointed left edge and an eyelet — rather than a plain
     * chip.  Reserved for things that actually are tags: the same component also carries
     * the count badges in the Tags table, and a point on a number reads as an arrow.
     */
    tag?: boolean;
    children?: React.ReactNode;
    onClick?: React.MouseEventHandler<HTMLSpanElement>;
    className?: string;
}

/** A chip.  Filled in light, dark and amber; an outline in night, where a filled
 *  patch would be a bright surface. */
export function Label({color = 'grey', icon, tag, children, onClick, className}: LabelProps) {
    return <span
        className={['wrolpi-label', `wrolpi-label-${color}`, tag ? 'wrolpi-tag' : '', className]
            .filter(Boolean).join(' ')}
        style={{['--label-color' as string]: `var(--${color})`, cursor: onClick ? 'pointer' : undefined}}
        onClick={onClick}
    >
        {icon && (typeof icon === 'string' ? <Icon name={icon} size={14}/> : <Icon component={icon} size={14}/>)}
        {children}
    </span>
}

// ------------------------------------------------------------------ Progress

export interface ProgressProps {
    /** 0-100.  Values outside the range are clamped. */
    percent?: number;
    /**
     * Work is happening but its size is unknown — an upload that has not reported yet.
     * Animates instead of sitting at 0%, which otherwise reads as stalled.
     */
    indeterminate?: boolean;
    /** Show the percentage inside the bar. */
    showPercent?: boolean;
    color?: PaletteColorName | RoleName;
    /** Replaces the percentage with arbitrary text (e.g. "2.1 GB / 5.3 GB"). */
    label?: React.ReactNode;
    className?: string;
}

export function Progress({
    percent = 0, showPercent = true, color = 'blue', label, indeterminate, className,
}: ProgressProps) {
    const clamped = Math.min(100, Math.max(0, Number.isFinite(percent) ? percent : 0));
    return <div
        className={['wrolpi-progress', indeterminate ? 'wrolpi-progress-indeterminate' : '', className]
            .filter(Boolean).join(' ')}
        role='progressbar'
        // An indeterminate bar reports no value, which is what tells assistive tech the
        // amount is unknown rather than zero.
        aria-valuenow={indeterminate ? undefined : Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
    >
        <div
            className='wrolpi-progress-fill'
            style={{
                width: indeterminate ? undefined : `${clamped}%`,
                ['--progress-color' as string]: `var(--${color})`,
            }}
        />
        {(showPercent || label) && <span className='wrolpi-progress-text'>
            {label ?? `${Math.round(clamped)}%`}
        </span>}
    </div>
}

// -------------------------------------------------------------------- Status

export type StatusKind = 'complete' | 'active' | 'pending' | 'failed';

/*
 * Status was the one component already doing this correctly: it had per-theme overrides
 * in ui.css because night has no hues to distinguish four states with.  Those are gone --
 * the roles carry the brightness ramp now, so this table is the whole of it and every
 * theme is served by the same rule.
 */
const statusRoles: Record<StatusKind, RoleName> = {
    complete: 'success',
    active: 'info',
    pending: 'neutral',
    failed: 'danger',
};

const statusIcons: Record<StatusKind, string> = {
    complete: 'check',
    active: 'circle notch',
    pending: 'circle',
    failed: 'x',
};

export interface StatusProps {
    kind: StatusKind;
    children?: React.ReactNode;
    /** Hide the leading icon. */
    plain?: boolean;
}

/**
 * Status text.  Encoded by hue in light and dark; night mode has no hue to
 * spend, so brightness carries it (see ui.css).  Callers name the state, never
 * the color.
 */
export function Status({kind, children, plain}: StatusProps) {
    return <span
        className={`wrolpi-status wrolpi-status-${kind}`}
        style={{['--status-color' as string]: `var(--${statusRoles[kind]})`}}
    >
        {!plain && <Icon name={statusIcons[kind]} size={14} loading={kind === 'active'}/>}
        {children}
    </span>
}

// ------------------------------------------------------------------- Loaders

export interface LoaderProps {
    size?: number | 'xs' | 'sm' | 'md' | 'lg' | 'xl';
    label?: string;
}

export function Loader({size = 'sm', label}: LoaderProps) {
    return <MLoader size={size} color='var(--blue)' aria-label={label ?? 'Loading'}/>
}

export interface LoadingProps {
    /** What is being waited on: "Loading backups…".  Also the accessible name. */
    children?: React.ReactNode;
    size?: LoaderProps['size'];
    /** Vertical padding around the loader. */
    padding?: number | string;
}

/**
 * A centered loader with a caption, for a region that has nothing to show yet.
 * A centred spinner with optional text under it.  The wrapper is the component's,
 * so the 19 call sites that show one do not each roll their own.
 */
export function Loading({children, size = 'sm', padding = '2em'}: LoadingProps) {
    // `padding` is the caller's, so it stays inline; the rest is in ui.css so it scales.
    return <div className='wrolpi-loading' style={{padding}}>
        <Loader size={size} label={typeof children === 'string' ? children : undefined}/>
        {children && <div className='wrolpi-loading-caption'>{children}</div>}
    </div>
}

/** Placeholder for content that has not arrived: a few skeleton lines. */
export function Placeholder({lines = 3, height = 12}: {lines?: number; height?: number}) {
    return <div className='wrolpi-placeholder'>
        {Array.from({length: lines}, (_, index) => <Skeleton
            key={index}
            // In rem so a placeholder line matches the height of the text it stands in for.
            height={pxToRem(height)}
            // A ragged last line reads as text rather than a block.
            width={index === lines - 1 ? '60%' : '100%'}
            radius={0}
            animate
        />)}
    </div>
}

export {Skeleton};
