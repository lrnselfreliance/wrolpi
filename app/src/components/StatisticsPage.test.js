import React from 'react';
import {act, render, screen} from '../test-utils';
import {StatisticsPage} from './Apps';
import {getStatistics} from '../api';

// What the Statistics page shows while the numbers are still loading, when the fetch failed, and
// once they arrive.  "Failed to fetch statistics" may only appear for a failed fetch.

jest.mock('../api', () => ({
    ...jest.requireActual('../api'),
    getStatistics: jest.fn(),
}));

const FAILED = /Failed to fetch statistics/;
const STATS = {
    global_statistics: {db_size: 1024},
    file_statistics: {
        archive_count: 1, audio_count: 2, ebook_count: 3, image_count: 4, pdf_count: 5, total_count: 21,
        video_count: 6, zip_count: 0, total_size: 4096, tagged_files: 7, tagged_zims: 0, tags_count: 2,
    },
};

beforeEach(() => getStatistics.mockReset());

test('pending: shows a loader, not the error', () => {
    getStatistics.mockReturnValue(new Promise(() => {
    }));
    const {container} = render(<StatisticsPage/>);
    expect(container.querySelector('.wrolpi-loading')).toBeInTheDocument();
    expect(screen.queryByText(FAILED)).not.toBeInTheDocument();
});

test('failed: shows the error', async () => {
    // The api helper toasts and returns undefined on a non-OK response.
    getStatistics.mockResolvedValue(undefined);
    render(<StatisticsPage/>);
    await act(async () => {
    });
    expect(screen.getByText(FAILED)).toBeInTheDocument();
});

test('loaded: shows the numbers', async () => {
    getStatistics.mockResolvedValue(STATS);
    render(<StatisticsPage/>);
    await act(async () => {
    });
    expect(screen.getByText('All Files')).toBeInTheDocument();
    expect(screen.queryByText(FAILED)).not.toBeInTheDocument();
});
