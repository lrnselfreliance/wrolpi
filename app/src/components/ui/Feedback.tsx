import React from 'react';
import {Loader as MLoader, Skeleton} from '@mantine/core';
import {Icon} from './Icon';
import {SemanticColorName} from '../../themes/mantine';

/*
 * Feedback: messages, labels, progress, status text, loaders.
 *
 * These carry the design rules that change form (not just color) between
 * themes, so their markup is ours and their values come from tokens.
 */

// ------------------------------------------------------------------ Messages

export type MessageKind = 'info' | 'success' | 'warning' | 'error';

const messageColors: Record<MessageKind, string> = {
    info: 'var(--blue)',
    success: 'var(--green)',
    warning: 'var(--amber)',
    error: 'var(--red)',
};

export interface MessageProps {
    kind?: MessageKind;
    title?: React.ReactNode;
    children?: React.ReactNode;
    /** Semantic icon name or a Tabler component, shown to the left of the text. */
    icon?: string | React.ComponentType<any>;
    /** Renders a dismiss button.  Omit for messages the user cannot clear. */
    onDismiss?: () => void;
    className?: string;
}

export function Message({kind = 'info', title, children, icon, onDismiss, className}: MessageProps) {
    return <div
        // Errors and warnings interrupt; info and success are announced politely.
        role={kind === 'error' ? 'alert' : 'status'}
        className={['wrolpi-message', kind === 'error' ? 'wrolpi-message-error' : '', className]
            .filter(Boolean).join(' ')}
        style={{['--message-color' as string]: messageColors[kind]}}
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
    color?: SemanticColorName | 'black' | 'white';
    icon?: string | React.ComponentType<any>;
    children?: React.ReactNode;
    onClick?: React.MouseEventHandler<HTMLSpanElement>;
    className?: string;
}

/** A tag/chip.  Filled in light and dark; an outline in night, where a filled
 *  patch would be a bright surface. */
export function Label({color = 'grey', icon, children, onClick, className}: LabelProps) {
    return <span
        className={['wrolpi-label', `wrolpi-label-${color}`, className].filter(Boolean).join(' ')}
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
    color?: SemanticColorName;
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
    return <span className={`wrolpi-status wrolpi-status-${kind}`}>
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
 * Replaces Semantic's `<Loader active inline='centered'>`, which 19 call sites
 * used with their own wrapper div.
 */
export function Loading({children, size = 'sm', padding = '2em'}: LoadingProps) {
    return <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, padding,
    }}>
        <Loader size={size} label={typeof children === 'string' ? children : undefined}/>
        {children && <div style={{fontSize: 13, color: 'var(--muted)'}}>{children}</div>}
    </div>
}

/** Placeholder for content that has not arrived.  Replaces Semantic's Placeholder. */
export function Placeholder({lines = 3, height = 12}: {lines?: number; height?: number}) {
    return <div style={{display: 'flex', flexDirection: 'column', gap: 8}}>
        {Array.from({length: lines}, (_, index) => <Skeleton
            key={index}
            height={height}
            // A ragged last line reads as text rather than a block.
            width={index === lines - 1 ? '60%' : '100%'}
            radius={0}
            animate
        />)}
    </div>
}

export {Skeleton};
