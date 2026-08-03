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
    CardGroup,
    Checkbox,
    Confirm,
    Header,
    Icon,
    IconStack,
    Loader,
    Loading,
    Placeholder,
    Pagination,
    SearchBox,
    TabBar,
    tabClassName,
    IconButton,
    Label,
    Message,
    Modal,
    Panel,
    PathInput,
    Progress,
    resolveIconName,
    Statistic,
    StatisticGroup,
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

    it('maps every icon name written anywhere in the app', () => {
        /*
         * The three checks above cover the theme picker, the mimetype helpers, and the map's
         * own integrity -- and between them they missed eleven names, because none of them
         * looks at what call sites actually write.  The calculators page had seven "?"
         * glyphs in a row: `cogs`, `tint`, `food`, `signal`, `thermometer`, `car`, `th
         * large`.  `arrow left` was missing while `arrow down`, `right` and `up` were there.
         *
         * An unmapped name is not subtle -- it is a help-circle glyph and a console error --
         * but nothing failed, so it shipped and stayed until somebody looked at the page.
         *
         * Every spelling matters, and each one hid a real defect:
         *   `<Icon name='x'/>` and `icon='x'`      -- the plain JSX prop
         *   `{icon: 'x'}`                          -- a data table; how calculators declare theirs
         *   `icon={active ? 'tags' : 'tag'}`       -- a ternary, where `tags` was unmapped
         * The last two are exactly the forms an audit by eye skips.
         */
        const patterns = [
            /<Icon\s[^>]*?\bname=['"]([^'"]+)['"]/gs,
            /\bicons?(?:After)?=['"]([^'"]+)['"]/g,
            /\bicons?(?:Name)?\s*:\s*['"]([^'"]+)['"]/g,
        ];
        // Any string literal inside an icon={...} expression is a candidate name.
        const expressions = /\b(?:icons?(?:After)?|name)=\{([^}]*)\}/g;

        const src = path.join(__dirname, '..', '..');
        const walk = (directory) => fs.readdirSync(directory, {withFileTypes: true})
            .flatMap(entry => {
                const full = path.join(directory, entry.name);
                if (entry.isDirectory()) return entry.name === 'node_modules' ? [] : walk(full);
                if (!/\.(js|jsx|ts|tsx)$/.test(entry.name)) return [];
                // This file names an unmapped icon on purpose, one test below.
                if (full === __filename) return [];
                return [[full, fs.readFileSync(full, 'utf8')]];
            });

        const unmapped = [];
        for (const [file, source] of walk(src)) {
            const names = patterns.flatMap(pattern => [...source.matchAll(pattern)].map(m => m[1]));
            for (const match of source.matchAll(expressions)) {
                /*
                 * Drop comparison operands first.  `name={sorted === 'descending' ? 'arrow
                 * down' : 'arrow up'}` picks an icon by testing a sort direction, and
                 * 'descending' is the thing being tested, not a name.
                 */
                const expression = match[1]
                    .replace(/[=!]==?\s*['"][^'"]*['"]/g, '')
                    .replace(/['"][^'"]*['"]\s*[=!]==?/g, '');
                names.push(...[...expression.matchAll(/['"]([^'"]+)['"]/g)].map(m => m[1]));
            }
            for (const name of names) {
                if (!resolveIconName(name)) {
                    unmapped.push(`${path.relative(src, file)}: ${name}`);
                }
            }
        }

        expect([...new Set(unmapped)]).toEqual([]);
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

    it("puts trailing content in the heading's row, not after its wrapper", () => {
        /*
         * The whole point of the slot.  `.wrolpi-header` is a block, so anything placed after
         * it starts a new line -- which is what happened to every help icon in the app when
         * these headings stopped being a bare `<h3>`.  A shared flex row holds them together.
         */
        const {container} = renderUI(
            <Header as='h3' after={<button type='button'>Help</button>}>Root CA Certificate</Header>);

        const row = container.querySelector('.wrolpi-header-row');
        expect(row).toContainElement(container.querySelector('h3'));
        expect(row).toContainElement(screen.getByRole('button', {name: 'Help'}));
    });

    it("keeps the control out of the heading's accessible name", () => {
        // Inside the <h3> the control becomes part of the name, so heading navigation
        // announces "Root CA Certificate Help".
        renderUI(<Header as='h3' after={<button type='button'>Help</button>}>Root CA Certificate</Header>);

        expect(screen.getByRole('heading')).toHaveAccessibleName('Root CA Certificate');
    });

    it('puts layout styles on the block, not on the heading inside it', () => {
        /*
         * `style` is used for spacing the header as a whole -- marginBottom on Status's
         * "Drive Bandwidth", marginTop on the extension page.  On the inner heading those set
         * a margin inside the wrapper and worked only through margin collapse, which stops as
         * soon as the wrapper gains padding or a border.
         */
        const {container} = renderUI(
            <Header as='h3' style={{marginBottom: '1em'}}>Drive Bandwidth</Header>);

        expect(container.querySelector('.wrolpi-header')).toHaveStyle({marginBottom: '1em'});
        expect(container.querySelector('h3').style.marginBottom).toBe('');
    });

    it('still colors the heading text from the color prop', () => {
        const {container} = renderUI(<Header as='h4' color='danger'>2 items to remove</Header>);

        expect(container.querySelector('h4')).toHaveStyle({color: 'var(--danger)'});
    });

    it('renders nothing extra when there is no trailing content', () => {
        const {container} = renderUI(<Header as='h3'>Root CA Certificate</Header>);

        expect(container.querySelector('.wrolpi-header-after')).toBeNull();
    });
});

