import {useOutdatedZims, useSearchZim, useWROLMode} from "../hooks/customHooks";
import React, {useState} from "react";
import {
    APIButton,
    encodeMediaPath,
    ErrorMessage,
    HandPointMessage,
    humanFileSize,
    IframeViewer,
    InfoMessage,
    normalizeEstimate,
    Paginator,
    TabLinks,
    TagIcon,
    Toggle,
    useTitle,
    WarningMessage
} from "./Common";
import {
    Accordion,
    Button,
    Divider,
    Group,
    Header,
    Label,
    Loading,
    Message,
    Modal,
    Panel,
    Placeholder,
    Select,
    Table,
    toast,
} from "./ui";
import {TextPlaceholder} from "./Placeholder";
import {TagsSelector} from "../Tags";
import {AddToPlaylistButton} from "./AddToPlaylist";
import {
    deleteOutdatedZims,
    fetchZims,
    fetchZimSubscriptions,
    refreshFiles,
    saveSettings,
    setZimAutoSearch,
    tagZimEntry,
    untagZimEntry,
    zimSubscribe,
    zimUnsubscribe
} from "../api";
import {useSearch} from "./Search";
import {TagsQuerySelector} from "./Files";
import {Link, Route, Routes} from "react-router";
import {SortableTable} from "./SortableTable";
import _ from "lodash";
import {ZIM_VIEWER_URI} from "./Vars";
import {HeadlineText} from "./Headline";

export const OutdatedZimsMessage = ({onClick}) => {
    const [open, setOpen] = React.useState(false);

    const {outdated, current} = useOutdatedZims();

    const onClose = () => setOpen(false);

    const handleDelete = async () => {
        try {
            const success = await deleteOutdatedZims();
            if (success) {
                toast({
                    type: 'info',
                    title: 'Zims deleted',
                    description: 'Outdated Zims have been deleted.',
                    time: 5000,
                });
            } else {
                toast({
                    type: 'error',
                    title: 'Failed to delete Zims',
                    description: 'Outdated Zims have NOT been deleted.  See server logs.',
                    time: 5000,
                });
            }
        } finally {
            onClose();
        }
    }

    const handleIgnore = async () => {
        const config = {ignore_outdated_zims: true};
        await saveSettings(config);
        if (onClick) {
            await onClick();
        }
    }

    let modalContent = <Placeholder lines={1}/>;
    if (outdated && outdated.length > 0) {
        modalContent = <>
            <Header as='h3'>To Delete</Header>
            {outdated.map(i => <pre key={i}>{i}</pre>)}

            <Header as='h3'>To Keep</Header>
            {current.map(i => <pre key={i}>{i}</pre>)}
        </>
    }

    return <Message kind='info' icon='question' title='Outdated Zim Files'>
        New Zim files have been downloaded. Outdated Zim files can be removed.
        <p></p>

        <Button role='danger' onClick={() => setOpen(true)}>Delete</Button>
        <Modal size='small' open={open}
               onClose={onClose}
               title='Delete'
        >
            {modalContent}
            <Modal.Actions>
                <APIButton
                    role='danger'
                    onClick={handleDelete}
                >Delete</APIButton>
                <Button role='cancel' onClick={onClose}>Close</Button>
            </Modal.Actions>
        </Modal>

        <Link to='/files?folders=zims'><Button role='cancel'>Delete Manually</Button></Link>
        <APIButton role='cancel'
                   onClick={handleIgnore}
        >Ignore Forever</APIButton>
    </Message>
}

