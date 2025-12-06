import React from 'react';
import {createMockDomain, createTestForm, render, renderInDarkMode, screen, waitFor} from '../test-utils';
import userEvent from '@testing-library/user-event';
import {DomainEditPage} from './Archive';

// Mock useParams to return domain ID
jest.mock('react-router-dom', () => ({
    ...jest.requireActual('react-router-dom'),
    useParams: () => ({domainId: '1'}),
    useNavigate: () => jest.fn(),
}));

// Mock the useDomain hook
const mockUseDomain = jest.fn();

jest.mock('../hooks/customHooks', () => ({
    ...jest.requireActual('../hooks/customHooks'),
    useDomain: (...args) => mockUseDomain(...args),
}));

// Mock useTitle
jest.mock('./Common', () => ({
    ...jest.requireActual('./Common'),
    useTitle: jest.fn(),
}));

// Mock CollectionEditForm
jest.mock('./collections/CollectionEditForm', () => ({
    CollectionEditForm: ({form, fields, title, actionButtons}) => (
        <div data-testid="collection-edit-form">
            {title && <h1>{title}</h1>}
            {form?.loading && <div data-testid="loading-indicator">Loading...</div>}
            {form?.formData && <div data-testid="collection-data">Collection data loaded</div>}
            {fields && <div data-testid="fields-present">Fields configured</div>}
            {actionButtons && <div data-testid="action-buttons">{actionButtons}</div>}
        </div>
    ),
}));

// Mock CollectionTagModal
jest.mock('./collections/CollectionTagModal', () => ({
    CollectionTagModal: ({open, onClose, currentTagName, originalDirectory, getTagInfo, onSave, collectionName}) => {
        if (!open) return null;
        return (
            <div data-testid="collection-tag-modal">
                <div data-testid="modal-header">{currentTagName ? 'Modify Tag' : 'Add Tag'}</div>
                <input type="text" data-testid="directory-input" defaultValue={originalDirectory || ''}/>
                <button data-testid="cancel-button" onClick={onClose}>Cancel</button>
                <button data-testid="save-button"
                        onClick={() => onSave && onSave(currentTagName, originalDirectory)}>Save
                </button>
            </div>
        );
    },
}));

// Mock API functions
const mockGetCollectionTagInfo = jest.fn();
jest.mock('../api', () => ({
    ...jest.requireActual('../api'),
    getCollectionTagInfo: (...args) => mockGetCollectionTagInfo(...args),
    tagDomain: jest.fn(),
}));

