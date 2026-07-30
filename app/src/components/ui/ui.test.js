import React from 'react';
import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MantineProvider} from '@mantine/core';
import {IconMoodSmile} from '@tabler/icons-react';
import {ThemeContext} from '../../contexts/contexts';
import {cssVariablesResolver, mantineTheme, semanticColorNames} from '../../themes/mantine';
import {themeChoices} from '../../themes/names';
import {
    ActionInput,
    Button,
    Confirm,
    Header,
    Icon,
    IconButton,
    Label,
    Message,
    Panel,
    Progress,
    resolveIconName,
    Status,
    Table,
    ThemePicker,
    Toggle,
} from './index';

// The components need Mantine's provider, exactly as ThemeProvider supplies it.
const renderUI = (ui) => render(
    <MantineProvider theme={mantineTheme} cssVariablesResolver={cssVariablesResolver}>
        {ui}
    </MantineProvider>
);

describe('Icon', () => {
    it('renders a Semantic name as an SVG', () => {
        const {container} = renderUI(<Icon name='trash'/>);

        expect(container.querySelector('svg')).toBeInTheDocument();
    });

    it('accepts a Tabler component directly', () => {
        const {container} = renderUI(<Icon component={IconMoodSmile}/>);

        expect(container.querySelector('svg')).toBeInTheDocument();
    });

    it('maps every Semantic icon name the app uses', () => {
        // A name that falls through renders a fallback glyph, leaving a hole in the UI.
        const names = ['trash', 'warning sign', 'download', 'refresh', 'plus', 'edit', 'wifi',
            'search', 'lock', 'check', 'upload', 'play', 'folder', 'filter', 'file text',
            'external', 'disk', 'circle notched', 'terminal', 'eye'];

        const unmapped = names.filter(name => !resolveIconName(name));

        expect(unmapped).toEqual([]);
    });

    it('hides decorative icons from assistive technology but names labelled ones', () => {
        const {container} = renderUI(<><Icon name='trash'/><Icon name='trash' label='Delete'/></>);

        const [decorative, labelled] = [...container.querySelectorAll('svg')];
        expect(decorative).toHaveAttribute('aria-hidden', 'true');
        expect(labelled).toHaveAttribute('aria-label', 'Delete');
        expect(labelled).not.toHaveAttribute('aria-hidden');
    });

    it('maps every icon the theme choices ask for', () => {
        // Regression: the map was built by grepping literal name='...' strings, so icons
        // passed through a variable (the nav bar's picker) were missed and three of the
        // five theme choices rendered a fallback glyph.
        const unmapped = themeChoices.filter(choice => !resolveIconName(choice.icon));

        expect(unmapped.map(c => `${c.text}: ${c.icon}`)).toEqual([]);
    });

    it('reports an unknown name instead of failing silently', () => {
        const error = jest.spyOn(console, 'error').mockImplementation(() => {});

        renderUI(<Icon name='not a real icon'/>);

        expect(error).toHaveBeenCalledWith(expect.stringContaining('not a real icon'));
        error.mockRestore();
    });
});

describe('Button', () => {
    it('renders a role as a themed button', () => {
        renderUI(<Button role='primary'>Download</Button>);

        expect(screen.getByRole('button', {name: 'Download'})).toBeInTheDocument();
    });

    it('marks destructive buttons so night mode can restyle them', () => {
        // The dashed-outline treatment lives in CSS keyed on this class; without it a
        // Delete button would stay filled red in night mode.
        renderUI(<Button role='danger'>Delete</Button>);

        expect(screen.getByRole('button', {name: 'Delete'})).toHaveClass('wrolpi-button-danger');
    });

    it('lets a call site override the role colors', () => {
        renderUI(<Button role='primary' variant='outline'>Odd one out</Button>);

        expect(screen.getByRole('button', {name: 'Odd one out'})).toHaveAttribute('data-variant', 'outline');
    });

    it('renders an icon alongside the label', () => {
        const {container} = renderUI(<Button role='save' icon='save'>Save</Button>);

        expect(container.querySelector('svg')).toBeInTheDocument();
        expect(screen.getByRole('button', {name: 'Save'})).toBeInTheDocument();
    });

    it('gives icon-only buttons an accessible name', () => {
        renderUI(<IconButton icon='trash' label='Delete channel'/>);

        expect(screen.getByRole('button', {name: 'Delete channel'})).toBeInTheDocument();
    });
});