const ZimSearchEntry = ({zimId, onTag, onUntag, entry}) => {
    const {path, title, headline, tag_names} = entry;
    const [open, setOpen] = React.useState(false);
    const url = `/api/zim/${zimId}/entry/${encodeMediaPath(path)}`;

    const handleClick = async (e) => {
        if (e) {
            e.preventDefault();
        }
        setOpen(true);
    }

    const localAddTag = (name) => {
        onTag(zimId, path, name);
    }

    const localUntag = (name) => {
        onUntag(zimId, path, name);
    }

    const tagIcon = tag_names && tag_names.length > 0 ? <TagIcon/> : null;

    return <div style={{marginLeft: '0.5em'}}>
        <Header
            as='h3'
            className='clickable'
            onClick={handleClick}
        >
            <u>
                <HeadlineText headline={title || path} openTag={'<i>'} closeTag={'</i>'}/>
            </u>
            {tagIcon}
        </Header>
        <HeadlineText headline={headline}/>
        <Modal size='large' open={open}
               onClose={() => setOpen(false)}>
            <div className='preview-fit'>
                <ZimViewer src={url} style={{
                    // Override IframeViewer's `fixed` so the iframe stays inside the Modal.
                    position: 'static',
                    height: '100%', width: '100%', border: 'none',
                    // Use white to avoid iframe displaying with dark-theme.
                    backgroundColor: '#ffffff',
                }}/>
            </div>
            <Modal.Actions>
                <Group justify='space-between' align='flex-start' wrap='wrap' style={{width: '100%'}}>
                    <TagsSelector selectedTagNames={tag_names} onAdd={localAddTag} onRemove={localUntag}/>
                    <Group gap='xs'>
                        <AddToPlaylistButton
                            zim={{zimId, entry: path, title: (title || path).replace(/<[^>]*>/g, '')}}
                            content={null} title='Add to Playlist'/>
                        <Button role='primary' component='a' href={url} target='_blank' rel='noopener noreferrer'>
                            Open
                        </Button>
                    </Group>
                </Group>
            </Modal.Actions>
        </Modal>
    </div>
}

const ZimAccordionItem = ({value, active, data, searchStr, activeTags}) => {
    const {id, estimate, metadata} = data;
    const {title, date} = metadata;
    const {zim, fetchSearch, pages, loading} = useSearchZim(searchStr, id, active, activeTags);

    const localAddTag = async (zimId, path, name) => {
        await tagZimEntry(zimId, path, name);
        await fetchSearch();
    }

    const localUntag = async (zimId, path, name) => {
        await untagZimEntry(zimId, path, name);
        await fetchSearch();
    }

    let body = <TextPlaceholder/>;
    if (zim && !loading) {
        const {search} = zim;
        if (search && search.length > 0) {
            body = search.map(i => <div
                key={i['path']}
                style={{borderBottom: '1px solid var(--border)', paddingBottom: '1em', marginBottom: '1em'}}
            >
                <ZimSearchEntry zimId={id} onTag={localAddTag} onUntag={localUntag} entry={i}/>
            </div>);
        } else {
            body = <p>No results</p>;
        }
    }

    const paginator = <div style={{marginTop: '2em'}}>
        <Paginator activePage={pages.activePage} totalPages={pages.totalPages} onPageChange={pages.setPage}/>
    </div>;

    const label = <Label color={estimate > 0 ? 'violet' : undefined}>{normalizeEstimate(estimate)}</Label>;

    return <Accordion.Item value={value}>
        <Accordion.Control>
            <Header as='h3' style={{marginBottom: 0}}>{title} {label}</Header>
        </Accordion.Control>
        <Accordion.Panel>
            <Header as='h4'>{date}</Header>
            {body}
            {paginator}
        </Accordion.Panel>
    </Accordion.Item>
}

const ZimsRefreshWarning = () => {
    return <div onClick={refreshFiles} style={{cursor: 'pointer'}}>
        <Message kind='warning' icon='hand point right' title='No Zims have been indexed.'>
            <a href='#'>Click here</a> to refresh all your files.
        </Message>
    </div>;
}

export const ZimSearchView = ({suggestions, loading}) => {
    const [activeValue, setActiveValue] = React.useState(null);
    const {searchStr, activeTags, setTags} = useSearch();
    const {zimsEstimates} = suggestions;

    let body;
    if (!_.isEmpty(zimsEstimates)) {
        body = <Accordion value={activeValue} onChange={setActiveValue}>
            {zimsEstimates.map(i => <ZimAccordionItem
                key={i['path']}
                value={String(i['id'])}
                active={activeValue === String(i['id'])}
                data={i}
                searchStr={searchStr}
                activeTags={activeTags}
            />)}
        </Accordion>;
    } else if (loading) {
        body = <Panel><Loading/></Panel>;
    } else if (_.isEmpty(zimsEstimates)) {
        body = <ZimsRefreshWarning/>;
    }

    return <>
        <TagsQuerySelector onChange={(i, j) => setTags(i)}/>
        {body}
    </>
}

const DownloadMessage = () => {
    return <InfoMessage>
        <p>More Zim files are available from the full Kiwix library&nbsp;
            <a href='https://download.kiwix.org/' rel='noopener noreferrer' target='_blank'>https://download.kiwix.org/</a>
        </p>
    </InfoMessage>
}

