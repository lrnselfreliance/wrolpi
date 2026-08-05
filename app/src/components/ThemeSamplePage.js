import React, {useContext, useState} from 'react';
import {ThemeContext} from '../contexts/contexts';
import {
    ActionInput,
    Button,
    Card,
    CardGroup,
    ColoredInput,
    Confirm,
    Header,
    Icon,
    IconButton,
    Label,
    Loader,
    Loading,
    IconStack,
    MediaFilterToggle,
    Message,
    MultiSelect,
    NumberInput,
    Modal,
    Pagination,
    Panel,
    PathInput,
    Placeholder,
    Progress,
    SearchBox,
    Select,
    Statistic,
    StatisticGroup,
    TabBar,
    tabClassName,
    Status,
    Table,
    TextInput,
    Textarea,
    Checkbox,
    ThemePicker,
    Toggle,
    Tooltip,
    clearToasts,
    toast,
} from './ui';
import {semanticColorNames} from '../themes/mantine';
import {contrastingColor} from './Common';
import {navBarStyle, navColorNames, useNavColors} from '../themes/navColors';
import {IconMenu2} from '@tabler/icons-react';

/*
 * A gallery of every component in the library, in the current theme.
 *
 * Reachable at /theme-sample and linked from Settings, so a user can see a theme
 * before committing to it.
 *
 * EVERY new component belongs here.  It is how we review the design and how we
 * catch a component that only looks wrong in one of the four themes — which has
 * already happened more than once.
 */

/*
 * A stand-in poster of exact intrinsic dimensions, so the poster caps can be seen against
 * the ratios that actually break them -- a real library has all five and the gallery has
 * no media of its own.
 */
