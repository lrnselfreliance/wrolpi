import fs from 'fs';
import path from 'path';
import React from 'react';
import {screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

/**
 * Report a viewport to fresnel, which renders only the breakpoints whose query matches: a
 * mock matching nothing renders no navbar at all, and one matching everything renders the
 * mobile and desktop bars at once.
 */
const useViewport = (kind) => {
    // Fresnel's breakpoints are mobile 0 / tablet 700 / wideTablet 880 / computer 1024.
    const matches = kind === 'desktop'
        ? (query) => query.includes('1024')
        : (query) => !/\d{3,}px/.test(query) || /\(max-width/.test(query);
    window.matchMedia = jest.fn().mockImplementation(query => ({
        matches: matches(query),
        media: query,
        onchange: null,
        addListener: jest.fn(),
        removeListener: jest.fn(),
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        dispatchEvent: jest.fn(),
    }));
};

/**
 * Give jsdom a bar of `barWidth` holding tabs of 60px each.
 *
 * Every width is 0 otherwise, so useOverflowNav concludes that nothing fits and sweeps all
 * eleven tabs into the closed "More" menu -- the bar renders no tabs at all and every
 * assertion about them passes vacuously.  A narrow bar is how the overflow path is reached
 * on purpose.
 */
const useBarWidth = (barWidth) => {
    rectSpy = rectSpy || null;
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', {configurable: true, value: barWidth});
    rectSpy = jest.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(() => ({
        width: 60, height: 40, top: 0, left: 0, right: 60, bottom: 40, x: 0, y: 0,
        toJSON: () => ({}),
    }));
};

/**
 * Hand back the real `getBoundingClientRect`.
 *
 * The stub above is for the overflow measurement, which the mobile bar never runs -- and
 * floating-ui, which positions the menu's portal, walks up to the document element and
 * crashes the worker on a rect that is not a real DOMRect.
 */
const useRealRects = () => {
    if (rectSpy) {
        rectSpy.mockRestore();
        rectSpy = null;
    }
};

let rectSpy = null;

beforeEach(() => {
    rectSpy = null;
    useViewport('desktop');
    useBarWidth(2000);
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

        // Exactly, not `toContain`: a regression leaving Home permanently marked alongside
        // the real tab satisfies "contains" on every row here.
        expect(currentTab()).toEqual([text]);
    });

    it.each([
        ['/videos/1234', 'Videos'],
        ['/videos/channel/5/video', 'Videos'],
        ['/archives/domain/example.com', 'Archive'],
        ['/files/some/deep/directory', 'Files'],
        ['/inventory/1/items', 'Inventory'],
        ['/more/calculators/electrical', 'Calculators'],
    ])('keeps the tab marked on a page underneath it: %s stays %s', (route, text) => {
        /*
         * Not where the reported bug was -- Videos never carried `end`, so opening a video
         * always marked it in the DOM; what was missing was the CSS that draws the mark.
         * These cases guard the other half: that nobody adds `end` to a link with pages
         * beneath it, which is what Calculators and Statistics used to have.
         */
        renderNav(route);

        expect(currentTab()).toEqual([text]);
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

    it('marks the current item inside the mobile menu', async () => {
        // On a phone the bar is a hamburger, so these menu items are the only place the
        // mark can appear -- and `.mantine-Menu-item.active` is the only rule that draws it.
        useViewport('mobile');
        useRealRects();
        renderNav('/videos');

        await userEvent.click(screen.getByRole('button', {name: 'Menu'}));

        const videos = await screen.findByRole('menuitem', {name: 'Videos'});
        expect(videos).toHaveAttribute('aria-current', 'page');
        expect(videos).toHaveClass('active');
    });

    it('marks the More button when the current section is folded inside it', () => {
        /*
         * A narrow bar pushes tabs into the overflow menu.  Nothing in the bar was marked
         * then: the trigger is a plain button, not a NavLink, so the bar went blank exactly
         * when the window got too small to show the tab -- and the user had to open the menu
         * to find out where they were.
         */
        useBarWidth(200);
        renderNav('/videos');

        const more = screen.getByRole('button', {name: /More/});
        expect(more).toHaveClass('active');
    });

    it('leaves the More button unmarked when the current section is not inside it', () => {
        useBarWidth(200);
        // Nothing in the bar's link list covers /admin/settings; Admin sits outside it.
        renderNav('/admin/settings');

        expect(screen.getByRole('button', {name: /More/})).not.toHaveClass('active');
    });

    it('styles that class, so the current tab actually looks current', () => {
        /*
         * The reported bug in full: react-router was already marking the tab, and the mark
         * was already reaching the DOM -- nothing styled it, so every tab looked identical
         * and clicking Videos appeared to do nothing to the bar.
         *
         * jsdom applies no stylesheet, so the rule itself is the thing to guard, and it is
         * guarded by its declarations rather than by its selector: a check for the selector
         * alone still passes with the body emptied, or with the underline deleted -- and the
         * underline is the half that survives on a dark bar, where the wash barely reads.
         */
        const css = fs.readFileSync(path.join(__dirname, '..', 'App.css'), 'utf8');
        const ruleBody = (selector) => {
            const match = css.match(new RegExp(`${selector}\\s*{([^}]*)}`));
            return match ? match[1] : '';
        };

        // The wash.
        expect(ruleBody('\\.wrolpi-navbar-link\\.active')).toMatch(/background:/);
        // The underline: drawn, in the bar's own foreground, with a height to draw.
        const underline = ruleBody('\\.wrolpi-navbar-link\\.active::after');
        expect(underline).toMatch(/content:/);
        expect(underline).toMatch(/background:\s*currentColor/);
        // Parsed, not pattern-matched: `(?!0)` would have called 0.1875rem zero.
        const height = underline.match(/height:\s*([\d.]+)\s*(?:rem|em|px)/);
        expect(height).not.toBeNull();
        expect(parseFloat(height[1])).toBeGreaterThan(0);
        // The menu items, which are the whole of the mark on a phone.
        expect(ruleBody('\\.mantine-Menu-item\\.active')).toMatch(/background:|font-weight:/);
    });
});