const ViewerMessage = () => {
    return <HandPointMessage>
        <p>You can view your Zim files using the Kiwix app, or at <a href={ZIM_VIEWER_URI}>{ZIM_VIEWER_URI}</a></p>
    </HandPointMessage>
}

export const ZimCatalogItemRow = ({item, subscriptions, iso_639_codes, fetchSubscriptions}) => {
    const {name, languages, size} = item;
    const subscription = name in subscriptions ? subscriptions[name] : null;
    const subscriptionLanguage = subscription ? subscription['language'] : 'en';

    const [language, setLanguage] = useState(subscriptionLanguage);
    const [pending, setPending] = useState(false);
    const languageChange = subscription ? language !== subscription['language'] : false;

    const wrolModeEnabled = useWROLMode();

    const handleButton = async () => {
        let success = false;
        try {
            setPending(true);
            if (subscription && !languageChange) {
                success = await zimUnsubscribe(subscription['id']);
            } else {
                success = await zimSubscribe(name, language);
            }
        } catch (e) {
            console.error(e);
        }
        setPending(false);
        if (!success) {
            toast({
                type: 'error',
                title: 'Error!',
                description: subscription ? 'Failed to unsubscribe' : 'Failed to subscribe',
            })
        }
        if (fetchSubscriptions) {
            await fetchSubscriptions();
        }
    }

    /*
     * The code itself when the API's table has no name for it.
     *
     * `iso_639_codes` covers 639-1 and 639-2; the Kiwix catalog also carries 639-3 codes and
     * locale variants -- `ami`, `ary`, `arz`, `be-tarask` -- and 89 of the codes in the
     * catalog on a live WROLPi are absent from its 672-entry table.  Each of those produced
     * `label: undefined`, and a `searchable` Mantine Select calls `option.label.toLowerCase()`
     * while building its dropdown on mount, before anyone opens it.  One unnamed language
     * anywhere in the catalog therefore took the whole /zim/manage page down.
     *
     * The code rather than a blank: a user choosing which language to subscribe to has to be
     * able to tell one unnamed language from another, and the code is all we know.
     *
     * `iso_639_codes` is also null on first render -- ManageZim initialises it that way and
     * fills it from the API -- so it is read defensively too.
     */
    const languageOptions = languages.map(i => {
        return {value: i, label: (iso_639_codes && iso_639_codes[i]) || i}
    });
    const languageDropdown = <Select
        searchable
        placeholder='Language'
        data={languageOptions}
        value={language}
        disabled={wrolModeEnabled}
        onChange={(value) => setLanguage(value)}
    />;

    const isDestructive = subscription && !languageChange;
    const subscribeButton = <APIButton
        role={isDestructive ? 'danger' : 'primary'}
        confirmContent={isDestructive ? 'Are you sure you want to unsubscribe from this Zim?' : undefined}
        confirmButton={isDestructive ? 'Unsubscribe' : undefined}
        disabled={pending}
        onClick={handleButton}
        obeyWROLMode={true}
    >
        {isDestructive ? 'Unsubscribe' : 'Subscribe'}
    </APIButton>

    return <Table.Row key={name}>
        <Table.Cell>{name}</Table.Cell>
        <Table.Cell>{languageDropdown}</Table.Cell>
        <Table.Cell>{subscribeButton}</Table.Cell>
        <Table.Cell>{humanFileSize(size)}</Table.Cell>
    </Table.Row>
}

