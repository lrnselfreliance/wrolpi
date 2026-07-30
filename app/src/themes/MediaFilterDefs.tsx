import React from 'react';

/**
 * SVG filter definitions used by monochrome themes to remap media that cannot
 * consume theme tokens: video, images, PDFs, embedded pages, canvases.
 *
 * Mounted once, near the app root.  See tokens.css for the `.media` rule that
 * applies these, and ui-design.md for the night-vision rationale.
 */
export function MediaFilterDefs() {
    return <svg
        aria-hidden='true'
        focusable='false'
        style={{position: 'absolute', width: 0, height: 0, overflow: 'hidden'}}
    >
        <defs>
            {/*
              Night: luminance -> red channel, green and blue driven to zero, so
              every filtered pixel lights only the red subpixel.  The gamma lift
              brightens midtones; red is perceptually dim, and without it text on
              a filtered document or PDF is unreadable.
            */}
            <filter id='wrolpi-night-red' colorInterpolationFilters='sRGB'>
                <feColorMatrix
                    type='matrix'
                    values='0.2126 0.7152 0.0722 0 0
                            0      0      0      0 0
                            0      0      0      0 0
                            0      0      0      1 0'
                />
                <feComponentTransfer>
                    <feFuncR type='gamma' amplitude='1' exponent='0.65' offset='0'/>
                </feComponentTransfer>
            </filter>

            {/*
              Amber: the same luminance collapse, then tinted to the theme's amber
              (#ff9500) by scaling each channel to that hue's ratios — red at full,
              green at 0.584, blue at zero.  Amber carries far more luminance than
              red, so it needs a gentler lift; 0.85 keeps highlights from clipping
              to a flat wash.

              This is opt-in: amber is a look, not a night-vision aid.
            */}
            <filter id='wrolpi-amber-mono' colorInterpolationFilters='sRGB'>
                <feColorMatrix
                    type='matrix'
                    values='0.2126 0.7152 0.0722 0 0
                            0.1242 0.4177 0.0422 0 0
                            0      0      0      0 0
                            0      0      0      1 0'
                />
                <feComponentTransfer>
                    <feFuncR type='gamma' amplitude='1' exponent='0.85' offset='0'/>
                    <feFuncG type='gamma' amplitude='1' exponent='0.85' offset='0'/>
                </feComponentTransfer>
            </filter>
        </defs>
    </svg>
}
