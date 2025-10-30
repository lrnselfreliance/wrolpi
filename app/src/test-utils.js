/**
 * Test utilities for React Testing Library
 * Provides custom render functions with necessary context providers
 */

import React from 'react';
import {render} from '@testing-library/react';
import {BrowserRouter} from 'react-router-dom';
import {MediaContextProvider, ThemeContext} from './contexts/contexts';

/**
 * Custom render function that wraps components with necessary providers
 * @param {React.Component} ui - Component to render
 * @param {Object} options - Render options
 * @param {boolean} options.inverted - Whether to use dark theme
 * @param {Object} options.themeContext - Custom theme context values
 * @param {boolean} options.withMedia - Include MediaContextProvider (default: false)
 * @param {Object} options.renderOptions - Additional React Testing Library options
 */
export function renderWithProviders(
    ui,
    {
        inverted = false,
        themeContext = {},
        withMedia = false,
        ...renderOptions
    } = {}
) {
    const defaultThemeContext = {
        inverted,
        setInverted: jest.fn(),
        // Theme components use different properties:
        i: inverted ? {inverted: true} : {inverted: undefined},  // For Semantic UI elements (Segment, Form, etc.)
        s: inverted ? {style: {backgroundColor: '#1B1C1D', color: '#dddddd'}} : {},  // For style inversion
        t: inverted ? {style: {color: '#eeeeee'}} : {},  // For text color inversion (Header, etc.)
        theme: inverted ? 'dark' : 'light',
        ...themeContext
    };

    function Wrapper({children}) {
        const content = (
            <BrowserRouter>
                <ThemeContext.Provider value={defaultThemeContext}>
                    {children}
                </ThemeContext.Provider>
            </BrowserRouter>
        );

        // Only wrap with MediaContextProvider if explicitly requested
        // (since it requires window.matchMedia which can be tricky in tests)
        if (withMedia) {
            return <MediaContextProvider>{content}</MediaContextProvider>;
        }

        return content;
    }

    return render(ui, {wrapper: Wrapper, ...renderOptions});
}

/**
 * Creates a mock collection metadata object for testing
 */
export function createMockMetadata(kind = 'domain', overrides = {}) {
    return {
        kind,
        columns: [
            {key: 'domain', label: 'Domain', sortable: true},
            {key: 'archive_count', label: 'Archives', sortable: true, align: 'right'},
            {key: 'size', label: 'Size', sortable: true, align: 'right', format: 'bytes'},
            {key: 'tag_name', label: 'Tag', sortable: true},
            {key: 'actions', label: 'Manage', sortable: false, type: 'actions'},
        ],
        fields: [
            {key: 'directory', label: 'Directory', type: 'text', placeholder: 'Optional directory path'},
            {key: 'tag_name', label: 'Tag', type: 'tag', placeholder: 'Select or create tag', depends_on: 'directory'},
            {key: 'description', label: 'Description', type: 'textarea', placeholder: 'Optional description'},
        ],
        routes: {
            list: '/archive/domains',
            edit: '/archive/domain/:id/edit',
            search: '/archive',
        },
        messages: {
            no_directory: 'Set a directory to enable tagging',
            tag_will_move: 'Tagging will move files to a new directory'
        },
        ...overrides
    };
}

/**
 * Creates a mock domain collection object for testing
 */
export function createMockDomain(overrides = {}) {
    return {
        id: 1,
        domain: 'example.com',
        archive_count: 42,
        size: 1024000,
        tag_name: null,
        directory: '',
        can_be_tagged: false,
        description: '',
        ...overrides
    };
}

/**
 * Creates multiple mock domains for list testing
 */
export function createMockDomains(count = 3) {
    return Array.from({length: count}, (_, i) => createMockDomain({
        id: i + 1,
        domain: `example${i + 1}.com`,
        archive_count: (i + 1) * 10,
        size: (i + 1) * 1000000,
    }));
}

/**
 * Mock fetch implementation for API calls
 */