class ManageZim extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            catalog: null,
            iso_639_codes: null,
            subscriptions: null,
            zims: null,
        }
    }

    async componentDidMount() {
        await this.fetchZims();
        await this.fetchSubscriptions();
    }

    async fetchZims() {
        try {
            const {zims} = await fetchZims();
            this.setState({zims});
        } catch (e) {
            console.error(e);
            this.setState({zims: undefined}); // Display error.
        }
    }

    async fetchSubscriptions() {
        try {
            const {subscriptions, catalog, iso_639_codes} = await fetchZimSubscriptions();
            this.setState({subscriptions, catalog, iso_639_codes});
        } catch (e) {
            console.error(e);
            this.setState({subscriptions: undefined, catalog: undefined}); // Display error.
        }
    }

    zimFileTableRow = (zim, sortData, localFetchZims) => {
        const {id, path, size, auto_search} = zim;

        const toggleZimAutoSearch = async () => {
            try {
                await setZimAutoSearch(id, !auto_search);
            } catch (e) {
                throw e;
            } finally {
                await localFetchZims();
            }
        }
        const toggle = <Toggle
            checked={auto_search}
            onChange={toggleZimAutoSearch}
            popupContent='Enable/Disable searching this Zim file in the Global Search.'
        />

        return <Table.Row key={path}>
            <Table.Cell>{path}</Table.Cell>
            <Table.Cell>{humanFileSize(size)}</Table.Cell>
            <Table.Cell>{toggle}</Table.Cell>
        </Table.Row>
    }

    render() {
        const {zims, catalog, iso_639_codes, subscriptions} = this.state;

        const zimFilesHeaders = [
            {key: 'path', text: 'Path', sortBy: 'path', width: 14},
            {key: 'size', text: 'Size', sortBy: 'size', width: 2},
            {key: 'search', text: 'Search', sortBy: 'auto_search', width: 2},
        ];
        let zimFilesBody = <Placeholder lines={2}/>;
        if (zims && zims.length >= 1) {
            zimFilesBody = <SortableTable
                data={zims}
                rowFunc={(i, sortData) => this.zimFileTableRow(i, sortData, this.fetchZims.bind(this))}
                rowKey='path'
                tableHeaders={zimFilesHeaders}
            />;
        } else if (zims && zims.length === 0) {
            zimFilesBody = <WarningMessage>
                You have not subscribed to any Kiwix projects, or your files have not been refreshed.
            </WarningMessage>;
        } else if (zims === undefined) {
            zimFilesBody = <ErrorMessage>Could not fetch Zim files</ErrorMessage>;
        }

        const kiwixCatalogHeaders = [
            {
                key: 'name', text: 'Name', 'sortBy': [i => {
                    return i['name'].toLowerCase()
                }], width: 8
            },
            {key: 'language', text: 'Language', 'sortBy': null, width: 4},
            {key: 'subscription', text: 'Subscription', 'sortBy': null, width: 2},
            {key: 'size', text: 'Maximum Size', sortBy: 'size', width: 2},
        ];
        let kiwixCatalog = <Placeholder lines={2}/>;
        if (catalog && catalog.length > 0) {
            kiwixCatalog = <SortableTable
                defaultSortColumn='name'
                data={catalog}
                rowFunc={i => <ZimCatalogItemRow
                    iso_639_codes={iso_639_codes}
                    subscriptions={subscriptions}
                    item={i}
                    fetchSubscriptions={async () => await this.fetchSubscriptions()}
                />}
                rowKey='name'
                tableHeaders={kiwixCatalogHeaders}
            />
        } else if (catalog === undefined) {
            kiwixCatalog = <ErrorMessage>Could not fetch catalog</ErrorMessage>;
        }

        /*
         * A fragment, not a `PageContainer`.  `ZimRoute` already provides the page chrome -- a
         * `wrolpi-stack` wrapper with its own top margin -- so a second one put this page a
         * further 1em down and 1em in from the tab bar than the viewer beside it.
         */
        return <>
            <Header as='h2'>Zim Files</Header>
            {zimFilesBody}

            <Header as='h2'>Kiwix Catalog</Header>
            {kiwixCatalog}

            <Divider/>

            <DownloadMessage/>
            <ViewerMessage/>
        </>
    }
}

function ZimViewer({src = ZIM_VIEWER_URI, style = null}) {
    const fallback = <Panel>
        <Header as='h3'>Failed to fetch Zim service.</Header>
        <p>You may need to give permission to access the page: <a href={src}>{src}</a></p>

        <p>If the above does not work, try starting the service:</p>
        <pre>sudo systemctl start wrolpi-kiwix</pre>

        <p>Check the logs</p>
        <pre>journalctl -u wrolpi-kiwix</pre>
    </Panel>;

    return <IframeViewer title='zim' src={src} fallback={fallback} style={style}/>
}

export function ZimRoute() {
    useTitle('Zim');

    const links = [
        {text: 'Viewer', to: '/zim', key: 'zim', end: true},
        {text: 'Manage', to: '/zim/manage', key: 'manage'},
    ]

    // `wrolpi-stack`: this route wraps its own content rather than using PageContainer, so it is
    // what spaces the tab bar from the page below it.
    return <div className='wrolpi-stack' style={{marginTop: '2em'}}>
        <TabLinks links={links}/>
        <Routes>
            <Route path='/' exact element={<ZimViewer/>}/>
            <Route path='manage' exact element={<ManageZim/>}/>
        </Routes>
    </div>
}
