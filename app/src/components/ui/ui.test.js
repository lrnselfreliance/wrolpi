import fs from 'fs';
import path from 'path';
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
    Card,
    Confirm,
    Header,
    Icon,
    IconStack,
    Pagination,
    SearchBox,
    TabBar,
    tabClassName,
    IconButton,
    Label,
    Message,
    Modal,
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

    it('maps every name the mimetype and file-suffix helpers can return', () => {
        // These two build icon names from arbitrary files in the user's library, so an
        // unmapped one is not hypothetical — it is a console error and a fallback glyph
        // the moment somebody opens a folder containing that file type.
        const common = fs.readFileSync(path.join(__dirname, '..', 'Common.js'), 'utf8');
        const section = common.slice(
            common.indexOf('export function mimetypeIconName'),
            common.indexOf('export function FileIcon'));
        const returned = [...new Set([...section.matchAll(/return '([^']+)'/g)].map(m => m[1]))];

        expect(returned.length).toBeGreaterThan(10);
        expect(returned.filter(name => !resolveIconName(name))).toEqual([]);
    });

    it('points every mapped name at a Tabler component that exists', () => {
        // A typo in the map resolves to undefined and renders the fallback glyph, which
        // looks like a design choice rather than a bug.
        const source = fs.readFileSync(path.join(__dirname, 'Icon.tsx'), 'utf8');
        const names = [...source.matchAll(/^ {4}'([^']+)': '([^']+)',$/gm)].map(m => m[1]);

        expect(names.length).toBeGreaterThan(100);
        expect(names.filter(name => !resolveIconName(name))).toEqual([]);
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

    it('translates Semantic size names, which Mantine would otherwise ignore', () => {
        // Unmigrated call sites still pass size='tiny'.  Mantine drops a size it does not
        // recognise without warning, so the button quietly renders at the default size.
        renderUI(<><Button size='tiny'>Old</Button><Button size='sm'>New</Button></>);

        expect(screen.getByRole('button', {name: 'Old'})).toHaveAttribute('data-size', 'xs');
        // A Mantine size still passes through untouched.
        expect(screen.getByRole('button', {name: 'New'})).toHaveAttribute('data-size', 'sm');
    });

    it('renders an anchor when given an href, without being told twice', () => {
        /*
         * Mantine drops `href` unless it also gets `component='a'`, so a button carrying
         * only an href looked like a link and navigated nowhere.  Semantic spelled this
         * `as='a'`, so every migrated call site that kept just the href was silently
         * broken — a download button that downloads nothing.
         */
        renderUI(<>
            <Button href='/media/thing.pdf'>Download</Button>
            <IconButton icon='download' label='Save file' href='/media/other.pdf'/>
        </>);

        const link = screen.getByRole('link', {name: 'Download'});
        expect(link.tagName).toBe('A');
        expect(link).toHaveAttribute('href', '/media/thing.pdf');
        expect(screen.getByRole('link', {name: 'Save file'}).tagName).toBe('A');
    });

    it('forwards a ref to the underlying DOM element', () => {
        /*
         * Ported from the old Theme.test.js, which caught a real crash: Semantic's Button
         * was a class component, so a forwarded ref resolved to the class instance, and
         * anything that called `node.contains(...)` on the trigger -- a Modal or Popup
         * portal checking whether a click landed inside -- threw "contains is not a
         * function".  Our Tooltip and Menu targets rely on this ref too.
         */
        const ref = React.createRef();
        renderUI(<Button ref={ref}>Click</Button>);

        expect(ref.current).toBeInstanceOf(HTMLElement);
        expect(typeof ref.current.contains).toBe('function');
        expect(ref.current.tagName).toBe('BUTTON');
    });

    it('survives a document click while used as a modal trigger', () => {
        // The other half of that regression: the Control page crashed when the document
        // was clicked with a modal open whose trigger was a themed Button.
        renderUI(<>
            <Button>Open</Button>
            <Modal open onClose={jest.fn()}><Modal.Content>content</Modal.Content></Modal>
        </>);

        expect(() => document.body.dispatchEvent(new MouseEvent('click', {bubbles: true})))
            .not.toThrow();
    });

    it('is still a button when there is no href', () => {
        renderUI(<Button onClick={jest.fn()}>Save</Button>);

        expect(screen.getByRole('button', {name: 'Save'}).tagName).toBe('BUTTON');
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

    it('keeps its percent text readable on every bar colour', () => {
        /*
         * Ported from Theme.test.js, which asserted Semantic's `inverted-progress-text`
         * class across all fourteen colours and both modes.  That class is gone; the
         * mechanism now is that the text always takes `--text` while light mode lightens
         * the fill beneath it, because the text sits across both the filled and unfilled
         * halves of the bar.
         */
        const css = fs.readFileSync(path.join(__dirname, 'ui.css'), 'utf8');

        expect(css).toMatch(/\.wrolpi-progress-text\s*{[^}]*color:\s*var\(--text\)/);
        expect(css).toMatch(/html\[data-theme="light"] \.wrolpi-progress-fill\s*{[^}]*brightness/);
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

    it('reports no value when the size is unknown', () => {
        // Semantic called this `indicating`.  An upload that has not reported its size
        // would otherwise sit at 0% and read as stalled, and `aria-valuenow=0` would tell
        // a screen reader the same wrong thing.
        renderUI(<Progress indeterminate label='Uploading…'/>);

        const bar = screen.getByRole('progressbar');
        expect(bar).not.toHaveAttribute('aria-valuenow');
        expect(bar).toHaveClass('wrolpi-progress-indeterminate');
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

    it('makes a sortable column a keyboard-reachable button that announces its state', async () => {
        // A click handler on the <th> alone is unreachable by keyboard, and the arrow
        // glyph says nothing to a screen reader.
        const onSort = jest.fn();
        renderUI(<Table>
            <Table.Header>
                <Table.Row>
                    <Table.HeaderCell sorted='descending' onSort={onSort}>Size</Table.HeaderCell>
                    <Table.HeaderCell onSort={jest.fn()}>Name</Table.HeaderCell>
                    <Table.HeaderCell>Actions</Table.HeaderCell>
                </Table.Row>
            </Table.Header>
        </Table>);

        expect(screen.getByRole('columnheader', {name: /Size/})).toHaveAttribute('aria-sort', 'descending');
        // Sortable but not currently sorted.
        expect(screen.getByRole('columnheader', {name: /Name/})).toHaveAttribute('aria-sort', 'none');
        // Not sortable at all.
        expect(screen.getByRole('columnheader', {name: 'Actions'})).not.toHaveAttribute('aria-sort');

        await userEvent.click(screen.getByRole('button', {name: /Size/}));
        expect(onSort).toHaveBeenCalled();
    });

    it('keeps wide tables from scrolling the page sideways', () => {
        const {container} = renderUI(<Table><Table.Body>
            <Table.Row><Table.Cell>wide</Table.Cell></Table.Row>
        </Table.Body></Table>);

        expect(container.querySelector('.wrolpi-table-scroll')).toBeInTheDocument();
    });
});

describe('Card', () => {
    it('draws a mimetype accent from a token, not a hex', () => {
        // File cards carry the mimetype's colour on their top edge so a grid of results is
        // scannable by kind.  Semantic did this with `<Card color='violet'>`; two migrated
        // files had dropped the accent because our Card had no equivalent.
        const {container} = renderUI(<Card title='Water Storage.pdf' color='red'/>);

        expect(container.firstChild).toHaveStyle({borderBottom: '3px solid var(--red)'});
    });

    it('has no accent when no colour is given', () => {
        const {container} = renderUI(<Card title='Plain'/>);

        expect(container.firstChild.style.borderBottom).toBe('');
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

describe('Pagination', () => {
    it('reports the current page and moves when one is clicked', async () => {
        const onPageChange = jest.fn();
        renderUI(<Pagination activePage={3} totalPages={12} onPageChange={onPageChange}/>);

        await userEvent.click(screen.getByRole('button', {name: 'Page 5'}));

        expect(onPageChange).toHaveBeenCalledWith(5);
    });

    it('still renders one page when the total is unknown', () => {
        // Downloads render the paginator before the first response arrives; collapsing to
        // nothing and back shifts the whole page.
        renderUI(<Pagination activePage={1} totalPages={undefined} onPageChange={jest.fn()}/>);

        expect(screen.getByRole('button', {name: 'Page 1'})).toBeInTheDocument();
    });
});

describe('TabBar', () => {
    it('marks the active tab with a class the themes key on', () => {
        const {container} = renderUI(<TabBar>
            <button className={tabClassName(true)}>Videos</button>
            <button className={tabClassName(false)}>Channels</button>
        </TabBar>);

        expect(container.querySelectorAll('.wrolpi-tab')).toHaveLength(2);
        expect(container.querySelectorAll('.wrolpi-tab-active')).toHaveLength(1);
    });
});

describe('SearchBox', () => {
    const results = {
        directories: {name: 'Directories', results: [{title: 'videos/'}]},
        channels: {name: 'Channels', results: [
            {title: 'videos/Wranglerstar', description: 'Wranglerstar'},
            {title: 'videos/RoseRed', description: 'RoseRed Homestead'},
        ]},
    };

    it('submits what was typed', async () => {
        const onSubmit = jest.fn();
        renderUI(<SearchBox value='axe' onChange={jest.fn()} onSubmit={onSubmit}/>);

        await userEvent.type(screen.getByRole('textbox'), '{Enter}');

        expect(onSubmit).toHaveBeenCalledWith('axe');
    });

    it('shows suggestions under their group headings', async () => {
        renderUI(<SearchBox value='vid' onChange={jest.fn()} results={results}
                            onResultSelect={jest.fn()}/>);

        await userEvent.click(screen.getByRole('combobox'));

        expect(screen.getByText('Directories')).toBeInTheDocument();
        expect(screen.getAllByRole('option')).toHaveLength(3);
    });

    it('selects a suggestion by click', async () => {
        const onResultSelect = jest.fn();
        renderUI(<SearchBox value='vid' onChange={jest.fn()} results={results}
                            onResultSelect={onResultSelect}/>);
        await userEvent.click(screen.getByRole('combobox'));

        await userEvent.click(screen.getByText('videos/Wranglerstar'));

        expect(onResultSelect).toHaveBeenCalledWith(
            expect.objectContaining({title: 'videos/Wranglerstar'}));
    });

    it('moves through suggestions with the arrow keys and takes one with Enter', async () => {
        const onResultSelect = jest.fn();
        const onSubmit = jest.fn();
        renderUI(<SearchBox value='vid' onChange={jest.fn()} results={results}
                            onResultSelect={onResultSelect} onSubmit={onSubmit}/>);

        const input = screen.getByRole('combobox');
        await userEvent.click(input);
        await userEvent.keyboard('{ArrowDown}{ArrowDown}{Enter}');

        expect(onResultSelect).toHaveBeenCalledWith(
            expect.objectContaining({title: 'videos/Wranglerstar'}));
        // Enter took the highlighted suggestion instead of submitting the raw text.
        expect(onSubmit).not.toHaveBeenCalled();
    });

    it('wraps around rather than stranding the user at the end of the list', async () => {
        const onResultSelect = jest.fn();
        renderUI(<SearchBox value='vid' onChange={jest.fn()} results={results}
                            onResultSelect={onResultSelect}/>);

        await userEvent.click(screen.getByRole('combobox'));
        await userEvent.keyboard('{ArrowUp}{Enter}');

        expect(onResultSelect).toHaveBeenCalledWith(
            expect.objectContaining({title: 'videos/RoseRed'}));
    });

    it('lets a caller render a suggestion its own way', async () => {
        // The search suggestions render a tag as a chip rather than a line of text; a
        // dropped resultRenderer loses that presentation silently.
        renderUI(<SearchBox value='vid' onChange={jest.fn()} results={results}
                            onResultSelect={jest.fn()}
                            resultRenderer={result => <em>{`custom: ${result.title}`}</em>}/>);

        await userEvent.click(screen.getByRole('combobox'));

        expect(screen.getByText('custom: videos/Wranglerstar').tagName).toBe('EM');
        // The default title/description markup is replaced, not wrapped.
        expect(document.querySelector('.wrolpi-searchbox-result-title')).not.toBeInTheDocument();
    });

    it('closes on Escape without clearing what was typed', async () => {
        const onChange = jest.fn();
        renderUI(<SearchBox value='vid' onChange={onChange} results={results}
                            onResultSelect={jest.fn()}/>);
        await userEvent.click(screen.getByRole('combobox'));

        await userEvent.keyboard('{Escape}');

        expect(screen.queryByRole('option')).not.toBeInTheDocument();
        expect(screen.getByRole('combobox')).toHaveValue('vid');
        expect(onChange).not.toHaveBeenCalled();
    });

    it('says it is searching rather than "no results" while suggestions are pending', async () => {
        renderUI(<SearchBox value='vid' onChange={jest.fn()} results={{}} loading
                            onResultSelect={jest.fn()}/>);

        await userEvent.click(screen.getByRole('combobox'));

        expect(screen.getByText(/searching/i)).toBeInTheDocument();
    });

    it('clears the input and submits the empty search', async () => {
        const onChange = jest.fn();
        const onSubmit = jest.fn();
        renderUI(<SearchBox value='axe' onChange={onChange} onSubmit={onSubmit} clearable/>);

        await userEvent.click(screen.getByRole('button', {name: 'Clear search'}));

        expect(onChange).toHaveBeenCalledWith('');
        expect(onSubmit).toHaveBeenCalledWith('');
    });

    it('is a plain search field when no suggestions are wired up', () => {
        // Without this, a box that can never show options still claims to be a combobox.
        renderUI(<SearchBox value='' onChange={jest.fn()} onSubmit={jest.fn()}/>);

        expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
        expect(screen.getByRole('textbox')).toBeInTheDocument();
    });
});

describe('IconStack', () => {
    it('names the pair once, and hides the corner glyph from assistive tech', () => {
        const {container} = renderUI(
            <IconStack corner={<Icon name='question'/>} label='WiFi status unknown'>
                <Icon name='wifi'/>
            </IconStack>
        );

        expect(screen.getByRole('img', {name: 'WiFi status unknown'})).toBeInTheDocument();
        expect(container.querySelector('.wrolpi-icon-stack-corner')).toHaveAttribute('aria-hidden', 'true');
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
