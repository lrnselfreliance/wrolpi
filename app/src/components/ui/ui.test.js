import React from 'react';
import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MantineProvider} from '@mantine/core';
import {IconMoodSmile} from '@tabler/icons-react';
import {ThemeContext} from '../../contexts/contexts';
import {cssVariablesResolver, mantineTheme, semanticColorNames} from '../../themes/mantine';
import {
    Button,
    Confirm,
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
        const value = {savedTheme: null, setTheme, ...themeContext};
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