describe('Message', () => {
    it('announces errors assertively and other kinds politely', () => {
        renderUI(<><Message kind='error' title='Failed'/><Message kind='info' title='Working'/></>);

        expect(screen.getByRole('alert')).toHaveTextContent('Failed');
        expect(screen.getByRole('status')).toHaveTextContent('Working');
    });

    it('gives errors the dashed danger border in every theme', () => {
        renderUI(<Message kind='error' title='Failed'>Try again</Message>);

        expect(screen.getByRole('alert')).toHaveClass('wrolpi-message-error');
    });

    it('dismisses when asked', async () => {
        const onDismiss = jest.fn();
        renderUI(<Message title='Install the extension' onDismiss={onDismiss}/>);

        await userEvent.click(screen.getByRole('button', {name: 'Dismiss'}));

        expect(onDismiss).toHaveBeenCalled();
    });

    it('offers no dismiss button when the message cannot be cleared', () => {
        renderUI(<Message title='Refresh running'/>);

        expect(screen.queryByRole('button', {name: 'Dismiss'})).not.toBeInTheDocument();
    });

    it('renders a leading icon when given one', () => {
        const {container} = renderUI(<Message icon='puzzle piece' title='Extension'/>);

        expect(container.querySelector('.wrolpi-message-icon svg')).toBeInTheDocument();
    });
});

describe('Header', () => {
    it('renders the requested heading level', () => {
        renderUI(<Header as='h1'>Browser Extension</Header>);

        expect(screen.getByRole('heading', {level: 1, name: 'Browser Extension'})).toBeInTheDocument();
    });

    it('defaults to h3 so a call site that omits the level still nests sanely', () => {
        renderUI(<Header>Firefox</Header>);

        expect(screen.getByRole('heading', {level: 3, name: 'Firefox'})).toBeInTheDocument();
    });

    it('takes its size from the level, not from the call site', () => {
        // The class is what ui.css keys the type scale on; a call site passing its own
        // font-size is the thing this component exists to prevent.
        const {container} = renderUI(<Header as='h4'>Install steps</Header>);

        expect(container.querySelector('.wrolpi-header-h4')).toBeInTheDocument();
    });

    it('renders an icon and a subheader', () => {
        const {container} = renderUI(<Header icon='globe' subheader='Paste this into the extension'>
            This WROLPi's URL
        </Header>);

        expect(container.querySelector('svg')).toBeInTheDocument();
        expect(screen.getByText('Paste this into the extension')).toBeInTheDocument();
    });
});

describe('ActionInput', () => {
    it('joins the input and its action into one control', () => {
        const {container} = renderUI(
            <ActionInput label='URL' value='https://wrolpi.local' readOnly
                         action={<Button role='cancel'>Copy</Button>}/>
        );

        expect(container.querySelector('.wrolpi-action-input')).toBeInTheDocument();
        expect(screen.getByRole('textbox', {name: 'URL'})).toHaveValue('https://wrolpi.local');
        expect(screen.getByRole('button', {name: 'Copy'})).toBeInTheDocument();
    });

    it('is a plain input when no action is given', () => {
        const {container} = renderUI(<ActionInput label='URL'/>);

        expect(container.querySelector('.wrolpi-action-input')).not.toBeInTheDocument();
        expect(screen.getByRole('textbox', {name: 'URL'})).toBeInTheDocument();
    });
});

