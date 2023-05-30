import {useOutdatedZims, useSearchZim} from "../hooks/customHooks";
import {
    Accordion,
    Button,
    Divider,
    Header,
    Icon,
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
    TableFooter,
    TableHeaderCell,
    TableRow
} from "semantic-ui-react";
import React, {useContext, useState} from "react";
import {
    encodeMediaPath,
    humanFileSize,
    normalizeEstimate,
    PageContainer,
    Paginator,
    TabLinks,
    TagIcon,
    useTitle
} from "./Common";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {TagsSelector} from "../Tags";
import {
    deleteOutdatedZims,
    fetchZims,
    fetchZimSubscriptions,
    refreshFiles,
    saveSettings,
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

const VIEWER_URL = `http://${window.location.hostname}:8085/`;

export const OutdatedZimsMessage = ({onClick}) => {
    const [open, setOpen] = React.useState(false);

    const {outdated, current} = useOutdatedZims();

    const onOpen = () => setOpen(true);
    const onClose = () => setOpen(false);

    const handleDelete = async (e) => {
        if (e) {
            e.preventDefault();
        }
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

    const handleIgnore = async (e) => {
        if (e) {
            e.preventDefault();
        }
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
                    <Button color='red' floated='left' onClick={handleDelete}>Delete</Button>
                    <Button onClick={onClose}>Close</Button>
                </ModalActions>
            </Modal>

            <Link to='/files?folders=zims'><SButton>Delete Manually</SButton></Link>
            <SButton secondary onClick={handleIgnore}>Ignore Forever</SButton>
        </Message.Content>
    </Message>
}

export const KiwixRestartMessage = () => {
    return <Message icon warning>
        <SIcon name='exclamation'/>
        <Message.Content>
            <Message.Header>Kiwix must be restarted</Message.Header>
            <p>New Zim files have been downloaded; you must restart your containers.</p>

            <p>Run the following to restart your containers:</p>
            <pre>  docker-compose restart</pre>
        </Message.Content>
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
        <Modal closeIcon
               open={open}
               onClose={() => setOpen(false)}>
            <ModalContent>
                <div className='full-height'>
                    <iframe title='textModal' src={url}
                            style={{
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

    return <React.Fragment>
        <AccordionTitle
            index={index}
            active={index === activeIndex}
            onClick={() => onClick(index, activeIndex)}
        >
            <Header as='h3'>
                <Icon name='dropdown'/> {title} <Label>{normalizeEstimate(estimate)}</Label>
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

export const ZimSearchView = ({estimates}) => {
    const [activeIndex, setActiveIndex] = React.useState(null);
    const {searchStr, activeTags, setTags} = useSearch();
    const {zims} = estimates;

    const handleClick = (index, activeIndex_) => {
        setActiveIndex(index === activeIndex_ ? -1 : index);
    }

    let body = <TextPlaceholder/>;
    if (zims && zims.length === 0) {
        body = <ZimsRefreshWarning/>;
    } else if (zims) {
        body = zims.map((i, index) => <ZimAccordion
            key={i['path']}
            index={index}
            activeIndex={activeIndex}
            data={i}
            searchStr={searchStr}
            activeTags={activeTags}
            onClick={handleClick}
        />);
    }

    return <>
        <TagsQuerySelector onChange={setTags}/>
        <Accordion>
            {body}
        </Accordion>
    </>
}

const ViewerMessage = () => {
    return <Message warning icon>
        <SIcon name='warning'/>
        <Message.Content>
            <p>You can view your Zim files using the Kiwix app, or at <a href={VIEWER_URL}>{VIEWER_URL}</a></p>
        </Message.Content>
    </Message>
}

const ZimCatalogItemRow = ({item, subscriptions, iso_639_codes, fetchSubscriptions}) => {
    const {name, languages, size} = item;
    const subscription = name in subscriptions ? subscriptions[name] : null;
    const subscriptionLanguage = subscription ? subscription['language'] : 'en';

    const [langauge, setLanguage] = useState(subscriptionLanguage);
    const [pending, setPending] = useState(false);
    const languageChange = subscription ? langauge !== subscription['language'] : false;

    const handleButton = async (e) => {
        if (e) {
            e.preventDefault();
        }
        let success = false;
        try {
            setPending(true);
            if (subscription && !languageChange) {
                success = await zimUnsubscribe(subscription['id']);
            } else {
                success = await zimSubscribe(name, langauge);
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
                                       value={langauge}
                                       onChange={handleLanguageChange}
    />;

    const subscribeButton = <Button
        disabled={pending}
        onClick={handleButton}>
        {subscription && !languageChange ? 'Unsubscribe' : 'Subscribe'}
    </Button>

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
            catalog: undefined,
            iso_639_codes: undefined,
            subscriptions: undefined,
            zims: undefined,
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
        }
    }

    async fetchSubscriptions() {
        try {
            const {subscriptions, catalog, iso_639_codes} = await fetchZimSubscriptions();
            this.setState({subscriptions, catalog, iso_639_codes});
        } catch (e) {
            console.error(e);
        }
    }

    zimFileTableRow = (zim, sortData) => {
        const {path, size} = zim;

        return <TableRow key={path}>
            <TableCell>{path}</TableCell>
            <TableCell>{humanFileSize(size)}</TableCell>
        </TableRow>
    }

    render() {
        const {zims, catalog, iso_639_codes, subscriptions} = this.state;

        const zimFilesHeaders = [
            {key: 'path', text: 'Path', sortBy: 'path', width: 14},
            {key: 'size', text: 'Size', sortBy: 'size', width: 2},
        ];
        let zimFilesBody = <Placeholder>
            <PlaceholderHeader>
                <PlaceholderLine/>
                <PlaceholderLine/>
            </PlaceholderHeader>
        </Placeholder>;
        if (zims && zims.length > 0) {
            zimFilesBody = <SortableTable
                data={zims}
                rowFunc={this.zimFileTableRow}
                rowKey='path'
                tableHeaders={zimFilesHeaders}
            />;
        } else if (zims === null || (zims && zims.length === 0)) {
            zimFilesBody = <Message icon warning>
                <Message.Content>
                    You have not subscribed to any Kiwix projects, or your files have not been refreshed.
                </Message.Content>
            </Message>;
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
        if (subscriptions && Object.keys(subscriptions).length > 0) {
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
                footer={<TableFooter>
                    <TableRow>
                        <TableHeaderCell colSpan={4}>
                            <p>More Zim files are available from the full Kiwix library&nbsp;
                                <a href='https://download.kiwix.org/'>https://download.kiwix.org/</a>
                            </p>
                        </TableHeaderCell>
                    </TableRow>
                </TableFooter>}
            />
        }

        return <PageContainer>
            <Header as='h2'>Zim Files</Header>
            {zimFilesBody}

            <Header as='h2'>Kiwix Catalog</Header>
            {kiwixCatalog}

            <Divider/>

            <ViewerMessage/>
        </PageContainer>
    }
}

function ZimApp() {
    return <iframe
        title='zim'
        src={VIEWER_URL}
        style={{
            position: 'fixed',
            height: '100%',
            width: '100%',
            border: 'none',
            backgroundColor: '#FFFFFF',
        }}/>
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
            <Route path='/' exact element={<ZimApp/>}/>
            <Route path='manage' exact element={<ManageZim/>}/>
        </Routes>
    </div>
}