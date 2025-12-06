// Jest setup file for React Testing Library
// This file is automatically loaded by Create React App before running tests

import '@testing-library/jest-dom';

// Mock react-stl-viewer to avoid three.js errors in test environment
jest.mock('react-stl-viewer', () => ({
    StlViewer: () => null,
}));

// Mock window.matchMedia (used by Semantic UI Media components)
Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: jest.fn().mockImplementation(query => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: jest.fn(), // deprecated
        removeListener: jest.fn(), // deprecated
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        dispatchEvent: jest.fn(),
    })),
});

// Mock IntersectionObserver (if needed for lazy loading)
global.IntersectionObserver = class IntersectionObserver {
    constructor() {}
    disconnect() {}
    observe() {}
    takeRecords() {
        return [];
    }
    unobserve() {}
};

// Suppress console errors during tests (optional - uncomment if needed)
// const originalError = console.error;
// beforeAll(() => {
//     console.error = (...args) => {
//         if (
//             typeof args[0] === 'string' &&
//             args[0].includes('Warning: ReactDOM.render')
//         ) {
//             return;
//         }
//         originalError.call(console, ...args);
//     };
// });
//
// afterAll(() => {
//     console.error = originalError;
// });
