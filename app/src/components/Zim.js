import {useOutdatedZims, useSearchZim, useWROLMode} from "../hooks/customHooks";
import {
    Accordion,
    Button,
    Divider,
    Header,
    Icon,
    Loader,
    Modal,
    ModalActions,
    ModalContent,
    ModalHeader,
    Placeholder,
    Segment
} from "./Theme";
import {HeadlineText} from "./Headline";
import {TextPlaceholder} from "./Placeholder";
import {
    AccordionContent,
    AccordionTitle,
    Button as SButton,
    Dropdown,
    Icon as SIcon,
    Label,
    Message,
    PlaceholderHeader,
    PlaceholderLine,
    TableCell,
    TableRow
} from "semantic-ui-react";
import React, {useContext, useState} from "react";
import {
    APIButton,
    encodeMediaPath,
    ErrorMessage,
    HandPointMessage,
    humanFileSize,
    IframeViewer,
    InfoMessage,
    normalizeEstimate,
    PageContainer,
    Paginator,
    TabLinks,
    TagIcon,
    Toggle,
    useTitle,
    WarningMessage
} from "./Common";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {TagsSelector} from "../Tags";
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
import {ThemeContext} from "../contexts/contexts";
import {Link, Route, Routes} from "react-router-dom";
import {SortableTable} from "./SortableTable";
import {toast} from "react-semantic-toasts-2";
import _ from "lodash";
import {ZIM_VIEWER_URI} from "./Vars";

export const OutdatedZimsMessage = ({onClick}) => {
    const [open, setOpen] = React.useState(false);

    const {outdated, current} = useOutdatedZims();

    const onOpen = () => setOpen(true);
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

    let modalContent = <Placeholder>
        <PlaceholderLine/>
    </Placeholder>;
    if (outdated && outdated.length > 0) {
        modalContent = <>
            <Header as='h3'>To Delete</Header>
            {outdated.map(i => <pre key={i}>{i}</pre>)}

            <Header as='h3'>To Keep</Header>
            {current.map(i => <pre key={i}>{i}</pre>)}
        </>
    }

    return <Message icon info>
        <SIcon name='question'/>
        <Message.Content>
            <Message.Header>Outdated Zim Files</Message.Header>
            New Zim files have been downloaded. Outdated Zim files can be removed.
            <p></p>

            <SButton primary onClick={() => setOpen(true)}>Delete</SButton>
            <Modal closeIcon
                   open={open}
                   onClose={onClose}
                   onOpen={onOpen}
            >
                <ModalHeader>Delete</ModalHeader>
                <ModalContent>
                    {modalContent}
                </ModalContent>
                <ModalActions>
                    <APIButton
                        color='red'
                        floated='left'
                        onClick={handleDelete}
                    >Delete</APIButton>
                    <Button onClick={onClose}>Close</Button>
                </ModalActions>
            </Modal>

            <Link to='/files?folders=zims'><SButton>Delete Manually</SButton></Link>
            <APIButton secondary
                       onClick={handleIgnore}
            >Ignore Forever</APIButton>
        </Message.Content>
    </Message>
}

export const KiwixRestartMessage = () => {
    return <WarningMessage>
        <Message.Header>Kiwix must be restarted</Message.Header>
        <p>New Zim files have been downloaded; you must restart your containers.</p>

        <p>Run the following to restart your containers:</p>
        <pre>  docker-compose restart</pre>
    </WarningMessage>
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
        <Modal closeIcon
               open={open}
               onClose={() => setOpen(false)}>
            <ModalContent>
                <div className='full-height'>
                    <ZimViewer src={url} style={{
                        height: '100%', width: '100%', border: 'none', position: 'absolute', top: 0,
                        // Use white to avoid iframe displaying with dark-theme.
                        backgroundColor: '#ffffff',
                    }}/>
                </div>
            </ModalContent>
            <ModalActions>
                <Grid>
                    <Grid.Column mobile={10} tablet={14}>
                        <TagsSelector selectedTagNames={tag_names} onAdd={localAddTag} onRemove={localUntag}/>
                    </Grid.Column>
                    <Grid.Column width={2}>
                        <Button color='blue' as='a' href={url} target='_blank'>Open</Button>
                    </Grid.Column>
                </Grid>
            </ModalActions>
        </Modal>
    </div>
}

const ZimAccordion = ({data, index, activeIndex, onClick, searchStr, activeTags}) => {
    const {id, estimate, metadata} = data;
    const {title, date} = metadata;
    const {zim, fetchSearch, pages, loading} = useSearchZim(searchStr, id, index === activeIndex, activeTags);
    const {t} = useContext(ThemeContext);

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
            body = search.map(i => <Segment vertical key={i['path']}>
                <ZimSearchEntry zimId={id} onTag={localAddTag} onUntag={localUntag} entry={i}/>
            </Segment>);
        } else {
            body = <p {...t}>No results</p>;
        }
    }

    const paginator = <center style={{marginTop: '2em'}}>
        <Paginator activePage={pages.activePage} totalPages={pages.totalPages} onPageChange={pages.setPage}/>
    </center>;

    const label = <Label color={estimate > 0 ? 'violet' : undefined}>{normalizeEstimate(estimate)}</Label>;

    return <React.Fragment>
        <AccordionTitle
            index={index}
            active={index === activeIndex}
            onClick={() => onClick(index, activeIndex)}
        >
            <Header as='h3'>
                <Icon name='dropdown'/> {title} {label}
            </Header>
        </AccordionTitle>
        <AccordionContent active={index === activeIndex}>
            <Header as='h4'>{date}</Header>
            {body}
            {paginator}
        </AccordionContent>
    </React.Fragment>
}