describe('Progress', () => {
    it('reports its value to assistive technology', () => {
        renderUI(<Progress percent={62}/>);

        const bar = screen.getByRole('progressbar');
        expect(bar).toHaveAttribute('aria-valuenow', '62');
        expect(bar).toHaveTextContent('62%');
    });

    it('clamps values outside 0-100', () => {
        // A download reporting 103% must not overflow its container.
        renderUI(<><Progress percent={150}/><Progress percent={-20}/></>);

        const [high, low] = screen.getAllByRole('progressbar');
        expect(high).toHaveAttribute('aria-valuenow', '100');
        expect(low).toHaveAttribute('aria-valuenow', '0');
    });

    it('survives a missing percentage', () => {
        renderUI(<Progress percent={undefined}/>);

        expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
    });

    it('shows arbitrary label text instead of the percentage', () => {
        renderUI(<Progress percent={40} label='2.1 GB / 5.3 GB'/>);

        expect(screen.getByRole('progressbar')).toHaveTextContent('2.1 GB / 5.3 GB');
    });
});

describe('Status', () => {
    it('names the state in a class so themes can encode it differently', () => {
        // Night mode has no hue to spend, so it encodes status by brightness.
        const {container} = renderUI(<Status kind='failed'>failed</Status>);

        expect(container.querySelector('.wrolpi-status-failed')).toBeInTheDocument();
    });
});

describe('Label', () => {
    it('supports every Semantic color', () => {
        const {container} = renderUI(<>
            {semanticColorNames.map(color => <Label key={color} color={color}>{color}</Label>)}
        </>);

        expect(container.querySelectorAll('.wrolpi-label')).toHaveLength(semanticColorNames.length);
    });
});

describe('Table', () => {
    it('renders a Semantic-shaped compound table', () => {
        renderUI(<Table>
            <Table.Header>
                <Table.Row><Table.HeaderCell>URL</Table.HeaderCell></Table.Row>
            </Table.Header>
            <Table.Body>
                <Table.Row><Table.Cell>example.com</Table.Cell></Table.Row>
            </Table.Body>
        </Table>);

        expect(screen.getByRole('columnheader', {name: 'URL'})).toBeInTheDocument();
        expect(screen.getByRole('cell', {name: 'example.com'})).toBeInTheDocument();
    });

    it('marks failed rows for the danger border', () => {
        const {container} = renderUI(<Table>
            <Table.Body>
                <Table.Row failed><Table.Cell>broken</Table.Cell></Table.Row>
            </Table.Body>
        </Table>);

        expect(container.querySelector('.wrolpi-row-failed')).toBeInTheDocument();
    });

    it('keeps wide tables from scrolling the page sideways', () => {
        const {container} = renderUI(<Table><Table.Body>
            <Table.Row><Table.Cell>wide</Table.Cell></Table.Row>
        </Table.Body></Table>);

        expect(container.querySelector('.wrolpi-table-scroll')).toBeInTheDocument();
    });
});

describe('Panel', () => {
    it('marks danger zones', () => {
        const {container} = renderUI(<Panel danger>Destructive actions</Panel>);

        expect(container.querySelector('.wrolpi-panel-danger')).toBeInTheDocument();
    });
});

describe('Toggle', () => {
    it('carries the class its unchecked-track rule needs', () => {
        // Mantine writes --switch-bg onto the track element, so the token override has to
        // be a CSS rule scoped to this class rather than a style on the root.  Without it
        // the unchecked track falls back to Mantine's gray — a non-red pixel in night mode.
        const {container} = renderUI(<Toggle label='Hotspot'/>);

        expect(container.querySelector('.wrolpi-switch')).toBeInTheDocument();
    });

    it('exposes the switch role and reports its state', async () => {
        const onChange = jest.fn();
        renderUI(<Toggle label='Hotspot' checked={false} onChange={onChange}/>);

        const toggle = screen.getByRole('switch', {name: 'Hotspot'});
        expect(toggle).not.toBeChecked();
        await userEvent.click(toggle);

        expect(onChange).toHaveBeenCalled();
    });
});

