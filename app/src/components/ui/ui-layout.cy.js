import React from 'react';
import {ActionInput, Button, PathInput, TextInput} from './index';
import {themeNames} from '../../themes/names';

/*
 * Layout and theming assertions for the component library, run in a real browser.
 *
 * These belong here rather than in ui.test.js because jsdom parses CSS but never lays it
 * out: getBoundingClientRect() returns zeros, getComputedStyle() will not resolve a custom
 * property through the cascade, and no filter is ever applied.  A jest test therefore
 * cannot tell whether two boxes overlap, whether a token resolved, or whether media got
 * tinted -- which is precisely how five unreadable inputs reached the Settings page.
 *
 * Keep this file to claims that need real layout.  Behaviour that jsdom can judge belongs
 * in ui.test.js, which runs in about two seconds against the whole library.
 */

describe('PathInput lays its prefix beside the value, never over it', () => {
    // Every theme, because a theme is free to restyle borders and padding, and the fix has
    // to hold in all four rather than in whichever one happened to be open.
    themeNames.forEach((theme) => {
        it(`keeps the prefix clear of the input in ${theme}`, () => {
            cy.mountUI(
                <PathInput
                    label='Archive Destination'
                    prefix='/media/wrolpi'
                    defaultValue='archive/%(domain)s'
                />,
                {theme},
            );

            cy.shouldNotOverlap('.wrolpi-path-input-prefix', '.wrolpi-path-input-control input');

            // Sharing one outline is the reason the pair reads as a single control; a gap
            // would mean the flex row broke and they are two separate fields again.
            cy.get('.wrolpi-path-input-prefix').then(($prefix) => {
                cy.get('.wrolpi-path-input-control input').then(($input) => {
                    const prefix = $prefix[0].getBoundingClientRect();
                    const input = $input[0].getBoundingClientRect();
                    expect(input.left - prefix.right, 'gap between prefix and input')
                        .to.be.closeTo(0, 2);
                });
            });
        });
    });

    it('shows the whole value, with room left to type', () => {
        cy.mountUI(
            <PathInput prefix='/media/wrolpi' defaultValue='archive/%(domain)s'/>,
        );

        /*
         * scrollWidth well beyond clientWidth means the value is cut off -- the visible
         * symptom when a prefix eats the input's usable width.  Both are rounded to whole
         * pixels from a fractional layout, so they disagree by a pixel on a field that fits
         * perfectly; the tolerance is for that, and is far below the tens of pixels a real
         * clip costs.
         */
        cy.get('.wrolpi-path-input-control input').should(($input) => {
            const el = $input[0];
            expect(el.scrollWidth, 'value is not clipped').to.be.at.most(el.clientWidth + 2);
            expect(el.clientWidth, 'input has usable width').to.be.greaterThan(80);
        });
    });

    it('detects the overlap that started this, so the check has teeth', () => {
        /*
         * The original defect, reproduced deliberately: Mantine turns leftSectionWidth into
         * --input-padding-inline-start, and `padding-inline-start: auto` is invalid, so it
         * resolves to zero and the absolutely-positioned section prints over the value.
         *
         * Asserting that this DOES overlap proves shouldNotOverlap is measuring something
         * real.  A geometry check that has never once gone red is indistinguishable from a
         * check that cannot fail.
         */
        cy.mountUI(
            <TextInput
                leftSectionWidth='auto'
                leftSection={<span className='probe-section'>/media/wrolpi</span>}
                defaultValue='archive/%(domain)s'
            />,
        );

        cy.get('.probe-section').then(($section) => {
            cy.get('input').then(($input) => {
                const section = $section[0].getBoundingClientRect();
                const input = $input[0].getBoundingClientRect();
                expect(
                    section.right > input.left + 0.5,
                    'the historical bug still overlaps, so the geometry check is meaningful',
                ).to.equal(true);
            });
        });
    });
});

describe('ActionInput', () => {
    it('joins its button to the field without covering it', () => {
        cy.mountUI(
            <ActionInput
                defaultValue='https://example.com'
                action={<Button>Fetch</Button>}
            />,
        );

        cy.shouldNotOverlap('.wrolpi-action-input input', '.wrolpi-action-input button');
    });
});

describe('theme tokens actually resolve', () => {
    themeNames.forEach((theme) => {
        it(`paints text and borders from ${theme}'s table`, () => {
            cy.mountUI(<PathInput prefix='/media/wrolpi' defaultValue='x'/>, {theme});

            /*
             * A token that a theme forgot to define resolves to the empty string, and the
             * property falls back to something inherited -- usually black text on a dark
             * panel.  jsdom cannot catch that; it does not resolve var() at all.
             */
            cy.get('.wrolpi-path-input-control input').should(($input) => {
                const colour = getComputedStyle($input[0]).color;
                expect(colour, 'input text colour resolved').to.match(/^rgba?\(/);
                // Only an rgba() alpha of zero is invisible.  Matching a trailing ", 0)"
                // loosely would flag amber's opaque rgb(255, 149, 0) for its blue channel.
                expect(colour, 'input text is not transparent')
                    .not.to.match(/^rgba\(.*,\s*0(\.0+)?\)$/);
            });

            cy.get('.wrolpi-path-input-control').should(($control) => {
                expect(getComputedStyle($control[0]).borderTopColor, 'border resolved')
                    .to.match(/^rgba?\(/);
            });
        });
    });
});

describe('media filtering', () => {
    it('tints a bare image in night', () => {
        cy.mountUI(<img alt='poster' src='/logo.png' width='80' height='80'/>,
            {theme: 'night', mediaFilter: 'night-red'});

        cy.get('img').should(($img) =>
            expect(getComputedStyle($img[0]).filter).to.contain('wrolpi-night-red'));
    });

    it('filters a .media wrapper once, not its contents twice', () => {
        /*
         * Two passes of a luminance-to-red matrix is not the same as one -- the second pass
         * takes the luminance of an already-red pixel and the image comes out markedly
         * darker than its surroundings.  So a `.media` wrapper is filtered as a unit and the
         * leaf inside it must come back `none`.
         */
        cy.mountUI(
            <div className='media'>
                <img alt='poster' src='/logo.png' width='80' height='80'/>
            </div>,
            {theme: 'night', mediaFilter: 'night-red'},
        );

        cy.get('.media').should(($wrapper) =>
            expect(getComputedStyle($wrapper[0]).filter).to.contain('wrolpi-night-red'));
        cy.get('.media img').should(($img) =>
            expect(getComputedStyle($img[0]).filter).to.equal('none'));
    });

    it('leaves media alone when the user has turned the filter off', () => {
        // The attribute is absent rather than empty when filtering is off, so night with the
        // setting disabled must match no rule at all.
        cy.mountUI(<img alt='poster' src='/logo.png' width='80' height='80'/>,
            {theme: 'night'});

        cy.get('img').should(($img) =>
            expect(getComputedStyle($img[0]).filter).to.equal('none'));
    });
});
