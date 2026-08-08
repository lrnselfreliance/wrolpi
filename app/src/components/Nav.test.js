import fs from 'fs';
import path from 'path';
import React from 'react';
import {screen} from '@testing-library/react';
import {render} from '../test-utils';
import {FileWorkerStatusContext} from '../contexts/FileWorkerStatusContext';
import {NavBar} from './Nav';

/*
 * Which navbar tab is marked as the current page.
 *
 * `NavLink` marks itself with `aria-current="page"` and an `active` class, and both need to
 * be right: the class is what the bar styles, and the attribute is what tells a screen
 * reader which section the user is in.
 *
 * The rule these tests encode is "a tab stays current for everything underneath it" --
 * /videos/1234 is still Videos.  That is `NavLink`'s default, so the tests exist to catch
 * an `end` prop added to a link that has pages beneath it, which silently drops the mark on
 * every one of those pages.
 */

beforeEach(() => {
    /*
     * Two bits of browser the navbar needs and jsdom does not provide.
     *
     * Fresnel renders only the breakpoints whose query matches, so a mock matching nothing
     * renders no navbar at all, and one matching everything renders the mobile and desktop
     * bars at once.  Match the `computer` breakpoint alone: one bar, tabs in a row.
     */
    window.matchMedia = jest.fn().mockImplementation(query => ({
        matches: query.includes('1024'),
        media: query,
        onchange: null,
        addListener: jest.fn(),
        removeListener: jest.fn(),
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        dispatchEvent: jest.fn(),
    }));

    /*
     * Every width is 0 in jsdom, so useOverflowNav concludes that nothing fits and sweeps
     * all eleven tabs into the "More" menu -- which is closed, so the bar renders no tabs
     * and every assertion here would pass vacuously.  A wide bar with modest tabs runs the
     * same measuring path a browser does.
     */
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', {configurable: true, value: 2000});
    jest.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(() => ({
        width: 60, height: 40, top: 0, left: 0, right: 60, bottom: 40, x: 0, y: 0,
        toJSON: () => ({}),
    }));
});

// NavBar reads the file-worker status for its indicator icons.  That context lives outside
// contexts/contexts.js, so the spec supplies it -- see the note at the top of test-utils.
const fileWorkerStatus = {status: null, error: null, refresh: jest.fn(), setFastPolling: jest.fn()};

const renderNav = (route) => render(<NavBar/>, {
    route,
    withMedia: true,
    contexts: [[FileWorkerStatusContext, fileWorkerStatus]],
});

/** The tab marked as the current page, by its text. */
const currentTab = () => {
    const current = document.querySelectorAll('[aria-current="page"]');
    return [...current].map(el => el.textContent.trim());
};

describe('NavBar current tab', () => {
    it.each([
        ['/videos', 'Videos'],
        ['/archives', 'Archive'],
        ['/docs', 'Docs'],
        ['/map', 'Map'],
        ['/files', 'Files'],
        ['/playlists', 'Playlists'],
        ['/zim', 'Zim'],
        ['/inventory', 'Inventory'],
        ['/flasher', 'Flasher'],
        ['/more/calculators', 'Calculators'],
        ['/more/statistics', 'Statistics'],
    ])('marks %s as %s', (route, text) => {
        renderNav(route);

        expect(currentTab()).toContain(text);
    });

    it.each([
        ['/videos/1234', 'Videos'],
        ['/videos/channel/5/video', 'Videos'],
        ['/archives/domain/example.com', 'Archive'],
        ['/files/some/deep/directory', 'Files'],
        ['/inventory/1/items', 'Inventory'],
        ['/more/calculators/electrical', 'Calculators'],
    ])('keeps the tab marked on a page underneath it: %s stays %s', (route, text) => {
        // The reported bug: opening a video left no tab marked, because the tab only
        // matched its own exact path.
        renderNav(route);

        expect(currentTab()).toContain(text);
    });

    it('marks the home link only at the root', () => {
        // `to='/'` matches every path unless it is told not to, which would leave the home
        // link permanently marked and two tabs claiming to be the current page at once.
        renderNav('/videos');

        const home = screen.getByRole('link', {name: /WROLPi Home Icon|WROLPi/i});
        expect(home).not.toHaveAttribute('aria-current');
    });

    it('marks exactly one tab at a time', () => {
        renderNav('/videos/1234');

        expect(currentTab()).toHaveLength(1);
    });

    it('marks the home link at the root', () => {
        renderNav('/');

        expect(currentTab()).toHaveLength(1);
    });

    it('gives the current tab the class the bar styles', () => {
        renderNav('/videos');

        expect(document.querySelector('[aria-current="page"]')).toHaveClass('active');
    });

    it('styles that class, so the current tab actually looks current', () => {
        /*
         * The reported bug in full: react-router was already marking the tab, and the mark
         * was already reaching the DOM -- nothing styled it, so every tab looked identical
         * and clicking Videos appeared to do nothing to the bar.
         *
         * jsdom applies no stylesheet, so no rendering assertion can see this.  The rule
         * itself is the thing to guard.
         */
        const css = fs.readFileSync(path.join(__dirname, '..', 'App.css'), 'utf8');

        expect(css).toMatch(/\.wrolpi-navbar-link\.active/);
    });
});