const samplePoster = (width, height) => `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' width='${width}' height='${height}'>` +
    `<rect width='100%' height='100%' fill='%23808080'/></svg>`)}`;

const Section = ({label, children}) => <section style={{marginBottom: 34}}>
    <p style={{
        fontSize: '0.6875rem', fontWeight: 600, letterSpacing: '0.12em', textTransform: 'uppercase',
        color: 'var(--muted)', margin: '0 0 10px',
    }}>{label}</p>
    {children}
</section>;

const Row = ({children}) => <div style={{display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center'}}>
    {children}
</div>;

/*
 * One navigation bar, in one of the twelve colors a user can pick for it.
 *
 * The bar is the only surface in the app whose background the USER chooses, and every theme
 * resolves those twelve names to twelve of its own colors -- forty-eight backgrounds that
 * the same links and status icons have to stay legible on.  They did not: the bar drew every
 * one of them in `--btn-text`, which is near-black in three of the four themes, and night's
 * `--brown` is #451212.  That glyph was 1.33:1 against the bar behind it.
 *
 * These are the real `.wrolpi-navbar` chrome and the real `navBarStyle`, not a mock-up, so a
 * sample cannot show a bar the app does not draw.  The measured ratio is printed beside each
 * one because ten of the forty-eight still sit under 4.5:1 and no foreground will lift them
 * -- a monochrome theme resolves all twelve names onto one ramp, and a mid-tone of a hue
 * cannot carry text of that same hue.  Fixing those means changing the palette, which is a
 * decision to make while looking at them.
 */
const AA_CONTRAST = 4.5;

export const NavBarSample = ({color}) => {
    const colors = useNavColors(color);
    const short = colors.ratio !== null && colors.ratio < AA_CONTRAST;

    return <div data-nav-sample={color} style={{marginBottom: 8}}>
        <nav className='wrolpi-navbar' style={{...navBarStyle(colors), minHeight: '2.8em'}}>
            <span className='wrolpi-navbar-link'><i>WROLPi</i>&nbsp;<Icon name='lock'/></span>
            <span className='wrolpi-navbar-link'>Videos</span>
            <span className='wrolpi-navbar-link'>Map</span>
            <div className='wrolpi-navbar-right' style={{gap: '0.5em', paddingRight: '0.5em'}}>
                {/*
                  * All three shapes the real bar puts in this corner, because they take
                  * their color by three different routes and only one of them was ever
                  * right.  A bare Icon inherits.  An anchor does NOT -- `a {color:
                  * var(--blue)}` in tokens.css outranks the inherited value, which is what
                  * made the search icon blue on every bar in every theme.  And a Mantine
                  * ActionIcon paints its own themed color, which is what made the
                  * hamburger blue.  The first version of this sample used an IconButton for
                  * the search icon too, so it showed the second fault twice and hid the
                  * first entirely.
                  */}
                <Icon name='warning sign' size='large' label='Drive health warning'/>
                <Icon name='hdd' size='large' label='Drive temperature warning'/>
                {/* eslint-disable-next-line jsx-a11y/anchor-is-valid */}
                <a className='wrolpi-navbar-link' role='button' tabIndex={0} aria-label='Search'>
                    <Icon name='search' size='large'/>
                </a>
                <IconButton icon={IconMenu2} label='Menu' variant='subtle'/>
            </div>
        </nav>
        <div style={{
            fontSize: '0.6875rem', color: short ? 'var(--danger)' : 'var(--muted)',
            padding: '3px 2px 0', display: 'flex', gap: 8,
        }}>
            <strong style={{fontWeight: 600}}>{color}</strong>
            <span data-nav-sample-ratio={color}>
                {colors.ratio === null ? '—' : `${colors.ratio.toFixed(2)}:1`}
            </span>
            {short && <span>below 4.5:1 — the palette has no better option</span>}
        </div>
    </div>
};

// Numbers the stacked toasts so it is obvious which press produced which, and that a second
// press adds a toast rather than replacing the first.  Module scope, so it survives re-renders.
let toastCounter = 0;

export function ThemeSamplePage() {
    const {theme} = useContext(ThemeContext);
    const [confirmOpen, setConfirmOpen] = useState(false);
    const [wideConfirmOpen, setWideConfirmOpen] = useState(false);
    const [comments, setComments] = useState(true);
    const [hotspot, setHotspot] = useState(true);
    const [dismissed, setDismissed] = useState(false);
    const [modalOpen, setModalOpen] = useState(false);
    const [realColors, setRealColors] = useState(false);
    const [search, setSearch] = useState('');
    const [activeTab, setActiveTab] = useState('Videos');
    const [page, setPage] = useState(3);

    return <div style={{maxWidth: 1060, margin: '0 auto', padding: '20px 16px 60px', color: 'var(--text)'}}>
        <h1 style={{fontSize: '1.3125rem', fontWeight: 600, margin: '8px 0 4px'}}>Component gallery</h1>
        <p style={{color: 'var(--muted)', fontSize: '0.8125rem', marginTop: 0}}>
            Every component in the WROLPi interface library, rendered in the <strong>{theme}</strong> theme.
            Switch themes here or from the navigation bar.
        </p>

        <Section label='Theme picker'>
            <Panel>
                <ThemePicker/>
                <p style={{fontSize: '0.75rem', color: 'var(--muted)', marginBottom: 0, marginTop: 12}}>
                    The same picker the Settings page uses. The navigation bar has a compact
                    version; both read the same list of themes.
                </p>
            </Panel>
        </Section>

        <Section label='Navigation bars'>
            <Panel>
                <p style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: 0}}>
                    Every color the navigation bar can be set to (Settings &rarr; navbar
                    color), in the <strong>{theme}</strong> theme. The text and icons are not
                    a fixed color: each bar is measured, and drawn in whichever of this
                    theme's own colors reads best on it. The ratio under each bar is that
                    measurement — anything under 4.5:1 is called out, and means the palette
                    itself has no color that reads on that background.
                </p>
                {navColorNames.map(color => <NavBarSample key={color} color={color}/>)}
            </Panel>
        </Section>

        <Section label='Media filtering'>
            <Panel>
                <div style={{display: 'flex', gap: 18, flexWrap: 'wrap', alignItems: 'flex-start'}}>
                    <div>
                        {/*
                          A real <img>, so it goes through whatever filter the current theme
                          applies — this is the only way to see the filter working without
                          leaving the page.  The unfiltered copy beside it opts out with
                          `night-unfiltered`, so the two can be compared side by side.
                        */}
                        <img src='/icon.svg' alt='The WROLPi logo, filtered like any other media'
                             width={104} height={104}/>
                        <p style={{fontSize: '0.6875rem', color: 'var(--muted)', margin: '4px 0 0'}}>
                            Filtered
                        </p>
                    </div>
                    <div>
                        {/*
                          Kept behind a click: an unfiltered image is a bright patch, and
                          leaving one on screen in night mode would cost a user the dark
                          adaptation they came here to protect.  They can ask for it.
                        */}
                        {realColors
                            ? <img className='night-unfiltered' src='/icon.svg'
                                   alt='The WROLPi logo, unfiltered' width={104} height={104}/>
                            : <Button role='cancel' icon='eye' style={{width: 104, height: 104}}
                                      onClick={() => setRealColors(true)}>Show</Button>}
                        <p style={{fontSize: '0.6875rem', color: 'var(--muted)', margin: '4px 0 0'}}>
                            Real colors
                        </p>
                    </div>
                    <p style={{fontSize: '0.75rem', color: 'var(--muted)', margin: 0, maxWidth: 430}}>
                        Images, video, PDFs, embedded pages, and the map canvas cannot read theme
                        tokens, so a monochrome theme remaps them with an SVG color matrix instead.
                        Night filters to red unless you turn it off; amber tints to match only if
                        you ask. Light and dark offer no filter, so both images look the same here.
                        <br/><br/>
                        Use the toggle below to see the difference. An element can opt out
                        with <code>night-unfiltered</code> — that is what the right-hand copy
                        does, which is why it is behind a click: an unfiltered image is a
                        bright patch, and night mode should not spring one on you.
                    </p>
                </div>
                {/*
                  The same control the theme picker renders, and the same state: flipping
                  either one moves both.  It renders nothing at all in light and dark, which
                  is why it appears to be missing there.
                */}
                <div style={{marginTop: 14}}>
                    <MediaFilterToggle/>
                    <p style={{fontSize: '0.75rem', color: 'var(--muted)', margin: '8px 0 0'}}>
                        <code>MediaFilterToggle</code>, the control the theme picker ends with.
                        It is per theme — turning it off for night leaves amber's alone — and it
                        renders nothing for a theme that offers no filter, so light and dark
                        show only this caption.
                    </p>
                </div>
            </Panel>
        </Section>

        <Section label='Headers'>
            <Panel>
                <Header as='h1'>Page title (h1)</Header>
                <Header as='h2'>Section (h2)</Header>
                <Header as='h3' icon='folder' dividing>With an icon and a divider (h3)</Header>
                <Header as='h4' subheader='And a subheader below it'>Subsection (h4)</Header>
                <Header as='h5'>Smallest (h5)</Header>
                {/*
                  The `after` slot.  A help button beside the text rather than under it --
                  which is where every one of them sat until headings gained an `after`,
                  because a sibling placed after the heading's block wrapper wraps.
                */}
                <Header as='h3' after={<Icon name='question' size='small'/>}>
                    With a help icon beside it
                </Header>
                <p style={{fontSize: '0.75rem', color: 'var(--muted)', marginBottom: 0}}>
                    The level picks the size, so the type scale stays a scale: call sites
                    choose a heading level for the document outline, never a font size.
                </p>
            </Panel>
        </Section>

        <Section label='Statistics'>
            {/*
              * Seven, deliberately: enough to wrap on a narrow window, which is where the row
              * hairlines are worth looking at.  The group rules both axes from --border, so the
              * grid holds together however the tracks fall.
              */}
            <StatisticGroup>
                <Statistic value='1,432' label='Videos'/>
                <Statistic value='896' label='Archives'/>
                <Statistic value='12,904' label='Files'/>
                <Statistic value='87.4 GiB' label='Free space'/>
                <Statistic value='14' label='Zim files'/>
                <Statistic value='312' label='eBooks'/>
                <Statistic value={0} label='Downloading'/>
            </StatisticGroup>

            {/* Status colors a reading that carries meaning.  Check these in night and amber,
                where there is no hue to spend and the value has to read some other way. */}
            {/* The group above ends in a label, and a heading has no margin of its own, so
                without this the two run together. */}
            <Header as='h5' style={{marginTop: 24}}>Colored readings, as Status draws them</Header>
            <StatisticGroup>
                <Statistic value='0.4' label='1 Min. Load'/>
                <Statistic value='2.6' label='5 Min. Load' color='warning'/>
                <Statistic value='4.1' label='15 Min. Load' color='danger'/>
                <Statistic value='48' label='Temp C°'/>
            </StatisticGroup>
        </Section>

        <Section label='Buttons'>
            <Panel>
                <Row>
                    <Button role='primary' icon='download'>Download</Button>
                    <Button role='save' icon='save'>Save</Button>
                    <Button role='retry' icon='refresh'>Retry</Button>
                    <Button role='danger' icon='trash' onClick={() => setConfirmOpen(true)}>Delete</Button>
                    <Button role='cancel' icon='x'>Cancel</Button>
                    <Button role='primary' loading>Working</Button>
                    <Button role='primary' disabled>Disabled</Button>
                </Row>
                <div style={{marginTop: 12}}>
                    <Row>
                        <IconButton icon='settings' label='Settings'/>
                        <IconButton icon='search' label='Search'/>
                        <IconButton icon='trash' role='danger' label='Delete'
                                    onClick={() => setConfirmOpen(true)}/>
                        <Tooltip label='Tooltips replace Semantic popups'>
                            <Button role='cancel'>Hover me</Button>
                        </Tooltip>
                        <Button role='cancel' onClick={() => toast({
                            type: 'success', title: 'Saved', description: 'Channel settings written.',
                        })}>Show a toast</Button>
                    </Row>
                </div>
                <div style={{marginTop: 12}}>
                    <Row>
                        {['xs', 'sm', 'md', 'lg', 'xl'].map(size => <div key={size}
                            style={{display: 'flex', gap: '0.4em', alignItems: 'flex-start'}}>
                            <Button size={size}>{size}</Button>
                            <IconButton size={size} icon='external' label={`Open (${size})`}/>
                        </div>)}
                    </Row>
                </div>
                <div style={{marginTop: 12}}>
                    <Header as='h5'>A row of actions</Header>
                    {/* `.wrolpi-button-row` is how a page lists the actions on a thing -- the
                        archive page's View/Read/Update/Delete, the edit pages' action row. It
                        wraps, so the last button drops to a second line at this width instead of
                        overflowing, and the row gap keeps the two lines apart. */}
                    <div className='wrolpi-button-row' style={{maxWidth: 320}}>
                        <Button color='violet'>View</Button>
                        <Button color='blue'>Read</Button>
                        <Button role='save'>Update</Button>
                        <Button role='danger'>Delete</Button>
                        <Button color='yellow'>Generate Screenshot</Button>
                    </div>
                </div>
                <p style={{fontSize: '0.75rem', color: 'var(--muted)', marginBottom: 0}}>
                    In night mode Delete drops its fill for a dashed red outline; dashed means
                    destructive or failed, and nothing else uses it.
                </p>
                <p style={{fontSize: '0.75rem', color: 'var(--muted)', marginBottom: 0}}>
                    Buttons in a row are spaced by the row, never by margins of their own. Semantic's
                    Button brought its own margin and nothing replaced it, so pages that listed
                    buttons as bare siblings had them sharing edges — and the ones that answered with
                    <code>margin-top</code> got a button sitting lower than its neighbours instead,
                    because <code>vertical-align: middle</code> is measured on the margin box.
                </p>
                <p style={{fontSize: '0.75rem', color: 'var(--muted)', marginBottom: 0}}>
                    An icon button is exactly as tall as a labelled one at every size, so a
                    group of them lines up. Mantine's own scale for icon buttons is unrelated
                    to its scale for buttons — <code>sm</code> is 22px against a button's 36px
                    — and the two components start from different defaults.
                </p>
            </Panel>
        </Section>

        <Section label='Toasts'>
            <Panel>
                {/*
                  * `toast` has thirteen call sites and no test, and it has already failed once
                  * app-wide: App.js dropped Semantic's toast container while seven pages were
                  * still importing the old helper, and every notification silently vanished.
                  * A toast is also the one component you cannot see by loading a page -- it has
                  * to be provoked -- which is why it needs buttons here rather than a sample.
                  */}
                <Row>
                    <Button role='primary' onClick={() => toast({
                        type: 'info', title: 'Refresh started',
                        description: 'Indexing the media directory.',
                    })}>Info</Button>
                    <Button role='save' onClick={() => toast({
                        type: 'success', title: 'Saved',
                        description: 'Channel settings written to config/channels.yaml.',
                    })}>Success</Button>
                    <Button role='cancel' onClick={() => toast({
                        type: 'warning', title: 'Daily download limit reached',
                        description: 'Downloads will resume tomorrow at 00:00.',
                    })}>Warning</Button>
                    <Button role='danger' onClick={() => toast({
                        type: 'error', title: 'Download failed',
                        description: 'HTTP 403 from the remote server after 3 attempts.',
                    })}>Error</Button>
                </Row>

                <Row>
                    {/* Click this repeatedly: each press is a separate toast, and the
                        container holds five at once. */}
                    <Button role='cancel' onClick={() => toast({
                        type: 'info', title: `Stacked toast ${++toastCounter}`,
                        description: 'Press again before this one expires.',
                    })}>Stack one more</Button>
                    <Button role='cancel' onClick={() => {
                        // All five at once, to see the container at its limit.
                        for (let i = 1; i <= 5; i += 1) {
                            toast({
                                type: 'info', title: `Toast ${i} of 5`,
                                description: 'Filling the container to its limit.',
                            });
                        }
                    }}>Fill the stack</Button>
                    <Button role='cancel' onClick={() => toast({
                        type: 'error', title: 'This one stays',
                        description: 'time: 0 means it waits to be dismissed. Close it yourself.',
                        time: 0,
                    })}>Never expires</Button>
                    <Button role='cancel' onClick={() => toast({
                        type: 'warning',
                        description: 'No title, only a description — some call sites send just this.',
                    })}>No title</Button>
                    <Button role='cancel' onClick={() => toast({
                        type: 'error', title: 'A long one, to see how it wraps',
                        description: 'Failed to fetch https://example.com/a/very/long/path/that/'
                            + 'keeps/going/for/a/while.html: the remote server closed the '
                            + 'connection after sending part of the response body.',
                    })}>Long text</Button>
                    {/* Events.js sends three of these, each opening a URL.  Click the toast
                        body, or Tab to it and press Enter; the dismiss button does not follow. */}
                    <Button role='cancel' onClick={() => toast({
                        type: 'info', title: 'Screenshot Generated',
                        description: 'Click here to view it.',
                        time: 10000,
                        onClick: () => toast({type: 'success', title: 'Followed the toast'}),
                    })}>Clickable</Button>
                    <Button role='danger' onClick={() => clearToasts()}>Clear all</Button>
                </Row>

                <p style={{fontSize: '0.75rem', color: 'var(--muted)', marginBottom: 0}}>
                    Top right, five at a time, five seconds each unless the caller says
                    otherwise. Check each type in all four themes: night has no second hue to
                    spend, so info, success, warning and error cannot be told apart by color
                    there.
                </p>
            </Panel>
        </Section>

        <Section label='Semantic roles'>
            <Panel>
                {/*
                  The roles side by side, which is the only way to see the thing that
                  matters: in night and amber these are five brightnesses of one hue, and
                  they have to stay tellable apart with no hue to help.
                */}
                {/* 120px so all five usually sit on one row; they still wrap on a phone,
                    which is why the caption says "in order" and not "left to right". */}
                <div style={{
                    display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
                    gap: 12,
                }}>
                    {[
                        ['neutral', 'pending, disabled, unknown'],
                        ['info', 'in progress, informational'],
                        ['success', 'complete, healthy'],
                        ['warning', 'needs attention'],
                        ['danger', 'failed, destructive'],
                    ].map(([role, meaning]) => <div key={role}>
                        <div style={{
                            height: 34, background: `var(--${role})`, marginBottom: 6,
                        }}/>
                        <div style={{fontSize: '0.8125rem', fontWeight: 600, color: `var(--${role})`}}>
                            {role}
                        </div>
                        <div style={{fontSize: '0.6875rem', color: 'var(--muted)'}}>{meaning}</div>
                    </div>)}
                </div>
                <p style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: 14, marginBottom: 0}}>
                    Components ask for a <em>meaning</em> — <code>danger</code> — not a hue.
                    Light and dark spend a color on each. Night and amber have only one hue,
                    so a role is a step on a brightness ramp instead; that is why an error and
                    an info toast used to be the same pixel there. Severity climbs in the order
                    shown for those two themes, and both <code>warning</code> and{' '}
                    <code>danger</code> are brighter than ordinary text — with no hue to carry
                    "look at this", brighter is the only thing left.
                </p>
            </Panel>
        </Section>

        <Section label='Status'>
            <Panel>
                <div style={{display: 'flex', gap: 18, flexWrap: 'wrap'}}>
                    <Status kind='complete'>complete</Status>
                    <Status kind='active'>downloading</Status>
                    <Status kind='pending'>pending</Status>
                    <Status kind='failed'>failed</Status>
                </div>
                <p style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: 12, marginBottom: 0}}>
                    Four states drawn from four roles. Failure also carries weight, because
                    brightness is the first thing lost on a dim screen and it is all night has.
                </p>
            </Panel>
        </Section>

        <Section label='Progress'>
            <Panel>
                {/*
                  The label sits on BOTH halves of the bar, so every one of these is really a
                  contrast test: the text has to read over the fill and over the track, in all
                  four themes.  That is why light brightens the fill rather than using the raw
                  token, and why night and amber drop it to --muted instead of a hue.
                */}
                <div style={{maxWidth: 460}}>
                    <Progress percent={0}/>
                    <Progress percent={8}/>
                    <Progress percent={37}/>
                    <Progress percent={62}/>
                    <Progress percent={94}/>
                    <Progress percent={100}/>
                </div>

                <Header as='h5'>Its own label instead of the percentage</Header>
                <div style={{maxWidth: 460}}>
                    <Progress percent={41} label='2.1 GB / 5.3 GB'/>
                    <Progress percent={73} label='CPU Usage (16 cores)'/>
                    <Progress percent={12} label='nbd0 read 4.2 MBps'/>
                </div>

                <Header as='h5'>No label at all, and unknown size</Header>
                <div style={{maxWidth: 460}}>
                    <Progress percent={55} showPercent={false}/>
                    {/* Indeterminate: a band sliding inside the bar, for work whose size is
                        not known yet.  It must stay within the track -- it used to slide out
                        past both edges, because nothing clipped it. */}
                    <Progress indeterminate label='Uploading…'/>
                    <Progress indeterminate showPercent={false}/>
                </div>

                <Header as='h5'>Carrying a meaning</Header>
                <div style={{maxWidth: 460}}>
                    <Progress percent={64} color='info' label='Downloading'/>
                    <Progress percent={100} color='success' label='Complete'/>
                    <Progress percent={80} color='warning' label='Disk 80% full'/>
                    <Progress percent={100} color='danger' label='Error: HTTP 403'/>
                </div>
                <p style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: 14, marginBottom: 0}}>
                    A bar is 22px so its label has room; at 16px the text filled the bar edge to
                    edge. Check the mid-range ones — 37% and 62% are where the label crosses the
                    boundary between fill and track, which is the case that has to work.
                </p>
            </Panel>
        </Section>

        <Section label='Messages'>
            <div style={{display: 'flex', flexDirection: 'column', gap: 10}}>
                <Message kind='info' title='Refresh started'>
                    Indexing the media directory. This can take several minutes.
                </Message>
                <Message kind='success' title='Config saved'>
                    Channel settings were written to config/channels.yaml.
                </Message>
                <Message kind='warning' title='Daily download limit reached'>
                    Downloads will resume tomorrow at 00:00.
                </Message>
                <Message kind='error' title='Download failed'>
                    HTTP 403 from the remote server after 3 attempts. Retry, or check the URL.
                </Message>
                <Message kind='info' icon='puzzle piece' title='With an icon, and dismissible'
                         onDismiss={() => setDismissed(true)}>
                    {dismissed
                        ? 'Dismissed — it would be gone in the real interface.'
                        : 'A nudge the user can clear. Only offer dismiss when clearing it is harmless.'}
                </Message>
            </div>
        </Section>

        <Section label='Downloads table'>
            <Table>
                <Table.Header>
                    <Table.Row>
                        <Table.HeaderCell sorted='ascending' onSort={() => {}}>URL</Table.HeaderCell>
                        <Table.HeaderCell onSort={() => {}}>Downloader</Table.HeaderCell>
                        <Table.HeaderCell style={{width: 150}}>Progress</Table.HeaderCell>
                        <Table.HeaderCell>Status</Table.HeaderCell>
                        <Table.HeaderCell>Size</Table.HeaderCell>
                        <Table.HeaderCell>Actions</Table.HeaderCell>
                    </Table.Row>
                </Table.Header>
                <Table.Body>
                    <Table.Row>
                        <Table.Cell>youtube.com/watch?v=hT6Rkfahyg</Table.Cell>
                        <Table.Cell>video</Table.Cell>
                        <Table.Cell><Progress percent={100}/></Table.Cell>
                        <Table.Cell><Status kind='complete'>complete</Status></Table.Cell>
                        <Table.Cell numeric>312 MiB</Table.Cell>
                        <Table.Cell><Button role='cancel' size='xs'>Details</Button></Table.Cell>
                    </Table.Row>
                    <Table.Row>
                        <Table.Cell>youtube.com/watch?v=Zk91nq2rrE</Table.Cell>
                        <Table.Cell>video</Table.Cell>
                        <Table.Cell><Progress percent={62}/></Table.Cell>
                        <Table.Cell><Status kind='active'>downloading</Status></Table.Cell>
                        <Table.Cell numeric>198 MiB</Table.Cell>
                        <Table.Cell><Button role='cancel' size='xs'>Stop</Button></Table.Cell>
                    </Table.Row>
                    <Table.Row failed>
                        <Table.Cell>example.org/prepping/water-storage.html</Table.Cell>
                        <Table.Cell>archive</Table.Cell>
                        <Table.Cell><Progress percent={0} showPercent={false}/></Table.Cell>
                        <Table.Cell><Status kind='failed'>failed</Status></Table.Cell>
                        <Table.Cell numeric>&mdash;</Table.Cell>
                        <Table.Cell>
                            <Row>
                                <Button role='retry' size='xs' icon='refresh'>Retry</Button>
                                <Button role='danger' size='xs' icon='trash'
                                        onClick={() => setConfirmOpen(true)}>Delete</Button>
                            </Row>
                        </Table.Cell>
                    </Table.Row>
                    <Table.Row>
                        <Table.Cell>wikipedia_en_all_maxi_2026-06.zim</Table.Cell>
                        <Table.Cell>zim</Table.Cell>
                        <Table.Cell><Progress percent={0}/></Table.Cell>
                        <Table.Cell><Status kind='pending'>pending</Status></Table.Cell>
                        <Table.Cell numeric>104 GiB</Table.Cell>
                        <Table.Cell><Button role='cancel' size='xs'>Cancel</Button></Table.Cell>
                    </Table.Row>
                </Table.Body>
            </Table>
        </Section>

        <Section label='Form controls'>
            <Panel>
                <div style={{display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 12}}>
                    <TextInput label='URLs' defaultValue='https://www.youtube.com/watch?v=hT6Rkfahyg'
                               description='One URL per line.'/>
                    <Select label='Downloader' defaultValue='Videos'
                            data={['Videos', 'Archive', 'File', 'Scrape']}/>
                    <TextInput label='Destination' defaultValue='videos/'/>
                </div>
                <div style={{marginTop: 12, display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12}}>
                    {/*
                      MultiSelect with a value already set, because the pills it renders for
                      chosen options are its own surface and they were the part most likely to
                      come out neutral grey.  Open it to check the dropdown too.
                    */}
                    <MultiSelect
                        label='Tags'
                        description='Applied to everything this download creates.'
                        data={['Preserve', 'Homestead', 'Radio', 'Medical', 'Reference']}
                        defaultValue={['Preserve', 'Radio']}
                        clearable
                    />
                    <NumberInput label='Depth' description='Follow links this far.'
                                 defaultValue={2} min={1} max={4}/>
                </div>
                <div style={{marginTop: 12}}>
                    <Textarea label='Notes' placeholder='Notes about this download…' minRows={2}/>
                </div>
                <div style={{marginTop: 12}}>
                    <PathInput
                        prefix='/media/wrolpi/'
                        label='Videos Directory'
                        description="A fixed prefix beside the value, not layered over it."
                        defaultValue='videos/%(channel_name)s'
                    />
                </div>
                <div style={{marginTop: 12}}>
                    <ActionInput
                        label="This WROLPi's URL"
                        readOnly
                        value='https://wrolpi.local'
                        action={<Button role='cancel' icon='copy'>Copy</Button>}
                    />
                </div>
                <div style={{marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 10}}>
                    <ColoredInput label='ft' color='blue' defaultValue='33'/>
                    <ColoredInput label='Ω' color='red' defaultValue='50'/>
                    <ColoredInput label='gal' color='green' labelPosition='right' defaultValue='275'/>
                </div>
                <p style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: 8, marginBottom: 0}}>
                    ColoredInput welds a Label to one edge of a field — the calculators' unit
                    markers. In night and amber the Label is an outline rather than a fill, so
                    the marker reads without a block of color.
                </p>
                <div style={{marginTop: 14, display: 'flex', flexDirection: 'column', gap: 10}}>
                    <Checkbox label='Download comments' checked={comments}
                              onChange={e => setComments(e.currentTarget.checked)}/>
                    <Toggle label='Hotspot' description='Broadcast the WROLPi WiFi network.'
                            checked={hotspot} onChange={e => setHotspot(e.currentTarget.checked)}/>
                    <Toggle label='WROL Mode' description='Read-only: disables downloads.'/>
                    <Toggle label='Bluetooth' description='No adapter detected.' disabled/>
                </div>
            </Panel>
        </Section>

        <Section label='Search'>
            <Panel>
                <SearchBox
                    value={search}
                    onChange={setSearch}
                    onSubmit={value => toast({type: 'info', title: 'Searched', description: value})}
                    onResultSelect={result => setSearch(result.title)}
                    results={{
                        directories: {
                            name: 'Directories',
                            results: [{title: 'videos/'}, {title: 'archive/'}],
                        },
                        channels: {
                            name: 'Channels',
                            results: [
                                {title: 'videos/Wranglerstar', description: 'Wranglerstar'},
                                {title: 'videos/RoseRed Homestead', description: 'RoseRed Homestead'},
                            ],
                        },
                    }}
                    clearable
                    placeholder='Search directory names…'
                />
                <p style={{fontSize: '0.75rem', color: 'var(--muted)', marginBottom: 0, marginTop: 12}}>
                    Focus the field to see grouped suggestions. Arrow keys move, Enter takes the
                    highlighted one or submits what you typed, Escape closes the list without
                    clearing the text.
                </p>
            </Panel>
        </Section>

        <Section label='Pagination and tabs'>
            <Panel>
                <TabBar right={<Label color='blue'>1,432 videos</Label>}>
                    {['Videos', 'Channels', 'Playlists'].map(tab => <button
                        key={tab}
                        type='button'
                        className={tabClassName(tab === activeTab)}
                        onClick={() => setActiveTab(tab)}
                    >{tab}</button>)}
                </TabBar>
                <Pagination activePage={page} totalPages={12} onPageChange={setPage} showFirstAndLast/>
                <p style={{fontSize: '0.75rem', color: 'var(--muted)', marginBottom: 0, marginTop: 12}}>
                    Night and amber mark the current page with a heavier border rather than a
                    filled block, which would be a bright surface. The tab bar takes rendered
                    children, so routing stays with the caller.
                </p>
            </Panel>
        </Section>

        <Section label='Labels'>
            <Panel>
                <Row>
                    {semanticColorNames.map(color => <Label key={color} color={color}>{color}</Label>)}
                    <Label color='black'>black</Label>
                    <Label color='white'>white</Label>
                    <Label color='blue' icon='tag'>tagged</Label>
                </Row>
            </Panel>
        </Section>

        <Section label='Tags'>
            <Panel>
                {/*
                  * Tag colors are the user's, stored per tag, so these are raw hex values --
                  * the only place in the app that paints with something no theme chose.  That
                  * is exactly why they belong here: the gallery had label swatches in theme
                  * colors and no user-colored tag, so nobody saw that night was calculating
                  * the text color against a fill it had already thrown away.
                  *
                  * Deliberately spans the range: near-white and near-black fills, where the
                  * black-or-light text decision flips, plus enough tags to wrap a row.
                  */}
                <Row>
                    {[
                        ['Water', '#2185d0'], ['Food', '#21ba45'], ['Medical', '#db2828'],
                        ['Shelter', '#a5673f'], ['Power', '#fbbd08'], ['Comms', '#6435c9'],
                        ['Reference', '#f2f2f2'], ['Archived', '#1b1c1d'],
                        ['Seeds', '#b5cc18'], ['Tools', '#00b5ad'], ['Navigation', '#e03997'],
                    ].map(([name, color]) => <span
                        key={name}
                        className='wrolpi-label wrolpi-tag'
                        style={{'--label-color': color, '--label-text': contrastingColor(color)}}
                    >{name}</span>)}
                </Row>
                <p style={{marginTop: 14, fontSize: '0.8125rem', color: 'var(--muted)'}}>
                    Every tag must be readable in all four themes. In night and amber the
                    user's color is discarded, so all tags look alike — that is the same
                    trade the labels above make, and it is deliberate.
                </p>
            </Panel>
        </Section>

        <Section label='Icons'>
            <Panel>
                <Row>
                    {['film', 'archive', 'file text', 'map outline', 'book', 'settings', 'search',
                        'download', 'trash', 'warning sign'].map(name => <Icon key={name} name={name} size='large'/>)}
                </Row>
                <div style={{marginTop: 14}}>
                    <Row>
                        <Loader/>
                        <Icon name='circle notch' loading/>
                        <span style={{fontSize: '0.75rem', color: 'var(--muted)'}}>
                            Icons inherit currentColor, so they follow every theme.
                        </span>
                    </Row>
                </div>
                {/*
                  These are on a Panel, so each one says so.  The default is the page
                  background, which is right for the nav bar and wrong everywhere else.
                */}
                <div style={{marginTop: 18}}>
                    <Row>
                        <IconStack corner={<Icon name='question' size={12}/>} label='WiFi status unknown'
                                   style={{'--icon-stack-bg': 'var(--panel)'}}>
                            <Icon name='wifi' size='large'/>
                        </IconStack>
                        <IconStack corner={<Icon name='add' size={12}/>} label='New folder'
                                   style={{'--icon-stack-bg': 'var(--panel)'}}>
                            <Icon name='folder' size='large'/>
                        </IconStack>
                        <IconStack corner={<Icon name='x' size={12}/>} label='Download failed'
                                   style={{'--icon-stack-bg': 'var(--panel)'}}>
                            <Icon name='download' size='large'/>
                        </IconStack>
                        <span style={{fontSize: '0.75rem', color: 'var(--muted)', maxWidth: 400}}>
                            <code>IconStack</code> composes two glyphs into one symbol. The corner
                            glyph paints the surface behind itself so the two sets of strokes do not
                            cross, which means it has to be told what that surface is:{' '}
                            <code>--icon-stack-bg</code>, set to the panel here.
                        </span>
                    </Row>
                </div>
            </Panel>
        </Section>

        <Section label='Cards'>
            <CardGroup>
                {[
                    ['How To Sharpen An Axe The Right Way', 'Wranglerstar · 2024-11-03', 'blue', 'film'],
                    ['Pressure Canning Basics', 'RoseRed Homestead · 2025-02-17', 'blue', 'film'],
                    ['Water Storage Guide.pdf', 'docs/ · 2025-08-21', 'red', 'file pdf'],
                    ['Ham Radio General License.epub', 'ebooks/ · 2024-05-09', 'yellow', 'book'],
                ].map(([title, meta, color, icon]) => <Card
                    key={title}
                    title={title}
                    meta={meta}
                    color={color}
                    media={<div style={{
                        aspectRatio: '16/9', background: 'var(--head)', display: 'flex',
                        alignItems: 'center', justifyContent: 'center', color: 'var(--muted)',
                    }}><Icon name={icon} size={34}/></div>}
                />)}
            </CardGroup>

            <Header as='h4'>Posters</Header>
            <CardGroup>
                {[
                    ['16:9 video thumbnail', 1280, 720],
                    ['4:3 screenshot', 800, 600],
                    ['square thumbnail', 600, 600],
                    ['portrait book cover', 306, 396],
                    ['smaller than the card', 120, 90],
                ].map(([label, w, h]) => <Card
                    key={label}
                    title={label}
                    meta={`${w}×${h}`}
                    color='blue'
                    media={<div className='wrolpi-card-poster'>
                        <img alt='' src={samplePoster(w, h)}/>
                    </div>}
                />)}
            </CardGroup>
            <p style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: 10}}>
                A poster is capped on both axes — the card's width, and{' '}
                <code>--card-poster-max-height</code> — and keeps its own ratio whichever
                cap bites. Capping the width alone let a square thumbnail stand as tall as
                the card is wide. A poster smaller than the card is left at its own size
                rather than upscaled.
            </p>

            <Header as='h4'>Meta, body and actions</Header>
            <CardGroup>
                {[
                    ['Rainwater Harvesting And Filtration For A Small Off-Grid Homestead',
                        'engineering775.com · 2025-01-30', true],
                    ['Solar Basics', 'wiki.example.org · 2024-08-02', true],
                    ['Field Notes.pdf', 'docs/ · 2023-06-14', false],
                ].map(([title, meta, withActions]) => <Card
                    key={title}
                    title={<a href='#cards' className='no-link-underscore card-link'>{title}</a>}
                    meta={meta}
                    color='blue'
                    actions={withActions ? <div style={{display: 'flex', gap: '0.5em'}}>
                        <Button icon='file alternate'>Details</Button>
                        <IconButton icon='external' label='Open original URL'/>
                    </div> : undefined}
                />)}
            </CardGroup>
            <p style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: 10}}>
                Titles are links but take the body color, not the link color — a grid of
                results should read as titles. The meta line sits directly under the title;
                actions are pushed to the foot, so a row lines its buttons up however many
                lines each title took. A card with no actions simply ends.
            </p>
            <p style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: 10}}>
                The bottom edge carries the file type's color, so a grid of results is
                scannable by kind before any title is read. It comes from a token, so night
                and amber render the accent in their own single hue rather than four.
            </p>
        </Section>

        <Section label='Loading placeholders'>
            <Panel><Placeholder lines={4}/></Panel>
            <div style={{marginTop: 10}}>
                <Panel><Loading>Loading backups…</Loading></Panel>
            </div>
        </Section>

        <Section label='Modal'>
            <Panel>
                <Row>
                    <Button role='cancel' icon='eye' onClick={() => setModalOpen(true)}>Open a modal</Button>
                </Row>
                <p style={{fontSize: '0.75rem', color: 'var(--muted)', marginBottom: 0, marginTop: 10}}>
                    Semantic's compound shape is kept — Modal.Header, Modal.Content,
                    Modal.Actions — so the 34 call sites written against it migrate by import.
                </p>
                <Modal open={modalOpen} onClose={() => setModalOpen(false)} size='small'>
                    <Modal.Header>Restore Backup: channels.yaml</Modal.Header>
                    <Modal.Content>
                        <p style={{marginTop: 0}}>
                            Actions sit below the body behind a hairline, right-aligned so the
                            confirming action lands where the eye finishes reading.
                        </p>
                    </Modal.Content>
                    <Modal.Actions>
                        <Button role='cancel' onClick={() => setModalOpen(false)}>Close</Button>
                        <Button role='save' icon='check' onClick={() => setModalOpen(false)}>Apply</Button>
                    </Modal.Actions>
                </Modal>
            </Panel>
        </Section>

        <Section label='Danger zone'>
            <Panel danger>
                <h2 style={{color: 'var(--danger)', fontSize: '0.875rem', margin: '0 0 4px'}}>Danger zone</h2>
                <p style={{color: 'var(--muted)', fontSize: '0.8125rem', margin: '0 0 12px'}}>
                    These actions are destructive and cannot be undone.
                </p>
                <Row>
                    <Button role='danger' icon='trash' onClick={() => setConfirmOpen(true)}>
                        Delete channel
                    </Button>
                    <Button role='danger' icon='trash' onClick={() => setConfirmOpen(true)}>
                        Wipe download history
                    </Button>
                    <Button role='danger' icon='trash' onClick={() => setWideConfirmOpen(true)}>
                        Delete tagged files
                    </Button>
                </Row>
                <p style={{fontSize: '0.75rem', color: 'var(--muted)', marginBottom: 0, marginTop: 10}}>
                    A confirmation is 380px wide, which suits a question. One that has to show
                    what it is about takes a size, in the same vocabulary as Modal.
                </p>
            </Panel>
        </Section>

        <Confirm
            open={confirmOpen}
            destructive
            title='Delete channel?'
            confirmLabel='Delete'
            onConfirm={() => setConfirmOpen(false)}
            onCancel={() => setConfirmOpen(false)}
        >
            <p style={{marginTop: 0}}>
                The channel <strong>Wranglerstar</strong> and its download rules will be removed.
            </p>
            <p style={{color: 'var(--muted)', marginBottom: 0}}>
                videos/Wranglerstar/ (312 files) will not be deleted.
            </p>
        </Confirm>

        <Confirm
            open={wideConfirmOpen}
            size='large'
            destructive
            title={<><Icon name='warning sign'/> Tagged files will be deleted</>}
            confirmLabel='Delete'
            onConfirm={() => setWideConfirmOpen(false)}
            onCancel={() => setWideConfirmOpen(false)}
        >
            <p style={{marginTop: 0}}>The following tagged files will be deleted:</p>
            <Table>
                <Table.Header>
                    <Table.Row>
                        <Table.HeaderCell>File</Table.HeaderCell>
                        <Table.HeaderCell>Tags</Table.HeaderCell>
                    </Table.Row>
                </Table.Header>
                <Table.Body>
                    <Table.Row>
                        <Table.Cell>videos/Practical Engineering/Season 2024/Spillways.mp4</Table.Cell>
                        <Table.Cell>favorite, water</Table.Cell>
                    </Table.Row>
                    <Table.Row>
                        <Table.Cell>archives/en.wikipedia.org/Sluice_gate.html</Table.Cell>
                        <Table.Cell>water</Table.Cell>
                    </Table.Row>
                </Table.Body>
            </Table>
        </Confirm>
    </div>
}