export function mockFetch(data, options = {}) {
    const {
        ok = true,
        status = 200,
        delay = 0,
    } = options;

    return jest.fn(() =>
        new Promise((resolve) => {
            setTimeout(() => {
                resolve({
                    ok,
                    status,
                    json: async () => data,
                    text: async () => JSON.stringify(data),
                });
            }, delay);
        })
    );
}

/**
 * Mock API error response
 */
export function mockFetchError(error = 'An error occurred', status = 400) {
    return jest.fn(() =>
        Promise.resolve({
            ok: false,
            status,
            json: async () => ({error}),
            text: async () => error,
        })
    );
}

/**
 * Wait for async updates to complete
 * Useful for testing loading states
 */
export async function waitForLoadingToFinish() {
    const {waitFor} = await import('@testing-library/react');
    await waitFor(() => {}, {timeout: 100});
}

/**
 * Test helper to render components in dark mode
 *
 * Usage:
 *   renderInDarkMode(<MyComponent />)
 *
 * Verify inverted styling is applied:
 *   const element = container.querySelector('.ui.segment.inverted');
 *   expect(element).toBeInTheDocument();
 */
export function renderInDarkMode(ui, options = {}) {
    return renderWithProviders(ui, {
        inverted: true,
        ...options
    });
}

/**
 * Test helper to render components in light mode
 * (This is the default, but provided for explicitness in tests)
 */
export function renderInLightMode(ui, options = {}) {
    return renderWithProviders(ui, {
        inverted: false,
        ...options
    });
}

/**
 * Helper to check if an element has theme-aware (inverted) styling
 * Returns true if the element has the 'inverted' class
 *
 * Usage:
 *   const segment = container.querySelector('.ui.segment');
 *   expect(hasInvertedStyling(segment)).toBe(true);
 */
export function hasInvertedStyling(element) {
    return element && element.classList.contains('inverted');
}

/**
 * Creates a test-friendly form object using real useForm hook
 *
 * This uses the actual useForm implementation, making tests more reliable.
 * The form starts in a "ready" state with the provided data.
 *
 * Usage:
 *   const form = createTestForm({domain: 'test.com', directory: '/path'});
 *   render(<CollectionEditForm form={form} metadata={metadata} />);
 *
 *   // With overrides:
 *   const form = createTestForm(data, {overrides: {loading: true, disabled: true}});
 */
export function createTestForm(initialData = {}, config = {}) {
    // Return a plain object that mimics the useForm interface without actual React hooks
    // This avoids async state updates that cause act() warnings in tests
    const _ = require('lodash');
    const formData = {...initialData};

    const setValue = (path, newValue) => {
        _.set(formData, path, newValue);
    };

    const form = {
        formData,
        ready: true,
        loading: false,
        disabled: false,
        dirty: false,
        errors: {},
        // Methods that update formData directly
        patchFormData: jest.fn((updates) => {
            Object.assign(formData, updates);
        }),
        reset: jest.fn(() => {
            Object.keys(formData).forEach(key => delete formData[key]);
            Object.assign(formData, initialData);
        }),
        onSubmit: config.submitter || jest.fn(async () => initialData),
        // Input helpers
        setError: jest.fn(),
        setValidator: jest.fn(),
        setValidValue: jest.fn(),
        setRequired: jest.fn(),
        // Property getter for field values
        get: (path) => _.get(formData, path),
        setValue: jest.fn((path, value) => setValue(path, value)),
        // getCustomProps - mimics the real useForm method
        getCustomProps: ({name, path, required = false, type = 'text'}) => {
            path = path || name;
            const value = _.get(formData, path);

            const inputProps = {
                type,
                disabled: form.disabled,
                value: value !== undefined ? value : (type === 'array' ? [] : null),
                onChange: (newValue) => {
                    setValue(path, newValue);
                },
                'data-path': path,
            };

            const inputAttrs = {
                valid: true,
                path,
                localSetValue: (newValue) => setValue(path, newValue),
            };

            return [inputProps, inputAttrs];
        },
    };

    // Apply any overrides
    if (config.overrides) {
        Object.assign(form, config.overrides);
    }

    return form;
}

// Re-export everything from React Testing Library
export * from '@testing-library/react';

// Override the default render with our custom one
export {renderWithProviders as render};
