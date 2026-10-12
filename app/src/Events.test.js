import {handleEvents} from './Events';
import {toast} from './components/ui';

jest.mock('./components/ui', () => ({toast: jest.fn()}));

const notify = (url) => ({event: 'user_notify_message', message: 'Transcoding video.mp4', dt: '2026-10-12', url});

afterEach(() => {
    toast.mockClear();
});

describe('user_notify_message', () => {
    it('a notification without a URL is plain text, not a link', () => {
        handleEvents([notify(null)]);

        expect(toast).toHaveBeenCalledTimes(1);
        const options = toast.mock.calls[0][0];
        expect(options.title).toBe('Transcoding video.mp4');
        expect(options.description).toBeFalsy();
        expect(options.onClick).toBeFalsy();
    });

    it('a shared page opens its URL when clicked', () => {
        const open = jest.spyOn(window, 'open').mockImplementation(() => null);
        handleEvents([notify('/archive/1')]);

        const options = toast.mock.calls[0][0];
        expect(options.description).toBe('Click here to view the shared page');
        options.onClick();
        expect(open).toHaveBeenCalledWith('/archive/1', '_self');
        open.mockRestore();
    });
});
