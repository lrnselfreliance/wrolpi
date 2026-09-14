import React from 'react';

export interface SparklineProps {
    /** The series, oldest first.  Non-finite values are drawn as gaps. */
    values: Array<number | null | undefined>;
    /** Fixed vertical ceiling; defaults to the series maximum so the line fills the box. */
    max?: number;
    /** Token color name (`blue`, `green`, `warning`…).  Resolves through `var(--name)`. */
    color?: string;
    /** Pixel height.  Width always fills the container. */
    height?: number;
    /** Draw a faint fill under the line. */
    area?: boolean;
    /** Accessible summary, e.g. "Download throughput over the last 10 seconds". */
    label?: string;
    className?: string;
}

/** A tiny inline-SVG line chart with no axes; the figure beside it carries the scale. */
export function Sparkline({values, max, color = 'blue', height = 48, area = true, label, className}: SparklineProps) {
    const width = 100;  // viewBox units; the SVG stretches to its container.
    const finite = values.map(v => (typeof v === 'number' && Number.isFinite(v) ? v : null));
    const ceiling = max && max > 0 ? max : Math.max(1e-9, ...finite.map(v => v ?? 0));
    const n = finite.length;
    const step = n > 1 ? width / (n - 1) : width;
    const pad = 2;
    const usable = height - pad * 2;

    // Break the polyline at gaps so a lost sample shows as missing rather than a plunge.
    const segments: string[] = [];
    let current: string[] = [];
    finite.forEach((v, i) => {
        if (v === null) {
            if (current.length) {
                segments.push(current.join(' '));
                current = [];
            }
            return;
        }
        const x = n > 1 ? i * step : width;
        const y = pad + usable - (Math.min(v, ceiling) / ceiling) * usable;
        current.push(`${x.toFixed(2)},${y.toFixed(2)}`);
    });
    if (current.length) {
        segments.push(current.join(' '));
    }

    const stroke = `var(--${color})`;

    return <svg
        className={['wrolpi-sparkline', className].filter(Boolean).join(' ')}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio='none'
        width='100%'
        height={height}
        role='img'
        aria-label={label}
        style={{display: 'block', overflow: 'visible'}}
    >
        {/* Baseline so an empty or flat-zero series still shows something is being drawn. */}
        <line x1={0} y1={height - pad} x2={width} y2={height - pad}
              stroke='var(--border)' strokeWidth={1} vectorEffect='non-scaling-stroke'/>
        {area && segments.map((points, i) => {
            const coords = points.split(' ');
            const first = coords[0].split(',')[0];
            const last = coords[coords.length - 1].split(',')[0];
            return <polygon key={`a${i}`}
                            points={`${first},${height - pad} ${points} ${last},${height - pad}`}
                            fill={stroke} opacity={0.15}/>;
        })}
        {segments.map((points, i) => <polyline key={i} points={points} fill='none' stroke={stroke}
                                                strokeWidth={2} strokeLinejoin='round' strokeLinecap='round'
                                                vectorEffect='non-scaling-stroke'/>)}
    </svg>;
}
