import {centerAutoCaptions} from './VideoPlayer';

// Build a fake TextTrack whose cues mimic what the browser parses from a .vtt file.
const makeTrack = (cues) => ({cues});

describe('centerAutoCaptions', () => {
    test('re-centers YouTube auto-caption cues (align:start position:0%)', () => {
        const track = makeTrack([
            {align: 'start', position: 0, line: 'auto', size: 100, text: 'hello'},
            {align: 'start', position: 0, line: 'auto', size: 100, text: 'world'},
        ]);

        const changed = centerAutoCaptions(track);

        expect(changed).toBe(2);
        for (const cue of track.cues) {
            expect(cue.align).toBe('center');
            expect(cue.position).toBe('auto');
            expect(cue.line).toBe('auto');
        }
    });

    test('leaves deliberately-positioned cues untouched', () => {
        const track = makeTrack([
            // Already centered (no cue settings in the .vtt file).
            {align: 'center', position: 'auto', line: 'auto'},
            // Deliberately placed at the top, right-aligned.
            {align: 'end', position: 90, line: 0},
        ]);

        const changed = centerAutoCaptions(track);

        expect(changed).toBe(0);
        expect(track.cues[0].align).toBe('center');
        expect(track.cues[1].align).toBe('end');
        expect(track.cues[1].position).toBe(90);
        expect(track.cues[1].line).toBe(0);
    });

    test('handles a track with no cues yet (mode disabled)', () => {
        expect(centerAutoCaptions({cues: null})).toBe(0);
        expect(centerAutoCaptions(null)).toBe(0);
        expect(centerAutoCaptions(undefined)).toBe(0);
    });

    test('only normalizes the auto-caption cues in a mixed track', () => {
        const track = makeTrack([
            {align: 'start', position: 0, line: 'auto'},
            {align: 'end', position: 90, line: 0},
        ]);

        const changed = centerAutoCaptions(track);

        expect(changed).toBe(1);
        expect(track.cues[0].align).toBe('center');
        expect(track.cues[1].align).toBe('end');
    });
});
