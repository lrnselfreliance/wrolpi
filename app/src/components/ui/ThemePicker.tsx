import React, {useContext} from 'react';
import {ThemeContext} from '../../contexts/contexts';
import {systemTheme, themeChoices} from '../../themes/names';
import {Icon} from './Icon';
import {Toggle} from './Inputs';

/*
 * The theme picker.
 *
 * Used on the Settings page.  The navigation bar has its own compact menu; both
 * read their options from `themeChoices` so they cannot drift apart.
 */

export interface ThemePickerProps {
    /** Show each theme's description under its name. */
    withDescriptions?: boolean;
}

/**
 * The media filter toggle for the current theme.
 *
 * Rendered only by themes that offer a filter, because there is nothing to say
 * about it otherwise — light and dark have no monochrome media treatment.
 */
export function MediaFilterToggle() {
    const {mediaFilter, mediaFilterEnabled, setMediaFilterEnabled} = useContext(ThemeContext);
    if (!mediaFilter) return null;

    return <div className='wrolpi-media-filter-setting'>
        <Toggle
            label={mediaFilter.label}
            description={mediaFilter.description}
            checked={mediaFilterEnabled}
            onChange={event => setMediaFilterEnabled(event.currentTarget.checked)}
        />
    </div>
}

export function ThemePicker({withDescriptions = true}: ThemePickerProps) {
    const {savedTheme, setTheme} = useContext(ThemeContext);
    // A user who has never chosen is following the system preference.
    const selected = savedTheme ?? systemTheme;

    return <>
        <div role='radiogroup' aria-label='Theme' className='wrolpi-theme-picker'>
            {themeChoices.map(choice => {
                const active = choice.value === selected;
                return <button
                    key={choice.value}
                    type='button'
                    role='radio'
                    aria-checked={active}
                    className={`wrolpi-theme-option${active ? ' wrolpi-theme-option-active' : ''}`}
                    onClick={() => setTheme(choice.value)}
                >
                    <span className='wrolpi-theme-option-name'>
                        <Icon name={choice.icon}/>
                        {choice.text}
                    </span>
                    {withDescriptions &&
                        <span className='wrolpi-theme-option-description'>{choice.description}</span>}
                </button>
            })}
        </div>
        <MediaFilterToggle/>
    </>
}
