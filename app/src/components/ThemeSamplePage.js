import React, {useContext, useState} from 'react';
import {ThemeContext} from '../contexts/contexts';
import {
    ActionInput,
    Button,
    Card,
    CardGroup,
    Confirm,
    Header,
    Icon,
    IconButton,
    Label,
    Loader,
    Loading,
    Message,
    Modal,
    Panel,
    Placeholder,
    Progress,
    Select,
    Statistic,
    StatisticGroup,
    Status,
    Table,
    TextInput,
    Textarea,
    Checkbox,
    ThemePicker,
    Toggle,
    Tooltip,
    toast,
} from './ui';
import {semanticColorNames} from '../themes/mantine';

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

const Section = ({label, children}) => <section style={{marginBottom: 34}}>
    <p style={{
        fontSize: 11, fontWeight: 600, letterSpacing: '0.12em', textTransform: 'uppercase',
        color: 'var(--muted)', margin: '0 0 10px',
    }}>{label}</p>
    {children}
</section>;

const Row = ({children}) => <div style={{display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center'}}>
    {children}
</div>;

export function ThemeSamplePage() {
    const {theme} = useContext(ThemeContext);
    const [confirmOpen, setConfirmOpen] = useState(false);
    const [comments, setComments] = useState(true);
    const [hotspot, setHotspot] = useState(true);
    const [dismissed, setDismissed] = useState(false);
    const [modalOpen, setModalOpen] = useState(false);
    const [realColors, setRealColors] = useState(false);

    return <div style={{maxWidth: 1060, margin: '0 auto', padding: '20px 16px 60px', color: 'var(--text)'}}>
        <h1 style={{fontSize: 21, fontWeight: 600, margin: '8px 0 4px'}}>Component gallery</h1>
        <p style={{color: 'var(--muted)', fontSize: 13, marginTop: 0}}>
            Every component in the WROLPi interface library, rendered in the <strong>{theme}</strong> theme.
            Switch themes here or from the navigation bar.
        </p>

        <Section label='Theme picker'>
            <Panel>
                <ThemePicker/>
                <p style={{fontSize: 12, color: 'var(--muted)', marginBottom: 0, marginTop: 12}}>
                    The same picker the Settings page uses. The navigation bar has a compact
                    version; both read the same list of themes.
                </p>
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
                        <p style={{fontSize: 11, color: 'var(--muted)', margin: '4px 0 0'}}>
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
                        <p style={{fontSize: 11, color: 'var(--muted)', margin: '4px 0 0'}}>
                            Real colors
                        </p>
                    </div>
                    <p style={{fontSize: 12, color: 'var(--muted)', margin: 0, maxWidth: 430}}>
                        Images, video, PDFs, embedded pages, and the map canvas cannot read theme
                        tokens, so a monochrome theme remaps them with an SVG color matrix instead.
                        Night filters to red unless you turn it off; amber tints to match only if
                        you ask. Light and dark offer no filter, so both images look the same here.
                        <br/><br/>
                        Use the toggle in the theme picker above to see the difference. An
                        element can opt out with <code>night-unfiltered</code> — that is what
                        the right-hand copy does, which is why it is behind a click: an
                        unfiltered image is a bright patch, and night mode should not spring
                        one on you.
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
                <p style={{fontSize: 12, color: 'var(--muted)', marginBottom: 0}}>
                    The level picks the size, so the type scale stays a scale: call sites
                    choose a heading level for the document outline, never a font size.
                </p>
            </Panel>
        </Section>

        <Section label='Statistics'>
            <StatisticGroup>
                <Statistic value='1,432' label='Videos'/>
                <Statistic value='896' label='Archives'/>
                <Statistic value='12,904' label='Files'/>
                <Statistic value='87.4 GiB' label='Free space'/>
                <Statistic value='14' label='Zim files'/>
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
                <p style={{fontSize: 12, color: 'var(--muted)', marginBottom: 0}}>
                    In night mode Delete drops its fill for a dashed red outline; dashed means
                    destructive or failed, and nothing else uses it.
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
                        <Table.HeaderCell>URL</Table.HeaderCell>
                        <Table.HeaderCell>Downloader</Table.HeaderCell>
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
                <div style={{marginTop: 12}}>
                    <Textarea label='Notes' placeholder='Notes about this download…' minRows={2}/>
                </div>
                <div style={{marginTop: 12}}>
                    <ActionInput
                        label="This WROLPi's URL"
                        readOnly
                        value='https://wrolpi.local'
                        action={<Button role='cancel' icon='copy'>Copy</Button>}
                    />
                </div>
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
                        <span style={{fontSize: 12, color: 'var(--muted)'}}>
                            Icons inherit currentColor, so they follow every theme.
                        </span>
                    </Row>
                </div>
            </Panel>
        </Section>

        <Section label='Cards'>
            <CardGroup>
                {[
                    ['How To Sharpen An Axe The Right Way', 'Wranglerstar · 2024-11-03'],
                    ['Pressure Canning Basics', 'RoseRed Homestead · 2025-02-17'],
                    ['Solar Panel Wiring: Series vs Parallel', 'DIY Solar Power · 2025-08-21'],
                    ['Ham Radio General License, Part 1', 'Ham Radio Crash Course · 2024-05-09'],
                ].map(([title, meta]) => <Card
                    key={title}
                    title={title}
                    meta={meta}
                    media={<div style={{
                        aspectRatio: '16/9', background: 'var(--head)', display: 'flex',
                        alignItems: 'center', justifyContent: 'center', color: 'var(--muted)',
                    }}><Icon name='film' size={34}/></div>}
                />)}
            </CardGroup>
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
                <p style={{fontSize: 12, color: 'var(--muted)', marginBottom: 0, marginTop: 10}}>
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
                <h2 style={{color: 'var(--red)', fontSize: 14, margin: '0 0 4px'}}>Danger zone</h2>
                <p style={{color: 'var(--muted)', fontSize: 13, margin: '0 0 12px'}}>
                    These actions are destructive and cannot be undone.
                </p>
                <Row>
                    <Button role='danger' icon='trash' onClick={() => setConfirmOpen(true)}>
                        Delete channel
                    </Button>
                    <Button role='danger' icon='trash' onClick={() => setConfirmOpen(true)}>
                        Wipe download history
                    </Button>
                </Row>
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
    </div>
}
