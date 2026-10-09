import React from 'react';
import {act, fireEvent, screen} from '@testing-library/react';
import {renderWithProviders} from '../test-utils';
import {CbzViewer} from './CbzViewer';
import {getArchiveContents} from '../api';

jest.mock('../api', () => ({
    ...jest.requireActual('../api'),
    getArchiveContents: jest.fn(),
    getArchiveMemberUrl: (path, member) => `/member/${member}`,
}));

const PATH = 'comics/issue.cbz';
const PAGES = ['01.jpg', '02.jpg', '03.jpg', '04.jpg'];

const {fetch: realFetch} = global;
const realSendBeacon = navigator.sendBeacon;

beforeEach(() => {
    window.sessionStorage.clear();
    getArchiveContents.mockResolvedValue({entries: PAGES.map(name => ({name, path: name, is_dir: false}))});
    navigator.sendBeacon = jest.fn(() => false);
    global.fetch = jest.fn(() => Promise.resolve({ok: true}));
});

afterEach(() => {
    global.fetch = realFetch;
    navigator.sendBeacon = realSendBeacon;
});

const saves = () => global.fetch.mock.calls.map(([, init]) => JSON.parse(init.body));

describe('CbzViewer progress', () => {
    test('opens at the saved page, and saves the page the reader leaves on', async () => {
        const fileGroup = {progress: 0.75, position: {kind: 'page', page: 2, updated_at: 1000}};
        const {unmount} = renderWithProviders(
            <CbzViewer path={PATH} progressPath={PATH} fileGroup={fileGroup}/>);

        expect(await screen.findByText('3 / 4')).toBeInTheDocument();
        expect(screen.getByAltText('Page 3')).toHaveAttribute('src', '/member/03.jpg');

        fireEvent.click(screen.getByLabelText('Next page'));
        expect(screen.getByText('4 / 4')).toBeInTheDocument();

        unmount();
        expect(saves()).toEqual([expect.objectContaining({
            file: PATH, progress: 1, final: true, position: expect.objectContaining({kind: 'page', page: 3}),
        })]);
    });

    test('a saved page past the end opens the last page', async () => {
        const fileGroup = {progress: 0.5, position: {kind: 'page', page: 40, updated_at: 1000}};
        renderWithProviders(<CbzViewer path={PATH} progressPath={PATH} fileGroup={fileGroup}/>);
        expect(await screen.findByText('4 / 4')).toBeInTheDocument();
    });

    test('without a progress path it opens at the first page and saves nothing', async () => {
        const fileGroup = {progress: 0.75, position: {kind: 'page', page: 2, updated_at: 1000}};
        const {unmount} = renderWithProviders(<CbzViewer path={PATH} fileGroup={fileGroup}/>);
        expect(await screen.findByText('1 / 4')).toBeInTheDocument();
        await act(async () => fireEvent.click(screen.getByLabelText('Next page')));
        unmount();
        expect(saves()).toEqual([]);
    });

    test('opening a comic saves nothing, so a finished comic stays finished', async () => {
        const fileGroup = {progress: 1, position: null, viewed: new Date(9000).toISOString()};
        const {unmount} = renderWithProviders(<CbzViewer path={PATH} progressPath={PATH} fileGroup={fileGroup}/>);
        expect(await screen.findByText('1 / 4')).toBeInTheDocument();
        unmount();
        expect(saves()).toEqual([]);
    });

    test('peeking at the cover keeps the reader\'s place', async () => {
        const fileGroup = {progress: 0.75, position: {kind: 'page', page: 2, updated_at: 1000}};
        const {unmount} = renderWithProviders(<CbzViewer path={PATH} progressPath={PATH} fileGroup={fileGroup}/>);
        expect(await screen.findByText('3 / 4')).toBeInTheDocument();
        fireEvent.click(screen.getByLabelText('Previous page'));
        fireEvent.click(screen.getByLabelText('Previous page'));
        expect(screen.getByText('1 / 4')).toBeInTheDocument();
        unmount();
        expect(saves()).toEqual([expect.objectContaining({position: expect.objectContaining({page: 1})})]);
    });
});