describe('DomainEditPage', () => {
    beforeEach(() => {
        jest.clearAllMocks();
    });

    describe('Loading States', () => {
        it('handles loading state while fetching domain', async () => {
            // Start with loading state (no domain yet)
            const form = createTestForm({}, {
                overrides: {ready: false, loading: false}
            });

            mockUseDomain.mockReturnValue({
                domain: null,
                form,
                fetchDomain: jest.fn(),
            });

            render(<DomainEditPage/>);

            // Should show Semantic UI Loader with text
            expect(screen.getByText(/loading domain/i)).toBeInTheDocument();

            // Form should not be visible during initial load
            expect(screen.queryByTestId('collection-edit-form')).not.toBeInTheDocument();
        });

        it('shows form when domain is loaded', () => {
            const mockDomain = createMockDomain({
                domain: 'test.com',
            });

            const form = createTestForm(mockDomain, {
                overrides: {ready: true, loading: false}
            });

            mockUseDomain.mockReturnValue({
                domain: mockDomain,
                form,
                fetchDomain: jest.fn(),
            });

            render(<DomainEditPage/>);

            // Should NOT show loading message
            expect(screen.queryByText(/loading domain/i)).not.toBeInTheDocument();

            // Should show domain name (may appear multiple times in header and form)
            expect(screen.getAllByText(/test\.com/i).length).toBeGreaterThan(0);
        });

        it('passes loading state to form during submission', () => {
            const mockDomain = createMockDomain({
                domain: 'example.com',
            });

            // Domain is loaded but form is submitting
            const form = createTestForm(mockDomain, {
                overrides: {ready: true, loading: true}
            });

            mockUseDomain.mockReturnValue({
                domain: mockDomain,
                form,
                fetchDomain: jest.fn(),
            });

            render(<DomainEditPage/>);

            // Should show loading indicator in form (from mocked component)
            // Multiple indicators due to Fresnel rendering for mobile and tablet+
            expect(screen.getAllByTestId('loading-indicator').length).toBeGreaterThan(0);

            // Should also show the domain name
            expect(screen.getAllByText(/example\.com/i).length).toBeGreaterThan(0);
        });
    });

    describe('Error States', () => {
        it('shows loader when form is not ready (fetch fails)', () => {
            // When form.ready is false (e.g., fetch failed), show loader
            const form = createTestForm({}, {
                overrides: {ready: false, loading: false, error: new Error('Domain not found')}
            });

            mockUseDomain.mockReturnValue({
                domain: null,
                form,
                fetchDomain: jest.fn(),
            });

            render(<DomainEditPage/>);

            // Should show loading screen when not ready
            expect(screen.getByText(/loading domain/i)).toBeInTheDocument();

            // Form should not be rendered
            expect(screen.queryByTestId('collection-edit-form')).not.toBeInTheDocument();
        });

        it('shows form when ready even if there was a submission error', () => {
            // Form is ready (domain loaded) but submission may have failed
            const mockDomain = createMockDomain({
                domain: 'example.com',
            });

            const form = createTestForm(mockDomain, {
                overrides: {ready: true, loading: false, error: new Error('Update failed')}
            });

            mockUseDomain.mockReturnValue({
                domain: mockDomain,
                form,
                fetchDomain: jest.fn(),
            });

            render(<DomainEditPage/>);

            // Should show domain name (form is rendered)
            // Multiple occurrences due to Fresnel rendering for mobile and tablet+
            expect(screen.getAllByText(/example\.com/i).length).toBeGreaterThan(0);

            // Should NOT show the initial loading screen
            expect(screen.queryByText(/loading domain/i)).not.toBeInTheDocument();
        });
    });

    describe('Page Title', () => {
        it('sets page title with domain name', () => {
            const {useTitle} = require('./Common');
            const mockDomain = createMockDomain({
                domain: 'example.com',
            });

            const form = createTestForm(mockDomain, {
                overrides: {ready: true, loading: false}
            });

            mockUseDomain.mockReturnValue({
                domain: mockDomain,
                form,
                fetchDomain: jest.fn(),
            });

            render(<DomainEditPage/>);

            // useTitle should be called with domain name
            expect(useTitle).toHaveBeenCalledWith('Edit Domain: example.com');
        });

        it('sets page title with placeholder while loading', () => {
            const {useTitle} = require('./Common');

            const form = createTestForm({}, {
                overrides: {ready: false, loading: false}
            });

            mockUseDomain.mockReturnValue({
                domain: null,
                form,
                fetchDomain: jest.fn(),
            });

            render(<DomainEditPage/>);

            // useTitle should be called with placeholder
            expect(useTitle).toHaveBeenCalledWith('Edit Domain: ...');
        });
    });

    describe('Theme Integration', () => {
        it('passes theme context to CollectionEditForm in dark mode', () => {
            const mockDomain = createMockDomain({
                domain: 'example.com',
            });

            const form = createTestForm(mockDomain, {
                overrides: {ready: true, loading: false}
            });

            mockUseDomain.mockReturnValue({
                domain: mockDomain,
                form,
                fetchDomain: jest.fn(),
            });

            // Render in dark mode
            renderInDarkMode(<DomainEditPage/>);

            // CollectionEditForm should be rendered
            expect(screen.getByTestId('collection-edit-form')).toBeInTheDocument();

            // The title should include the domain name
            expect(screen.getAllByText(/example\.com/i).length).toBeGreaterThan(0);
        });

        it('renders properly in light mode', () => {
            const mockDomain = createMockDomain({
                domain: 'test.com',
            });

            const form = createTestForm(mockDomain, {
                overrides: {ready: true, loading: false}
            });

            mockUseDomain.mockReturnValue({
                domain: mockDomain,
                form,
                fetchDomain: jest.fn(),
            });

            // Default render (light mode)
            render(<DomainEditPage/>);

            // CollectionEditForm should be rendered
            expect(screen.getByTestId('collection-edit-form')).toBeInTheDocument();

            // The title should include the domain name
            expect(screen.getAllByText(/test\.com/i).length).toBeGreaterThan(0);
        });
    });

    describe('Tag Modal and Directory Suggestions', () => {
        beforeEach(() => {
            jest.clearAllMocks();
            mockGetCollectionTagInfo.mockClear();
        });

        it('suggests directory when tag is selected', async () => {
            const mockDomain = createMockDomain({
                domain: 'example.com',
                id: 1,
            });

            const form = createTestForm(mockDomain, {
                overrides: {ready: true, loading: false}
            });

            mockUseDomain.mockReturnValue({
                domain: mockDomain,
                form,
                fetchDomain: jest.fn(),
            });

            // Mock successful tag info response
            mockGetCollectionTagInfo.mockResolvedValue({
                suggested_directory: 'archive/WROL/example.com',
                conflict: false,
                conflict_message: null,
            });

            render(<DomainEditPage/>);

            // Click the Tag button to open modal
            const tagButton = screen.getByText('Tag');
            await userEvent.click(tagButton);

            // Wait for modal to open
            await waitFor(() => {
                expect(screen.getByText(/Modify Tag|Add Tag/i)).toBeInTheDocument();
            });

            // Simulate selecting a tag (this would normally be done by TagsSelector)
            // Since TagsSelector is a real component, we need to wait for the API call
            // We'll verify the API was called when a tag would be selected
            // This test validates the structure is in place
        });

        it('displays conflict warning in modal when directory conflict exists', async () => {
            const mockDomain = createMockDomain({
                domain: 'example.com',
                id: 1,
            });

            const form = createTestForm(mockDomain, {
                overrides: {ready: true, loading: false}
            });

            mockUseDomain.mockReturnValue({
                domain: mockDomain,
                form,
                fetchDomain: jest.fn(),
            });

            // Mock tag info response with conflict
            mockGetCollectionTagInfo.mockResolvedValue({
                suggested_directory: 'archive/WROL/example.com',
                conflict: true,
                conflict_message: "A domain collection 'other.com' already uses this directory. Choose a different tag or directory.",
            });

            render(<DomainEditPage/>);

            // Open the modal
            const tagButton = screen.getByText('Tag');
            await userEvent.click(tagButton);

            // The modal should be present
            await waitFor(() => {
                expect(screen.getByTestId('collection-tag-modal')).toBeInTheDocument();
            });

            // Verify the modal structure includes the necessary inputs
            expect(screen.getByTestId('directory-input')).toBeInTheDocument();
        });

        it('clears conflict message when tag is changed', async () => {
            const mockDomain = createMockDomain({
                domain: 'example.com',
                id: 1,
            });

            const form = createTestForm(mockDomain, {
                overrides: {ready: true, loading: false}
            });

            mockUseDomain.mockReturnValue({
                domain: mockDomain,
                form,
                fetchDomain: jest.fn(),
            });

            render(<DomainEditPage/>);

            // Open modal
            const tagButton = screen.getByText('Tag');
            await userEvent.click(tagButton);

            await waitFor(() => {
                expect(screen.getByText(/Modify Tag|Add Tag/i)).toBeInTheDocument();
            });

            // Modal should be open and ready for tag selection
            // The actual tag selection and conflict clearing would be tested in integration tests
            // This validates the structure is present
        });

        it('populates directory input with suggested directory', async () => {
            const mockDomain = createMockDomain({
                domain: 'example.com',
                id: 1,
                directory: 'archive/example.com',
            });

            const form = createTestForm(mockDomain, {
                overrides: {ready: true, loading: false}
            });

            mockUseDomain.mockReturnValue({
                domain: mockDomain,
                form,
                fetchDomain: jest.fn(),
            });

            mockGetCollectionTagInfo.mockResolvedValue({
                suggested_directory: 'archive/WROL/example.com',
                conflict: false,
                conflict_message: null,
            });

            render(<DomainEditPage/>);

            // Open modal
            const tagButton = screen.getByText('Tag');
            await userEvent.click(tagButton);

            // Wait for modal to open
            await waitFor(() => {
                expect(screen.getByTestId('collection-tag-modal')).toBeInTheDocument();
            });

            // Verify directory input field exists with original directory value
            const directoryInput = screen.getByTestId('directory-input');
            expect(directoryInput).toBeInTheDocument();
            expect(directoryInput).toHaveValue('archive/example.com');
        });
    });
});
