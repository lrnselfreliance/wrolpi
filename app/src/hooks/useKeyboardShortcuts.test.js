import React from 'react';
import {render, screen, fireEvent, act} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {KeyboardShortcutsContext} from '../contexts/KeyboardShortcutsContext';
import {KeyboardShortcutsProvider, SHORTCUTS} from '../components/KeyboardShortcutsProvider';
import {ThemeContext} from '../contexts/contexts';
import {TagsContext} from '../Tags';
import {QueryContext} from '../contexts/contexts';

// Mock useSearchSuggestions to avoid complex setup
jest.mock('../components/Search', () => ({
    ...jest.requireActual('../components/Search'),
    useSearchSuggestions: () => ({
        suggestionsResults: {},
        handleResultSelect: jest.fn(),
        resultRenderer: () => null,
        loading: false,
        searchStr: '',
        setSearchStr: jest.fn(),
    }),
}));

// Test wrapper with all required providers
function TestWrapper({children}) {
    const mockThemeContext = {
        i: {},
        s: {},
        t: {},
        theme: 'light',
        inverted: '',
    };

    const mockTagsContext = {
        SingleTag: () => null,
        fuzzyMatchTagsByName: () => [],
    };

    const mockQueryContext = {
        searchParams: new URLSearchParams(),
        setSearchParams: jest.fn(),
        updateQuery: jest.fn(),
        getLocationStr: jest.fn((params, base) => base || '/'),
    };

    return (
        <MemoryRouter>
            <ThemeContext.Provider value={mockThemeContext}>
                <QueryContext.Provider value={mockQueryContext}>
                    <TagsContext.Provider value={mockTagsContext}>
                        <KeyboardShortcutsProvider>
                            {children}
                        </KeyboardShortcutsProvider>
                    </TagsContext.Provider>
                </QueryContext.Provider>
            </ThemeContext.Provider>
        </MemoryRouter>
    );
}

// Simple component that uses the context
function TestComponent() {
    const {
        searchModalOpen,
        helpModalOpen,
        openSearchModal,
        closeSearchModal,
        openHelpModal,
        closeHelpModal,
        closeAllModals,
    } = React.useContext(KeyboardShortcutsContext);

    return (
        <div>
            <div data-testid="search-modal-status">{searchModalOpen ? 'open' : 'closed'}</div>
            <div data-testid="help-modal-status">{helpModalOpen ? 'open' : 'closed'}</div>
            <button data-testid="open-search" onClick={openSearchModal}>Open Search</button>
            <button data-testid="close-search" onClick={closeSearchModal}>Close Search</button>
            <button data-testid="open-help" onClick={openHelpModal}>Open Help</button>
            <button data-testid="close-help" onClick={closeHelpModal}>Close Help</button>
            <button data-testid="close-all" onClick={closeAllModals}>Close All</button>
        </div>
    );
}

