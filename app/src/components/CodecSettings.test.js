import React from 'react';
import {screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {CodecSettingsForm} from './Download';
import {createTestForm, renderUI} from '../test-utils';

/** createTestForm implements getCustomProps but not getSelectionProps (used by
 * MultiSelectField); the shapes are compatible for these tests. */
const createCodecForm = (initialData) => {
    const form = createTestForm(initialData);
    form.getSelectionProps = form.getCustomProps;
    return form;
};

describe('CodecSettingsForm', () => {
    it('renders codec selectors and toggles', () => {
        const form = createCodecForm({settings: {video_codecs: ['h264'], audio_codecs: []}});

        renderUI(<CodecSettingsForm form={form}/>);

        expect(screen.getByText('Video Codecs')).toBeInTheDocument();
        expect(screen.getByText('Audio Codecs')).toBeInTheDocument();
        expect(screen.getByText('Transcode to preferred codecs')).toBeInTheDocument();
        expect(screen.getByText('Fail if codecs unavailable')).toBeInTheDocument();
    });

    it('keeps the strict toggle usable while transcode is enabled', () => {
        // Strict still matters with transcode on: a preference with no transcode target
        // (e.g. av1) cannot be fixed by transcoding, so the backend honors strict then.
        const form = createCodecForm({settings: {transcode: true, strict_codecs: true}});

        renderUI(<CodecSettingsForm form={form}/>);

        const toggles = screen.getAllByTestId('toggle');
        const [transcodeToggle, strictToggle] = toggles.map(i => i.querySelector('input') || i);
        expect(transcodeToggle).toBeChecked();
        expect(strictToggle).toBeChecked();
        expect(strictToggle).not.toBeDisabled();
    });

    it('toggling strict updates the form', async () => {
        const form = createCodecForm({settings: {transcode: false, strict_codecs: false}});

        renderUI(<CodecSettingsForm form={form}/>);

        const toggles = screen.getAllByTestId('toggle');
        const [, strictToggle] = toggles.map(i => i.querySelector('input') || i);
        expect(strictToggle).not.toBeDisabled();

        await userEvent.click(strictToggle);
        expect(form.formData.settings.strict_codecs).toBe(true);
    });
});
