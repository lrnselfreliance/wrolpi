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

    it('disables the strict toggle while transcode is enabled', () => {
        const form = createCodecForm({settings: {transcode: true, strict_codecs: false}});

        renderUI(<CodecSettingsForm form={form}/>);

        const toggles = screen.getAllByTestId('toggle');
        const [transcodeToggle, strictToggle] = toggles.map(i => i.querySelector('input') || i);
        expect(transcodeToggle).toBeChecked();
        expect(strictToggle).toBeDisabled();
    });

    it('enables the strict toggle while transcode is disabled', async () => {
        const form = createCodecForm({settings: {transcode: false, strict_codecs: false}});

        renderUI(<CodecSettingsForm form={form}/>);

        const toggles = screen.getAllByTestId('toggle');
        const [, strictToggle] = toggles.map(i => i.querySelector('input') || i);
        expect(strictToggle).not.toBeDisabled();

        await userEvent.click(strictToggle);
        expect(form.formData.settings.strict_codecs).toBe(true);
    });
});