describe('PathInput', () => {
    /*
     * These need no mocks at all -- no context, no API, no router.  That is the point of
     * putting the field in the library: the page that uses it needs a pile of provider and
     * fetch mocks, so its inputs were never covered, which is how a field shipped printing
     * its own prefix over its own value.
     */

    it('keeps the prefix out of the value', () => {
        // The bug this exists to prevent: the prefix must be its own element, never part of
        // the text the user is editing, so it cannot be typed over or submitted.
        renderUI(<PathInput prefix='/media/wrolpi/' label='Archive Directory'
                            value='archive/%(domain)s' onChange={jest.fn()}/>);

        const input = screen.getByLabelText(/Archive Directory/);
        expect(input).toHaveValue('archive/%(domain)s');
        expect(input.value).not.toContain('/media/wrolpi');
        // A sibling, not a child: an element inside the box could overlap it.
        expect(input.querySelector('*')).toBeNull();
        expect(screen.getByText('/media/wrolpi/')).not.toBe(input);
    });

    it('reports only what was typed, never the prefix', async () => {
        // Read the value inside the handler: React nulls `currentTarget` once the event has
        // been dispatched, so inspecting it afterwards from mock.calls throws.
        const seen = [];
        const onChange = jest.fn(event => seen.push(event.currentTarget.value));
        renderUI(<PathInput prefix='/media/wrolpi/' label='Map Directory' onChange={onChange}/>);

        await userEvent.type(screen.getByLabelText(/Map Directory/), 'map');

        expect(seen).toEqual(['m', 'ma', 'map']);
        seen.forEach(value => expect(value).not.toContain('/media/wrolpi'));
    });

    it('tells assistive technology what the path is relative to', () => {
        // Sighted users get that from the prefix; hiding it would leave everyone else
        // typing a relative path with no idea what it is relative to.
        renderUI(<PathInput prefix='/media/wrolpi/' label='Zims Directory' value='' onChange={jest.fn()}/>);

        expect(screen.getByLabelText(/Zims Directory/)).toHaveAccessibleDescription('/media/wrolpi/');
    });

    it('disables the input, not just the wrapper', async () => {
        const onChange = jest.fn();
        renderUI(<PathInput prefix='/media/wrolpi/' label='Videos Directory' disabled
                            value='videos' onChange={onChange}/>);

        const input = screen.getByLabelText(/Videos Directory/);
        expect(input).toBeDisabled();
        await userEvent.type(input, 'x');
        expect(onChange).not.toHaveBeenCalled();
    });

    it('marks an invalid path so the dashed danger treatment applies', () => {
        const {container} = renderUI(<PathInput prefix='/media/wrolpi/' label='Bad'
                                                error='Not a directory' value='' onChange={jest.fn()}/>);

        expect(container.querySelector('[data-error]')).toBeInTheDocument();
        expect(screen.getByText('Not a directory')).toBeInTheDocument();
    });

    it('reads out its help text as well as the prefix', () => {
        /*
         * Rendering the description on screen is not the same as announcing it.  Unless it is
         * referenced, a screen reader user hears the label and the prefix and never learns
         * what the field expects -- the help text is the part that explains the variables
         * these paths are allowed to contain.
         */
        renderUI(<PathInput
            prefix='/media/wrolpi/'
            label='Archive Directory'
            description='Accepts %(domain)s and %(tag)s.'
            value=''
            onChange={jest.fn()}
        />);

        expect(screen.getByLabelText(/Archive Directory/))
            .toHaveAccessibleDescription('/media/wrolpi/ Accepts %(domain)s and %(tag)s.');
    });

    it('announces the reason a path was rejected', () => {
        // The dashed border and red text carry the failure for sighted users; without the
        // error in the accessible description nothing carries it for anyone else.
        renderUI(<PathInput prefix='/media/wrolpi/' label='Zims Directory'
                            error='Not a directory' value='' onChange={jest.fn()}/>);

        const input = screen.getByLabelText(/Zims Directory/);
        expect(input).toHaveAccessibleDescription(/Not a directory/);
        expect(input).toBeInvalid();
    });

    it('is not marked invalid when there is nothing wrong with it', () => {
        renderUI(<PathInput prefix='/media/wrolpi/' label='Fine' value='' onChange={jest.fn()}/>);

        expect(screen.getByLabelText(/Fine/)).toBeValid();
    });

    it('forwards a ref to the input, for callers that focus it', () => {
        const ref = React.createRef();
        renderUI(<PathInput ref={ref} prefix='/media/wrolpi/' label='Focusable'
                            value='' onChange={jest.fn()}/>);

        expect(ref.current.tagName).toBe('INPUT');
    });
});

