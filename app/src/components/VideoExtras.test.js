import React from 'react';
import {render, screen} from '../test-utils';
import {Comments, VideoDescription} from './VideoPlayer';

// What the video page shows for each state of useVideoExtras.  The states are null (pending),
// undefined (fetch failed), and an empty value (loaded, nothing to show).  "No comments have been
// downloaded" carries a Refresh button that re-downloads the video, so it must only appear once
// the server has confirmed there are none.

const video = {id: 7, url: 'https://example.com/v'};
const NO_COMMENTS = /No comments have been/;
const NO_DESCRIPTION = /No description available/;

describe('Comments', () => {
    test('pending: shows a placeholder, not "no comments" or an error', () => {
        const {container} = render(<Comments comments={null} video={video}/>);
        expect(container.querySelector('.wrolpi-placeholder')).toBeInTheDocument();
        expect(screen.queryByText(NO_COMMENTS)).not.toBeInTheDocument();
        expect(screen.queryByText(/Could not/)).not.toBeInTheDocument();
        expect(screen.queryByRole('button', {name: 'Refresh'})).not.toBeInTheDocument();
    });

    test('failed: shows an error, not "no comments"', () => {
        render(<Comments comments={undefined} video={video}/>);
        expect(screen.getByText(/Could not fetch the comments/)).toBeInTheDocument();
        expect(screen.queryByText(NO_COMMENTS)).not.toBeInTheDocument();
    });

    test('empty: shows "no comments" with the Refresh button', () => {
        render(<Comments comments={[]} video={video}/>);
        expect(screen.getByText(NO_COMMENTS)).toBeInTheDocument();
        expect(screen.getByRole('button', {name: 'Refresh'})).toBeInTheDocument();
    });

    test('loaded: renders the comments', () => {
        render(<Comments comments={[{id: 'c1', parent: 'root', text: 'first!', author: 'a'}]} video={video}/>);
        expect(screen.getByText('first!')).toBeInTheDocument();
        expect(screen.queryByText(NO_COMMENTS)).not.toBeInTheDocument();
    });
});

describe('VideoDescription', () => {
    test('pending: shows a placeholder, not "no description" or an error', () => {
        const {container} = render(<VideoDescription description={null} setVideoTime={() => null}/>);
        expect(container.querySelector('.wrolpi-placeholder')).toBeInTheDocument();
        expect(screen.queryByText(NO_DESCRIPTION)).not.toBeInTheDocument();
        expect(screen.queryByText(/Could not/)).not.toBeInTheDocument();
    });

    test('failed: shows an error, not "no description"', () => {
        render(<VideoDescription description={undefined} setVideoTime={() => null}/>);
        expect(screen.getByText(/Could not fetch the description/)).toBeInTheDocument();
        expect(screen.queryByText(NO_DESCRIPTION)).not.toBeInTheDocument();
    });

    test('empty: shows "no description"', () => {
        render(<VideoDescription description='' setVideoTime={() => null}/>);
        expect(screen.getByText(NO_DESCRIPTION)).toBeInTheDocument();
    });

    test('loaded: renders the description', () => {
        render(<VideoDescription description='A fine video.' setVideoTime={() => null}/>);
        expect(screen.getByText('A fine video.')).toBeInTheDocument();
        expect(screen.queryByText(NO_DESCRIPTION)).not.toBeInTheDocument();
    });
});