describe('ThemePicker', () => {
    const renderPicker = (themeContext = {}) => {
        const setTheme = jest.fn();
        const value = {
            savedTheme: null,
            setTheme,
            mediaFilterEnabled: false,
            setMediaFilterEnabled: jest.fn(),
            ...themeContext,
        };
        render(
            <MantineProvider theme={mantineTheme} cssVariablesResolver={cssVariablesResolver}>
                <ThemeContext.Provider value={value}><ThemePicker/></ThemeContext.Provider>
            </MantineProvider>
        );
        return setTheme;
    };

    it('offers every theme plus following the system', () => {
        renderPicker();

        const options = screen.getAllByRole('radio').map(o => o.textContent);
        ['System', 'Light', 'Dark', 'Night', 'Amber'].forEach(name => {
            expect(options.some(text => text.startsWith(name))).toBe(true);
        });
    });

    it('marks the saved theme as selected', () => {
        renderPicker({savedTheme: 'night'});

        const night = screen.getAllByRole('radio').find(o => o.textContent.startsWith('Night'));
        expect(night).toHaveAttribute('aria-checked', 'true');
    });

    it('treats a user who has never chosen as following the system', () => {
        renderPicker({savedTheme: null});

        const system = screen.getAllByRole('radio').find(o => o.textContent.startsWith('System'));
        expect(system).toHaveAttribute('aria-checked', 'true');
    });

    it('applies the theme a user picks', async () => {
        const setTheme = renderPicker();

        await userEvent.click(screen.getAllByRole('radio').find(o => o.textContent.startsWith('Amber')));

        expect(setTheme).toHaveBeenCalledWith('amber');
    });

    it('explains what night mode is for', () => {
        // Users need to know it filters media too, not just the interface.
        renderPicker();

        expect(screen.getByText(/night vision/i)).toBeInTheDocument();
    });

    it('offers the media filter toggle in a theme that has one', () => {
        renderPicker({
            theme: 'night',
            mediaFilter: {id: 'night-red', defaultOn: true, label: 'Filter media to red',
                description: 'Videos, images, documents, and maps are remapped to red.'},
            mediaFilterEnabled: true,
        });

        expect(screen.getByRole('switch', {name: /filter media to red/i})).toBeChecked();
    });

    it('offers no toggle in a theme with no filter to offer', () => {
        // Light and dark have no monochrome media treatment, so there is nothing to say.
        renderPicker({theme: 'light', mediaFilter: undefined, mediaFilterEnabled: false});

        expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    });

    it('turns the filter off when the user flips the toggle', async () => {
        const setMediaFilterEnabled = jest.fn();
        renderPicker({
            theme: 'night',
            mediaFilter: {id: 'night-red', defaultOn: true, label: 'Filter media to red',
                description: 'Videos, images, documents, and maps are remapped to red.'},
            mediaFilterEnabled: true,
            setMediaFilterEnabled,
        });

        await userEvent.click(screen.getByRole('switch', {name: /filter media to red/i}));

        expect(setMediaFilterEnabled).toHaveBeenCalledWith(false);
    });
});

describe('Confirm', () => {
    it('names the action on its confirming button', async () => {
        const onConfirm = jest.fn();
        renderUI(<Confirm open destructive title='Delete channel?' confirmLabel='Delete'
                          onConfirm={onConfirm}/>);

        await userEvent.click(screen.getByRole('button', {name: 'Delete'}));

        expect(onConfirm).toHaveBeenCalled();
    });

    it('styles a destructive confirmation as destructive', () => {
        renderUI(<Confirm open destructive confirmLabel='Wipe' title='Wipe history?'/>);

        expect(screen.getByRole('button', {name: 'Wipe'})).toHaveClass('wrolpi-button-danger');
    });
});