describe('no input reserves space for a section it cannot measure', () => {
    it('nothing passes leftSectionWidth="auto"', () => {
        /*
         * `leftSectionWidth` becomes `--input-padding-inline-start`, and
         * `padding-inline-start: auto` is not valid CSS -- it resolves to zero, so the
         * section prints straight over the value.  Five fields on the Settings page shipped
         * that way and were unreadable.  It fails silently, in CSS, at runtime only, which
         * is exactly the kind of thing worth a source check.
         */
        const offenders = [];
        const walk = (dir) => {
            for (const entry of fs.readdirSync(dir, {withFileTypes: true})) {
                const full = path.join(dir, entry.name);
                if (entry.isDirectory()) walk(full);
                // Specs are exempt: ui-layout.cy.js reproduces this exact mistake on
                // purpose, to prove its overlap check can still detect it.
                else if (/\.(js|jsx|tsx)$/.test(entry.name)
                    && !/\.test\.|\.cy\./.test(entry.name)) {
                    // Comments are stripped first: the component that replaced this
                    // pattern documents it by name, and prose about a mistake is not the
                    // mistake.
                    const source = fs.readFileSync(full, 'utf8')
                        .replace(/\/\*[\s\S]*?\*\//g, '')
                        .replace(/^\s*\/\/.*$/gm, '');
                    if (/leftSectionWidth\s*=\s*['"`]auto['"`]/.test(source)
                        || /rightSectionWidth\s*=\s*['"`]auto['"`]/.test(source)) {
                        offenders.push(path.relative(path.join(__dirname, '..', '..'), full));
                    }
                }
            }
        };
        walk(path.join(__dirname, '..', '..'));

        expect(offenders).toEqual([]);
    });
});

describe('the library stays mockable-free', () => {
    /*
     * The whole reason these 80-odd tests need no setup is that a library component takes
     * props and reaches for nothing else -- no module-level fetch, no API helper, no
     * ambient state it has to be lied to about.  Pages are the opposite: DomainEditPage
     * needs seven jest.mock calls before it will render at all, which is precisely why the
     * inputs on the Settings page had no test when they broke.
     *
     * That property is worth asserting rather than hoping for.  The day a library
     * component grows a fetch, the mock somebody has to add to keep this file passing
     * trips the first check, and the import trips the second.
     */

    const libraryFiles = () => fs.readdirSync(__dirname)
        .filter(name => /\.(ts|tsx)$/.test(name) && !/\.test\./.test(name))
        .map(name => [name, fs.readFileSync(path.join(__dirname, name), 'utf8')]);

    it('needs no module mocked to render any of it', () => {
        const source = fs.readFileSync(path.join(__dirname, 'ui.test.js'), 'utf8')
            .replace(/\/\*[\s\S]*?\*\//g, '')
            .replace(/^\s*\/\/.*$/gm, '');

        expect(source).not.toMatch(/jest\.mock\s*\(/);
    });

    it('asks the network for nothing', () => {
        const offenders = libraryFiles()
            .filter(([, source]) => /\bfetch\s*\(|\bapiCall\b|\baxios\b/
                .test(source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')))
            .map(([name]) => name);

        expect(offenders).toEqual([]);
    });

    it('reads ambient state only in the theme controls', () => {
        /*
         * ThemePicker and MediaFilterToggle are the deliberate exception -- a control whose
         * entire job is to show and change the current theme has to know it.  Their tests
         * pass a real ThemeContext.Provider holding plain values, which is supplying data,
         * not mocking a module.  Everything else takes props.
         */
        const offenders = libraryFiles()
            .filter(([name]) => name !== 'ThemePicker.tsx')
            .filter(([, source]) => /useContext\s*\(/.test(source))
            .map(([name]) => name);

        expect(offenders).toEqual([]);
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

    it('keeps its percent text readable on every bar color', () => {
        /*
         * Ported from Theme.test.js, which asserted Semantic's `inverted-progress-text`
         * class across all fourteen colors and both modes.  That class is gone; the
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

describe('Label as a tag', () => {
    it('is a plain chip unless asked to be a tag', () => {
        // The same component carries the count badges in the Tags table -- file, zim, channel
        // and domain counts -- and a pointed left edge on a number reads as an arrow.
        const {container} = renderUI(<Label color='blue'>1,432</Label>);

        expect(container.querySelector('.wrolpi-label')).toBeInTheDocument();
        expect(container.querySelector('.wrolpi-tag')).not.toBeInTheDocument();
    });

    it('takes the tag shape when asked', () => {
        const {container} = renderUI(<Label tag color='blue'>Water</Label>);

        expect(container.querySelector('.wrolpi-tag')).toBeInTheDocument();
    });

    it('leaves the text color to the stylesheet', () => {
        // Every label routes its text color through `--label-text` so that night and amber,
        // which replace the fill with their own, can replace the text color with it.  An
        // inline `color` could not be overridden by either.
        const {container} = renderUI(<Label tag color='blue'>Water</Label>);

        expect(container.querySelector('.wrolpi-label').style.color).toBe('');
    });
});

describe('the library names severity by role, never by hue', () => {
    /*
     * A source guard, because a hue here is invisible in review and invisible in most tests.
     * In night `--red` and `--danger` are nearly the same pixel, so a rule that reverts to
     * `var(--red)` looks right in every screenshot and every distinctness check -- and is
     * still wrong, because the whole point is that a theme gets to decide what danger looks
     * like.  This is how `.wrolpi-message-error` kept a hardcoded `var(--red)` frame through
     * the change that moved its accent and icon onto roles.
     *
     * Focus rings and active-tab accents deliberately stay `--blue`: those are the primary
     * accent, not a severity, and `--primary` is a separate token for exactly that reason.
     */
    const severity = /(danger|error|failed|invalid|warning|success|complete)/i;

    it('uses no severity hue in a rule whose name means severity', () => {
        const css = fs.readFileSync(path.join(__dirname, 'ui.css'), 'utf8');
        const hues = /var\(--(red|green|amber|yellow|orange)\)/;

        // Split into rules, keeping each selector with its body.
        const offenders = [];
        for (const match of css.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
            const [, selector, body] = match;
            if (severity.test(selector) && hues.test(body)) {
                offenders.push(`${selector.trim().split('\n').pop().trim()} -> ${body.match(hues)[0]}`);
            }
        }

        expect(offenders).toEqual([]);
    });
});

describe('nothing paints a label\'s text with an inline color', () => {
    /*
     * A source guard, because this defect appeared at three separate call sites and fixing the
     * first one did not fix the others.
     *
     * A label's text color has to travel through `--label-text`.  An inline `color` is a
     * declaration no stylesheet rule can outrank, so night -- which turns a label into an
     * outline over a near-black page -- keeps whatever was calculated for the fill it just
     * discarded.  A bright fill leaves black text on near-black: the tag reads as an empty
     * outline, and nothing fails.
     *
     * The three were the tag chip, the tag edit preview (the very preview of the color being
     * chosen), and the Flasher's chip badges.  The stylesheet comment explaining the night and
     * amber override already named the Flasher, and it was still missed.
     */

    const sourceFiles = (directory) => fs.readdirSync(directory, {withFileTypes: true})
        .flatMap(entry => {
            const full = path.join(directory, entry.name);
            if (entry.isDirectory()) {
                return entry.name === 'node_modules' ? [] : sourceFiles(full);
            }
            if (!/\.(js|tsx)$/.test(entry.name) || /\.test\.|\.cy\./.test(entry.name)) {
                return [];
            }
            return [[full, fs.readFileSync(full, 'utf8')]];
        });

    it('sets --label-text instead, everywhere', () => {
        const src = path.join(__dirname, '..', '..');
        const offenders = [];

        for (const [file, source] of sourceFiles(src)) {
            const stripped = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
            let from = 0;
            while (true) {
                const at = stripped.indexOf('wrolpi-label', from);
                if (at === -1) break;
                from = at + 1;

                // The style object belonging to this element, if it has one nearby.
                const styleAt = stripped.indexOf('style={{', at);
                if (styleAt === -1 || styleAt - at > 200) continue;
                const styleEnd = stripped.indexOf('}}', styleAt);
                if (styleEnd === -1) continue;
                const styleObject = stripped.slice(styleAt, styleEnd);

                // A bare `color:` -- not `--label-color`, and not `backgroundColor` and friends,
                // which are camelCase and so do not match a lowercase `color:`.
                if (/(?:^|[^-\w])color\s*:/.test(styleObject)) {
                    offenders.push(`${path.relative(src, file)}: ${styleObject.slice(0, 90)}`);
                }
            }
        }

        expect(offenders).toEqual([]);
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

    it('draws no borders between columns', () => {
        /*
         * A full grid is a lot of ink to repeat what the column headings already say, and
         * it cost the header its identity: with no surface of its own, a bordered header
         * cell looked like one more cell in the grid.
         *
         * The marker goes on the CELLS.  Asserting the table lacks it is free -- the table
         * never carries it either way -- which is what this test did at first.
         */
        const {container} = renderUI(<Table>
            <Table.Body>
                <Table.Row><Table.Cell>a</Table.Cell><Table.Cell>b</Table.Cell></Table.Row>
            </Table.Body>
        </Table>);

        expect(container.querySelector('[data-with-column-border]')).toBeNull();
        // The outline around the table is a different thing, and it does live on the table.
        expect(container.querySelector('table')).toHaveAttribute('data-with-table-border');
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
        // File cards carry the mimetype's color on their top edge so a grid of results is
        // scannable by kind.  Semantic did this with `<Card color='violet'>`; two migrated
        // files had dropped the accent because our Card had no equivalent.
        const {container} = renderUI(<Card title='Water Storage.pdf' color='red'/>);

        expect(container.firstChild).toHaveStyle({borderBottom: '3px solid var(--red)'});
    });

    it('has no accent when no color is given', () => {
        const {container} = renderUI(<Card title='Plain'/>);

        expect(container.firstChild.style.borderBottom).toBe('');
    });

    it('puts the meta line under the title and the actions last', () => {
        /*
         * Order is the half of the fix jsdom can judge.  An Archive card renders its domain
         * and date as `meta` and its Details/Open buttons as `actions`; before `actions`
         * existed the buttons were children and the meta was foot-anchored, so every archive
         * card read buttons-then-domain.  Which slot lands where is what this asserts; that
         * the foot anchoring actually resolves is in ui-layout.cy.js, since `margin-top:
         * auto` needs a layout engine.
         *
         * That division is why there is no `margin-top: auto` assertion here any more.  There
         * was one, reading the inline style, and it broke when the card's sizes moved into
         * ui.css so the interface scale could reach them -- jsdom applies no stylesheet.  It
         * was asserting where the declaration was written rather than what it did, and the
         * cypress test above measures the actual foot alignment either way.
         */
        renderUI(<Card title='Rainwater Harvesting'
                       meta='engineering775.com'
                       actions={<button type='button'>Details</button>}>
            <span>body</span>
        </Card>);

        const body = screen.getByText('Rainwater Harvesting').parentElement;
        expect([...body.children].map(child => child.textContent)).toEqual([
            'Rainwater Harvesting', 'engineering775.com', 'body', 'Details',
        ]);
        expect(body.querySelector('.wrolpi-card-actions')).not.toBeNull();
        expect(body.querySelector('.wrolpi-card-meta')).not.toBeNull();
    });

    it('renders no actions row when a card has no actions', () => {
        // Otherwise every card in a grid pays for an empty foot, and the spacing below the
        // meta line differs between a card with buttons and one without.
        const {container} = renderUI(<Card title='Plain' meta='docs/'/>);

        expect(container.querySelector('.wrolpi-card-actions')).toBeNull();
    });
});

describe('CardGroup', () => {
    it('renders every card it is given', () => {
        renderUI(<CardGroup>
            <Card title='One'/>
            <Card title='Two'/>
            <Card title='Three'/>
        </CardGroup>);

        expect(screen.getByText('One')).toBeInTheDocument();
        expect(screen.getByText('Two')).toBeInTheDocument();
        expect(screen.getByText('Three')).toBeInTheDocument();
    });

    it('lays cards out on a track no narrower than minWidth, in rem so it scales', () => {
        /*
         * The default suits file results; a group of wide cards raises it.  If the value were
         * dropped the grid would fall back to one column, which is how a card wall becomes a
         * list on a desktop.
         *
         * The px the caller names is converted to rem, which is the whole reason a phone shows
         * one card per row again: as px, the track ignored the interface scale, and a 430px
         * screen fitted two 200px cards where the pre-migration build fitted one 290px card.
         */
        const {container} = renderUI(<CardGroup minWidth={320}><Card title='One'/></CardGroup>);

        expect(container.querySelector('.wrolpi-card-group'))
            .toHaveStyle({gridTemplateColumns: 'repeat(auto-fill, minmax(20rem, 1fr))'});
    });
});

describe('Statistic', () => {
    it('shows the value and its label', () => {
        renderUI(<Statistic value='87.4 GiB' label='Free space'/>);

        expect(screen.getByText('87.4 GiB')).toBeInTheDocument();
        expect(screen.getByText('Free space')).toBeInTheDocument();
    });

    it('colors the value from a token, not a hex', () => {
        // Status turns load, temperature and IO wait red or orange.  A hex here would not
        // remap in night mode, putting a green or orange pixel on a red-only screen.
        const {container} = renderUI(<Statistic value='3.9' label='1 Min. Load' color='red'/>);

        expect(container.querySelector('.wrolpi-statistic-value')).toHaveStyle({color: 'var(--red)'});
    });

    it('leaves the value in body text when no color is given', () => {
        const {container} = renderUI(<Statistic value='0.4' label='1 Min. Load'/>);

        expect(container.querySelector('.wrolpi-statistic-value').style.color).toBe('');
    });

    it('renders a zero rather than nothing', () => {
        // `pending_downloads` is 0 on an idle WROLPi, and a falsy check would blank the cell.
        renderUI(<Statistic value={0} label='Downloading'/>);

        expect(screen.getByText('0')).toBeInTheDocument();
    });

    it('forwards the props its wrappers spread onto it', () => {
        // `LoadStatistic` and the four Status wrappers (`CPUTemperatureStatistic`,
        // `FanRPMStatistic`, `IOWaitStatistic`, `UptimeStatistic`) all end in `{...props}`.
        // Statistic destructured a fixed five and dropped the rest on the floor, so anything
        // a caller passed through a wrapper vanished with no error anywhere.
        renderUI(<Statistic value='42' label='Fan RPM' title='Reported by the fan connector'/>);

        expect(screen.getByTitle('Reported by the fan connector')).toBeInTheDocument();
    });
});

describe('StatisticGroup', () => {
    it('gives each statistic its own cell', () => {
        const {container} = renderUI(<StatisticGroup>
            <Statistic value='1,432' label='Videos'/>
            <Statistic value='896' label='Archives'/>
        </StatisticGroup>);

        expect(container.querySelectorAll('.wrolpi-statistic-cell')).toHaveLength(2);
    });

    it('leaves a cell empty when its statistic renders nothing', () => {
        // `FanRPMStatistic` returns null on a device with no fan connector, which is most of
        // them.  The group cannot know that in advance, so the cell is still emitted and
        // `.wrolpi-statistic-cell:empty` takes it back out -- which only works while the cell
        // has nothing of its own inline for that rule to have to outrank.
        const Nothing = () => null;
        const {container} = renderUI(<StatisticGroup>
            <Statistic value='1,432' label='Videos'/>
            <Nothing/>
        </StatisticGroup>);

        const cells = container.querySelectorAll('.wrolpi-statistic-cell');
        expect(cells[1].childNodes).toHaveLength(0);
        expect(cells[1].getAttribute('style')).toBeNull();
    });

    it('draws no chrome of its own, in markup or in style', () => {
        // The group is spacing only: the statistics sit on whatever surface they were dropped
        // onto and take its color.  An inline border or background here would override the
        // stylesheet and could not be themed, so nothing may set one.
        const {container} = renderUI(<StatisticGroup>
            <Statistic value='1,432' label='Videos'/>
            <Statistic value='896' label='Archives'/>
        </StatisticGroup>);

        const group = container.querySelector('.wrolpi-statistic-group');
        expect(group.style.border).toBe('');
        expect(group.style.background).toBe('');
        expect(group.style.backgroundColor).toBe('');
        for (const cell of container.querySelectorAll('.wrolpi-statistic-cell')) {
            expect(cell.getAttribute('style')).toBeNull();
        }
    });

    it('still passes a style from the caller through', () => {
        const {container} = renderUI(<StatisticGroup style={{maxWidth: 600}}>
            <Statistic value='1,432' label='Videos'/>
        </StatisticGroup>);

        expect(container.querySelector('.wrolpi-statistic-group')).toHaveStyle({maxWidth: '600px'});
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

describe('Checkbox', () => {
    it('reports and changes its state', async () => {
        // Uncontrolled, so the box actually has to become checked.  Held at `checked={false}`
        // it never can, and the test could only ever say "a handler fired".
        renderUI(<Checkbox label='Download comments' defaultChecked={false}/>);

        const box = screen.getByRole('checkbox', {name: 'Download comments'});
        expect(box).not.toBeChecked();
        await userEvent.click(box);

        expect(box).toBeChecked();
    });

    it('hands the caller the new state', async () => {
        /*
         * Read inside the handler, as every call site does: `currentTarget` is only set
         * while the event is being dispatched and is null by the time the mock is inspected.
         * The claim is that the handler sees the state the user just asked for -- fire it
         * with the old value and each call site writes the state back unchanged.
         */
        let checkedWhenCalled;
        const onChange = jest.fn(event => {
            checkedWhenCalled = event.currentTarget.checked;
        });
        renderUI(<Checkbox label='Download comments' checked={false} onChange={onChange}/>);

        await userEvent.click(screen.getByRole('checkbox', {name: 'Download comments'}));

        expect(onChange).toHaveBeenCalledTimes(1);
        expect(checkedWhenCalled).toBe(true);
    });

    it('points Mantine\'s own variables at tokens', () => {
        /*
         * The only reason this wrapper exists.  Mantine draws the box and the tick from
         * --checkbox-color and --checkbox-icon-color; left alone they are Mantine's blue and
         * a literal white, and a white tick is exactly the pixel night mode forbids.
         */
        const {container} = renderUI(<Checkbox label='Download comments'/>);

        const root = container.querySelector('.mantine-Checkbox-root');
        expect(root.style.getPropertyValue('--checkbox-color')).toBe('var(--blue)');
        expect(root.style.getPropertyValue('--checkbox-icon-color')).toBe('var(--btn-text)');
    });

    it('keeps those variables when the caller brings a style of its own', () => {
        // `style={style}` instead of `style={{...checkboxStyles, ...style}}` would drop the
        // tokens for any call site that sets so much as a margin, and only in that one place.
        const {container} = renderUI(<Checkbox label='Download comments' style={{marginTop: 4}}/>);

        const root = container.querySelector('.mantine-Checkbox-root');
        expect(root.style.marginTop).toBe('4px');
        expect(root.style.getPropertyValue('--checkbox-color')).toBe('var(--blue)');
    });
});

describe('Loader', () => {
    it('has an accessible name, because a spinner with no name is silence', () => {
        renderUI(<Loader/>);

        expect(screen.getByLabelText('Loading')).toBeInTheDocument();
    });

    it('says what is being waited on when the caller knows', () => {
        renderUI(<Loader label='Fetching channels'/>);

        expect(screen.getByLabelText('Fetching channels')).toBeInTheDocument();
    });

    it('takes its color from a token rather than a fixed value', () => {
        // A hex here would be one color in all four themes, and a blue one in night mode.
        const {container} = renderUI(<Loader/>);

        expect(container.querySelector('.mantine-Loader-root').style.getPropertyValue('--loader-color'))
            .toBe('var(--blue)');
    });
});

describe('Loading', () => {
    it('names the spinner after the caption, so the wait is announced', () => {
        renderUI(<Loading>Loading backups…</Loading>);

        expect(screen.getByLabelText('Loading backups…')).toBeInTheDocument();
    });

    it('falls back to a generic name when the caption is not text', () => {
        // aria-label takes a string; handing it a React element yields "[object Object]".
        renderUI(<Loading><strong>Loading backups…</strong></Loading>);

        expect(screen.getByLabelText('Loading')).toBeInTheDocument();
    });

    it('renders no caption when there is nothing to say', () => {
        const {container} = renderUI(<Loading/>);

        const loader = container.querySelector('.mantine-Loader-root');
        expect(loader).toBeInTheDocument();
        /*
         * An empty caption div would still take its line-height and push the spinner off
         * centre.  Counted against the loader's own parent rather than the container: the
         * provider is free to add wrappers, and a global count would fail on that instead.
         */
        expect(loader.parentElement.children).toHaveLength(1);
    });
});

describe('Placeholder', () => {
    const lineWidths = (container) =>
        [...container.querySelectorAll('.mantine-Skeleton-root')]
            .map(line => line.style.getPropertyValue('--skeleton-width'));

    it('stands in for three lines by default', () => {
        const {container} = renderUI(<Placeholder/>);

        expect(lineWidths(container)).toHaveLength(3);
    });

    it('honours the number of lines asked for', () => {
        const {container} = renderUI(<Placeholder lines={5}/>);

        expect(lineWidths(container)).toHaveLength(5);
    });

    it('ends ragged, so it reads as text rather than a block', () => {
        const {container} = renderUI(<Placeholder lines={4}/>);

        expect(lineWidths(container)).toEqual(['100%', '100%', '100%', '60%']);
    });

    it('leaves a single line short as well', () => {
        // lines={1} makes the first line the last one; an off-by-one here would render one
        // full-width bar, which is a block and not a line of text.
        const {container} = renderUI(<Placeholder lines={1}/>);

        expect(lineWidths(container)).toEqual(['60%']);
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

describe('modal sizes', () => {
    /*
     * The size table is the single thing that halved every modal in the migration.
     *
     * Semantic's names were measured on the pre-migration build: mini 360, tiny 540, small
     * 720, large 1080, fullscreen 95%.  They are mapped onto Mantine's much smaller scale, so
     * a modal that said `small` went from 720px to 440px and one that said nothing at all
     * went from 900px to 440px.  That is deliberate now -- the sizes were audited call site
     * by call site against this scale -- but it means the table IS the design, and a quiet
     * edit to it moves seventy modals at once.
     */
    const MANTINE_PX = {xs: 320, sm: 380, md: 440, lg: 620, xl: 780};

    it('resolves each name to the width the audit was done against', () => {
        // Read out of Mantine's own stylesheet rather than restated, so a version bump that
        // changes the scale fails here instead of silently resizing the app.
        const css = fs.readFileSync(
            path.join(__dirname, '../../../node_modules/@mantine/core/styles.css'), 'utf8');

        Object.entries(MANTINE_PX).forEach(([name, px]) => {
            const declared = css.match(
                new RegExp(`--modal-size-${name}:\\s*calc\\(([\\d.]+)rem`));
            expect({name, px: declared && Math.round(parseFloat(declared[1]) * 16)})
                .toEqual({name, px});
        });
    });

    it('maps every Semantic name onto that scale', () => {
        // The mapping the call sites are written against.  `fullscreen` is the one that did
        // not shrink, and the one several audited modals were moved TO.
        const source = fs.readFileSync(path.join(__dirname, 'Overlays.tsx'), 'utf8');
        const table = source.match(/const modalSizes[^=]*=\s*{([^}]*)}/)[1];
        const pairs = Object.fromEntries([...table.matchAll(/(\w+):\s*'([^']+)'/g)]
            .map(m => [m[1], m[2]]));

        expect(pairs).toEqual({
            mini: 'xs', tiny: 'sm', small: 'md', large: 'lg', fullscreen: '100%',
        });
    });

    /**
     * The size Mantine was actually handed for each open modal, in source order, read off the
     * inline style it writes on the modal root (`--modal-size: var(--modal-size-lg)`).
     *
     * Read rather than restated so a call site that names a size the table cannot translate
     * shows up as the raw string it passed instead of quietly resolving to the default.
     *
     * All roots, not the first: a modal is portalled to `document.body`, so two renders in
     * one test both land there and `querySelector` on `baseElement` returns whichever opened
     * first.  That is how the first version of this reported the default twice and looked like
     * the size prop had no effect.
     */
    const renderedModalSizes = (baseElement) =>
        [...baseElement.querySelectorAll('.mantine-Modal-root')]
            .map(root => (root.getAttribute('style') ?? '').match(/--modal-size:\s*([^;]+)/)?.[1]);

    it('gives Confirm the tiny width by default, and lets a call site widen it', () => {
        /*
         * Confirm hardcoded `size='tiny'` and its props interface accepted no size at all, so
         * all twelve confirmations in the app were 380px whatever they contained -- including
         * TaggedDeleteConfirmModal, which renders a two-column table of file paths.  No call
         * site could do anything about it without editing this library.
         *
         * The default stays `tiny`: eleven of the twelve are one sentence, and a confirmation
         * that is wider than its question reads as a bigger decision than it is.
         */
        const {baseElement} = renderUI(<>
            <Confirm open title='Delete?'/>
            <Confirm open size='large' title='Delete these?'/>
        </>);

        expect(renderedModalSizes(baseElement))
            .toEqual(['var(--modal-size-sm)', 'var(--modal-size-lg)']);
    });

    it('never lets a call site name a size the table does not know', () => {
        /*
         * Two different hazards, and neither announces itself.
         *
         * A misspelled SEMANTIC name is not in the table, so it passes through untranslated,
         * Mantine does not recognise it either, and the modal silently renders at the default
         * 440px.  A raw MANTINE name -- `sm`, `md` -- is recognised and honoured: it works,
         * so nothing ever complains, and the call site quietly sits outside the vocabulary
         * the widths were audited in and outside the table that can retune them.  Flasher and
         * Confirm were both doing the second.
         *
         * The tag is scanned with a paren counter rather than matched with `[^>]*?`, which is
         * what the first version of this did.  `onClose={() => ...}` contains a `>`, so that
         * pattern stopped at the arrow and skipped the rest of the tag: it saw 44 of the 56
         * modals that declare a size, and the twelve it missed included Confirm's `size='sm'`
         * in this very library -- the one offender it was written to catch.
         */
        const known = new Set(['mini', 'tiny', 'small', 'large', 'fullscreen']);

        /** The opening tag starting at `start`, honouring braces in prop expressions. */
        const openingTag = (source, start) => {
            let depth = 0;
            for (let i = start; i < source.length; i++) {
                const character = source[i];
                if (character === '{' || character === '(') depth += 1;
                else if (character === '}' || character === ')') depth -= 1;
                else if (character === '>' && depth === 0) return source.slice(start, i + 1);
            }
            return '';
        };

        const walk = (directory) => fs.readdirSync(directory, {withFileTypes: true})
            .flatMap(entry => {
                const full = path.join(directory, entry.name);
                if (entry.isDirectory()) return entry.name === 'node_modules' ? [] : walk(full);
                if (!/\.(js|jsx|tsx)$/.test(entry.name)) return [];
                if (/\.(test|cy)\./.test(entry.name)) return [];
                return [[full, fs.readFileSync(full, 'utf8')]];
            });

        const offenders = [];
        let scanned = 0;
        let confirms = 0;
        for (const [file, source] of walk(path.join(__dirname, '..', '..'))) {
            /*
             * `Confirm` as well as `Modal`, now that it takes a size: it forwards the name
             * straight to Modal, so it is the same vocabulary and the same hazard.
             *
             * `(?![.\w])` because `<Modal\b` also matches `<Modal.Header` -- harmless while
             * those never declare a size, but it inflated an earlier count of these tags to
             * 243 and made the number useless as a premise check.
             */
            for (const match of source.matchAll(/<(Modal|Confirm)(?![.\w])/g)) {
                const tag = openingTag(source, match.index);
                // Quote-agnostic; a computed `size={...}` is the caller's business.
                const declared = tag.match(/\bsize=["']([^"']+)["']/);
                if (!declared) continue;
                scanned += 1;
                if (match[1] === 'Confirm') confirms += 1;
                if (!known.has(declared[1])) {
                    offenders.push(`${path.basename(file)}: size='${declared[1]}'`);
                }
            }
        }

        // The premise.  A scanner that silently matched nothing would report no offenders
        // and read exactly like a clean codebase, which is how the first version passed.
        expect(scanned).toBeGreaterThan(50);
        // And the premise for the half of the pattern that is new: at least one confirmation
        // names a size, so widening the scan is doing something rather than matching nothing.
        expect(confirms).toBeGreaterThan(0);
        expect(offenders).toEqual([]);
    });
});
