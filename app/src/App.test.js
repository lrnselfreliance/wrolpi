import React from 'react';
import {render, screen} from '@testing-library/react';
import {createMemoryRouter, RouterProvider} from 'react-router';
import {routes} from './App';
import {StatusProvider} from './hooks/customHooks';
import {FileWorkerStatusProvider} from './contexts/FileWorkerStatusContext';
import {MediaContextProvider} from './contexts/contexts';

// Jest does not transform CSS inside node_modules (see transformIgnorePatterns).
jest.mock('@mantine/core/styles.css', () => ({}));
jest.mock('@mantine/notifications/styles.css', () => ({}));
// Routes this test does not visit, whose libraries jsdom/Jest cannot load (maplibre needs
// browser APIs; esptool-js is ESM-only).
jest.mock('./components/Map', () => ({MapRoute: () => null}));
jest.mock('./components/Flasher', () => ({FlasherRoute: () => null}));

describe('unknown routes', () => {
    beforeEach(() => {
        // resetMocks clears setupTests' implementation; the theme and media providers read it.
        window.matchMedia.mockImplementation(query => ({
            matches: false,
            media: query,
            addListener: jest.fn(),
            removeListener: jest.fn(),
            addEventListener: jest.fn(),
            removeEventListener: jest.fn(),
        }));
        global.fetch = jest.fn(() => Promise.resolve({
            ok: true,
            status: 200,
            headers: {get: () => 'application/json'},
            json: () => Promise.resolve({tags: []}),
            text: () => Promise.resolve('{}'),
        }));
    });

    it('renders Page Not Found inside the app layout', async () => {
        const router = createMemoryRouter(routes, {initialEntries: ['/no-such-page']});
        // The providers App wraps around the router.
        render(<StatusProvider>
            <FileWorkerStatusProvider>
                <MediaContextProvider>
                    <RouterProvider router={router}/>
                </MediaContextProvider>
            </FileWorkerStatusProvider>
        </StatusProvider>);

        expect(await screen.findByText('Page Not Found!')).toBeInTheDocument();
        // Rendered inside Root's layout (the footer comes from Root), not as a bare error page.
        expect(screen.getByText('Donate')).toBeInTheDocument();
    });
});