describe('KeyboardShortcutsContext', () => {
    test('provides default values (modals closed)', () => {
        render(
            <TestWrapper>
                <TestComponent/>
            </TestWrapper>
        );

        expect(screen.getByTestId('search-modal-status')).toHaveTextContent('closed');
        expect(screen.getByTestId('help-modal-status')).toHaveTextContent('closed');
    });

    test('openSearchModal opens search modal', () => {
        render(
            <TestWrapper>
                <TestComponent/>
            </TestWrapper>
        );

        act(() => {
            fireEvent.click(screen.getByTestId('open-search'));
        });

        expect(screen.getByTestId('search-modal-status')).toHaveTextContent('open');
        expect(screen.getByTestId('help-modal-status')).toHaveTextContent('closed');
    });

    test('closeSearchModal closes search modal', () => {
        render(
            <TestWrapper>
                <TestComponent/>
            </TestWrapper>
        );

        // Open first
        act(() => {
            fireEvent.click(screen.getByTestId('open-search'));
        });
        expect(screen.getByTestId('search-modal-status')).toHaveTextContent('open');

        // Close
        act(() => {
            fireEvent.click(screen.getByTestId('close-search'));
        });
        expect(screen.getByTestId('search-modal-status')).toHaveTextContent('closed');
    });

    test('openHelpModal opens help modal', () => {
        render(
            <TestWrapper>
                <TestComponent/>
            </TestWrapper>
        );

        act(() => {
            fireEvent.click(screen.getByTestId('open-help'));
        });

        expect(screen.getByTestId('help-modal-status')).toHaveTextContent('open');
        expect(screen.getByTestId('search-modal-status')).toHaveTextContent('closed');
    });

    test('closeHelpModal closes help modal', () => {
        render(
            <TestWrapper>
                <TestComponent/>
            </TestWrapper>
        );

        // Open first
        act(() => {
            fireEvent.click(screen.getByTestId('open-help'));
        });
        expect(screen.getByTestId('help-modal-status')).toHaveTextContent('open');

        // Close
        act(() => {
            fireEvent.click(screen.getByTestId('close-help'));
        });
        expect(screen.getByTestId('help-modal-status')).toHaveTextContent('closed');
    });

    test('closeAllModals closes both modals', () => {
        render(
            <TestWrapper>
                <TestComponent/>
            </TestWrapper>
        );

        // Open search
        act(() => {
            fireEvent.click(screen.getByTestId('open-search'));
        });
        expect(screen.getByTestId('search-modal-status')).toHaveTextContent('open');

        // Close all
        act(() => {
            fireEvent.click(screen.getByTestId('close-all'));
        });
        expect(screen.getByTestId('search-modal-status')).toHaveTextContent('closed');
        expect(screen.getByTestId('help-modal-status')).toHaveTextContent('closed');
    });

    test('opening search modal closes help modal', () => {
        render(
            <TestWrapper>
                <TestComponent/>
            </TestWrapper>
        );

        // Open help first
        act(() => {
            fireEvent.click(screen.getByTestId('open-help'));
        });
        expect(screen.getByTestId('help-modal-status')).toHaveTextContent('open');

        // Open search should close help
        act(() => {
            fireEvent.click(screen.getByTestId('open-search'));
        });
        expect(screen.getByTestId('search-modal-status')).toHaveTextContent('open');
        expect(screen.getByTestId('help-modal-status')).toHaveTextContent('closed');
    });

    test('opening help modal closes search modal', () => {
        render(
            <TestWrapper>
                <TestComponent/>
            </TestWrapper>
        );

        // Open search first
        act(() => {
            fireEvent.click(screen.getByTestId('open-search'));
        });
        expect(screen.getByTestId('search-modal-status')).toHaveTextContent('open');

        // Open help should close search
        act(() => {
            fireEvent.click(screen.getByTestId('open-help'));
        });
        expect(screen.getByTestId('help-modal-status')).toHaveTextContent('open');
        expect(screen.getByTestId('search-modal-status')).toHaveTextContent('closed');
    });
});

describe('SHORTCUTS constant', () => {
    test('is defined and is an array', () => {
        expect(SHORTCUTS).toBeDefined();
        expect(Array.isArray(SHORTCUTS)).toBe(true);
        expect(SHORTCUTS.length).toBeGreaterThan(0);
    });

    test('contains search shortcuts', () => {
        const shortcutKeys = SHORTCUTS.map(s => s.keys);
        expect(shortcutKeys).toContain('meta+k, ctrl+k');
        expect(shortcutKeys).toContain('/');
    });

    test('contains help shortcut', () => {
        const shortcutKeys = SHORTCUTS.map(s => s.keys);
        expect(shortcutKeys).toContain('shift+/');
    });

    test('contains escape shortcut', () => {
        const shortcutKeys = SHORTCUTS.map(s => s.keys);
        expect(shortcutKeys).toContain('escape');
    });

    test('contains navigation shortcuts', () => {
        const shortcutKeys = SHORTCUTS.map(s => s.keys);
        expect(shortcutKeys).toContain('g h');
        expect(shortcutKeys).toContain('g v');
        expect(shortcutKeys).toContain('g a');
        expect(shortcutKeys).toContain('g m');
        expect(shortcutKeys).toContain('g z');
        expect(shortcutKeys).toContain('g f');
        expect(shortcutKeys).toContain('g s');
        expect(shortcutKeys).toContain('g i');
    });

    test('all shortcuts have required properties', () => {
        SHORTCUTS.forEach(shortcut => {
            expect(shortcut).toHaveProperty('keys');
            expect(shortcut).toHaveProperty('description');
            expect(shortcut).toHaveProperty('category');
            expect(typeof shortcut.keys).toBe('string');
            expect(typeof shortcut.description).toBe('string');
            expect(typeof shortcut.category).toBe('string');
        });
    });

    test('navigation shortcuts have path property', () => {
        const navShortcuts = SHORTCUTS.filter(s => s.category === 'Navigation');
        expect(navShortcuts.length).toBeGreaterThan(0);
        navShortcuts.forEach(shortcut => {
            expect(shortcut).toHaveProperty('path');
            expect(shortcut.path).toMatch(/^\//);
        });
    });

    test('shortcuts are grouped by category', () => {
        const categories = [...new Set(SHORTCUTS.map(s => s.category))];
        expect(categories).toContain('Search');
        expect(categories).toContain('Navigation');
        expect(categories).toContain('General');
        expect(categories).toContain('Help');
    });
});