const ZimsRefreshWarning = () => {
    return <Message icon warning onClick={refreshFiles}>
        <SIcon name='hand point right'/>
        <Message.Content>
            <Message.Header>No Zims have been indexed.</Message.Header>
            <a href='#'>Click here</a> to refresh all your files.
        </Message.Content>
    </Message>;
}

export const ZimSearchView = ({suggestions, loading}) => {
    const [activeIndex, setActiveIndex] = React.useState(null);
    const {searchStr, activeTags, setTags} = useSearch();
    const {zimsEstimates} = suggestions;

    const handleClick = (index, activeIndex_) => {
        setActiveIndex(index === activeIndex_ ? -1 : index);
    }

    let body;
    if (!_.isEmpty(zimsEstimates)) {
        body = zimsEstimates.map((i, index) => <ZimAccordion
            key={i['path']}
            index={index}
            activeIndex={activeIndex}
            data={i}
            searchStr={searchStr}
            activeTags={activeTags}
            onClick={handleClick}
        />);
    } else if (loading) {
        body = <AccordionContent>
            <Segment placeholder>
                <Loader active={true}/>
            </Segment>
        </AccordionContent>;
    } else if (_.isEmpty(zimsEstimates)) {
        body = <ZimsRefreshWarning/>;
    }

    return <>
        <TagsQuerySelector onChange={(i, j) => setTags(i)}/>
        <Accordion>
            {body}
        </Accordion>
    </>
}

const DownloadMessage = () => {
    return <InfoMessage>
        <p>More Zim files are available from the full Kiwix library&nbsp;
            <a href='https://download.kiwix.org/'>https://download.kiwix.org/</a>
        </p>
    </InfoMessage>
}

const ViewerMessage = () => {
    return <HandPointMessage>
        <p>You can view your Zim files using the Kiwix app, or at <a href={ZIM_VIEWER_URI}>{ZIM_VIEWER_URI}</a></p>
    </HandPointMessage>
}

const ZimCatalogItemRow = ({item, subscriptions, iso_639_codes, fetchSubscriptions}) => {
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

    const handleLanguageChange = (e, {value}) => {
        if (e) {
            e.preventDefault();
        }
        setLanguage(value);
    }

    const languageOptions = languages.map(i => {
        return {key: i, value: i, text: iso_639_codes[i]}
    });
    const languageDropdown = <Dropdown fluid search selection
                                       placeholder='Language'
                                       options={languageOptions}
                                       value={language}
                                       disabled={wrolModeEnabled}
                                       onChange={handleLanguageChange}
    />;

    const subscribeButton = <APIButton
        color='grey'
        disabled={pending}
        onClick={handleButton}
        obeyWROLMode={true}
    >
        {subscription && !languageChange ? 'Unsubscribe' : 'Subscribe'}
    </APIButton>

    return <TableRow key={name}>
        <TableCell>{name}</TableCell>
        <TableCell>{languageDropdown}</TableCell>
        <TableCell>{subscribeButton}</TableCell>
        <TableCell>{humanFileSize(size)}</TableCell>
    </TableRow>
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

        return <TableRow key={path}>
            <TableCell>{path}</TableCell>
            <TableCell>{humanFileSize(size)}</TableCell>
            <TableCell>{toggle}</TableCell>
        </TableRow>
    }

    render() {
        const {zims, catalog, iso_639_codes, subscriptions} = this.state;

        const zimFilesHeaders = [
            {key: 'path', text: 'Path', sortBy: 'path', width: 14},
            {key: 'size', text: 'Size', sortBy: 'size', width: 2},
            {key: 'search', text: 'Search', sortBy: 'auto_search', width: 2},
        ];
        let zimFilesBody = <Placeholder>
            <PlaceholderHeader>
                <PlaceholderLine/>
                <PlaceholderLine/>
            </PlaceholderHeader>
        </Placeholder>;
        if (zims && zims.length >= 1) {
            zimFilesBody = <SortableTable
                tableProps={{striped: true}}
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
        let kiwixCatalog = <Placeholder>
            <PlaceholderHeader>
                <PlaceholderLine/>
                <PlaceholderLine/>
            </PlaceholderHeader>
        </Placeholder>;
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

        return <PageContainer>
            <Header as='h2'>Zim Files</Header>
            {zimFilesBody}

            <Header as='h2'>Kiwix Catalog</Header>
            {kiwixCatalog}

            <Divider/>

            <DownloadMessage/>
            <ViewerMessage/>
        </PageContainer>
    }
}

function ZimViewer({src = ZIM_VIEWER_URI, style = null}) {
    const fallback = <Segment>
        <Header as='h3'>Failed to fetch Zim service.</Header>
        <p>You may need to give permission to access the page: <a href={src}>{src}</a></p>

        <p>If the above does not work, try starting the service:</p>
        <pre>sudo systemctl start wrolpi-kiwix</pre>

        <p>Check the logs</p>
        <pre>journalctl -u wrolpi-kiwix</pre>
    </Segment>;

    return <IframeViewer title='zim' src={src} fallback={fallback} style={style}/>
}

export function ZimRoute() {
    useTitle('Zim');

    const links = [
        {text: 'Viewer', to: '/zim', key: 'zim', end: true},
        {text: 'Manage', to: '/zim/manage', key: 'manage'},
    ]

    return <div style={{marginTop: '2em'}}>
        <TabLinks links={links}/>
        <Routes>
            <Route path='/' exact element={<ZimViewer/>}/>
            <Route path='manage' exact element={<ManageZim/>}/>
        </Routes>
    </div>
}