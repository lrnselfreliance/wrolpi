import React, {useContext, useState} from "react";
import {
    CardGroupCentered,
    CardPoster,
    encodeMediaPath,
    ErrorMessage,
    ExternalCardLink,
    FileIcon,
    findPosterPath,
    HandPointMessage,
    humanFileSize,
    isoDatetimeToAgoPopup,
    PageContainer,
    Paginator,
    PreviewLink,
    SearchInput,
    TagIcon,
    Toggle,
    textEllipsis,
    useTitle
} from "./Common";
import {
    usePages,
    useSearchDate,
    useSearchFiles,
    useSearchCensored,
    useSearchDeep,
    useSearchFilter,
    useSearchOrder,
    useSearchView,
    useStatusFlag,
    useWROLMode
} from "../hooks/customHooks";
import {useFileWorkerStatus} from "../contexts/FileWorkerStatusContext";
import {IconArticle, IconLayoutList, IconSortAscending, IconSortDescending} from "@tabler/icons-react";
import {Link, Route, Routes, useSearchParams} from "react-router";
import {CardPlaceholder} from "./Placeholder";
import {ArchiveCard, ArchiveRowCells} from "./Archive";
import {QueryContext} from "../contexts/contexts";
import {
    Button,
    Card,
    Divider,
    Group,
    Header,
    Icon,
    IconButton,
    Label,
    Modal,
    Panel,
    Placeholder,
    Progress,
    Radio,
    Stack,
    Table,
    Tooltip,
} from "./ui";
import {DateRangeForm, dateRangeIsEmpty, MonthsForm} from "./DatesSelector";
import {SelectableTable} from "./Tables";
import {VideoCard, VideoRowCells} from "./Videos";
import {FileBrowser} from "./FileBrowser";
import {refreshFiles} from "../api";
import {TagsSelector} from "../Tags";
import {Headlines} from "./Headline";
import {useSearch} from "./Search";
import {FILES_MEDIA_URI} from "./Vars";

// Split a ts_headline snippet on our sentinel markers and wrap each match in <b>.
// We use sentinels instead of ts_headline's default <b> tags so the snippet can be
// safely rendered as React children without dangerouslySetInnerHTML.
function renderHighlightedSnippet(snippet) {
    const parts = snippet.split(/\[\[WROLPI_HL\]\]|\[\[\/WROLPI_HL\]\]/);
    // Even indices are plain text, odd indices are highlighted matches.
    return parts.map((part, i) => i % 2 === 1 ? <b key={i}>{part}</b> : <span key={i}>{part}</span>);
}

function EbookCard({file, sortField}) {
    const [searchParams] = useSearchParams();
    const query = searchParams.get('q') || '';

    const downloadUrl = `/download/${encodeMediaPath(file.primary_path)}`;
    const isEpub = file['mimetype'] && file['mimetype'].startsWith('application/epub');
    const viewerUrl = isEpub ? `/epub/epub.html?url=${downloadUrl}` : null;

    // Link to doc detail page if this is a modeled doc, augmenting with
    // the section hint from search so the viewer opens at the right chapter/page.
    const hint = file.section_hint;
    let detailUrl = file.model === 'doc' ? `/docs/${file.id}` : null;
    if (detailUrl && hint) {
        const params = new URLSearchParams();
        if (hint.kind === 'epub_spine') params.set('loc', String(hint.ordinal));
        if (hint.kind === 'pdf_page') params.set('page', String(hint.ordinal));
        if (query) params.set('q', query);
        detailUrl = `${detailUrl}?${params.toString()}`;
    }

    const title = file.title || file.stem || file.name;
    const header = detailUrl
        ? <Link to={detailUrl} className='no-link-underscore card-link card-title-ellipsis'>{title}</Link>
        : <ExternalCardLink to={viewerUrl || downloadUrl} className='card-title-ellipsis'>{title}</ExternalCardLink>;

    const meta = <>
        {file.author ? <div><b>{file.author}</b></div> : null}
        {sortField === 'published_datetime'
            ? <div>{file.published_datetime ? isoDatetimeToAgoPopup(file.published_datetime, false) : null}</div>
            : file.size && <div>{humanFileSize(file.size)}</div>
        }
        {hint && <div style={{fontSize: '0.85em', marginTop: '0.3em'}}>
            <b>{hint.label}</b>
            {hint.snippet && <span style={{marginLeft: '0.4em', opacity: 0.8}}>
                {renderHighlightedSnippet(hint.snippet)}
            </span>}
        </div>}
    </>;

    return <Card media={<CardPoster file={file} to={detailUrl}/>}
                 title={<Tooltip label={title}>{header}</Tooltip>}
                 meta={meta}
    />
}

function ImageCard({file}) {
    const url = `/media/${encodeMediaPath(file.primary_path)}`;

    const title = file.title || file.stem || file.primary_path;
    const header = <ExternalCardLink to={url} className='no-link-underscore card-link'>
        <span>{textEllipsis(title)}</span>
    </ExternalCardLink>;
    const dt = file.published_datetime || file.published_modified_datetime || file.modified;
    const meta = <>
        <div>{isoDatetimeToAgoPopup(dt, false)}</div>
        <div>{humanFileSize(file.size)}</div>
    </>;
    return <Card media={<PreviewLink file={file}><CardPoster file={file}/></PreviewLink>}
                 title={<Tooltip label={title}>{header}</Tooltip>}
                 meta={meta}
    />
}

function FileCard({file}) {
    const {sort} = useSearchOrder();
    const sortField = sort ? sort.replace(/^-/, '') : null;

    const isDocType = file.model === 'doc' || (file.mimetype && (
        file.mimetype.startsWith('application/epub') || file.mimetype.startsWith('application/x-mobipocket-ebook')
    ));
    // Default doc sort is published_datetime when no order query param is set.
    const docSortField = sortField || 'published_datetime';

    if (file.model === 'video' && 'video' in file) {
        return <VideoCard key={file['primary_path']} file={file}/>;
    } else if (file.model === 'archive') {
        return <ArchiveCard key={file['primary_path']} file={file}/>;
    } else if (file.mimetype && file.mimetype.startsWith('image/')) {
        return <ImageCard key={file['primary_path']} file={file}/>;
    } else if (isDocType) {
        return <EbookCard key={file['primary_path']} file={file} sortField={docSortField}/>;
    }

    const author = file.author;
    const size = file.size !== null && file.size !== undefined ? humanFileSize(file.size) : null;

    const title = file.title || file.name || file.primary_path;
    const dt = file.published_datetime || file.published_modified_datetime || file.modified;
    const header = <PreviewLink file={file}>
        <Tooltip label={title}><span className='card-title-ellipsis'>{title}</span></Tooltip>
    </PreviewLink>;
    const meta = <>
        {author && <div><b>{author}</b></div>}
        {sortField === 'published_datetime'
            ? <div>{file.published_datetime ? isoDatetimeToAgoPopup(file.published_datetime, false) : null}</div>
            : <>
                <div>{isoDatetimeToAgoPopup(dt, false)}</div>
                <div>{size}</div>
            </>
        }
    </>;
    return <Card media={<CardPoster file={file}/>} title={header} meta={meta}/>
}

export function FileCards({files}) {
    if (files && files.length >= 1) {
        return <CardGroupCentered>
            {files.map(i => <FileCard key={i['primary_path']} file={i}/>)}
        </CardGroupCentered>
    } else if (files && files.length === 0) {
        return <Panel>No results!</Panel>
    } else if (files === undefined) {
        return <ErrorMessage>Could not search!</ErrorMessage>
    }
    // Response is pending.
    return <CardGroupCentered><CardPlaceholder/></CardGroupCentered>
}

function ImageRowCells({file}) {
    const url = `/media/${encodeMediaPath(file.primary_path)}`;

    let poster = <FileIcon file={file} size='large'/>;
    if (file.size && file.size < 50000000) {
        // Image is less than 5mb, use it.
        poster = <img alt='' src={url} width='50'/>;
    }

    // Fragment for SelectableRow
    return <React.Fragment>
        <Table.Cell>
            <center>
                {poster}
            </center>
        </Table.Cell>
        <Table.Cell>
            <PreviewLink file={file}>
                <p>{textEllipsis(file.title || file.stem || file.primary_path)}</p>
            </PreviewLink>
        </Table.Cell>
        <Table.Cell>{humanFileSize(file.size)}</Table.Cell>
    </React.Fragment>
}

export function EbookRowCells({file}) {
    let cover = <FileIcon file={file} size='large'/>;
    const posterPath = findPosterPath(file);
    if (posterPath) {
        const coverSrc = `/media/${encodeMediaPath(posterPath)}`;
        cover = <img alt='' src={coverSrc} width='50'/>;
    }

    // Fragment for SelectableRow
    return <React.Fragment>
        <Table.Cell>
            <center>{cover}</center>
        </Table.Cell>
        <Table.Cell>
            <PreviewLink file={file}>
                <FileRowTagIcon file={file}/>
                {textEllipsis(file.title || file.stem)}
            </PreviewLink>
        </Table.Cell>
        <Table.Cell>{humanFileSize(file.size)}</Table.Cell>
    </React.Fragment>
}

function FileRow({file}) {
    const isDocType = file.model === 'doc' || (file.mimetype && (
        file.mimetype.startsWith('application/epub') || file.mimetype.startsWith('application/x-mobipocket-ebook')
    ));

    if (file.model === 'video' && 'video' in file) {
        return <VideoRowCells file={file}/>;
    } else if (file.model === 'archive') {
        return <ArchiveRowCells file={file}/>;
    } else if (file.mimetype && file.mimetype.startsWith('image/')) {
        return <ImageRowCells file={file}/>;
    } else if (isDocType) {
        return <EbookRowCells key={file['primary_path']} file={file}/>;
    }

    // Fragment for SelectableRow
    return <React.Fragment>
        <Table.Cell>
            <center><FileIcon file={file} size='large'/></center>
        </Table.Cell>
        <Table.Cell>
            <FileRowTagIcon file={file}/>
            <PreviewLink file={file}>{textEllipsis(file.title || file.name || file.stem)}</PreviewLink>
        </Table.Cell>
        <Table.Cell/>
    </React.Fragment>
}

export function FileTable({files, selectOn, onSelect, footer, selectedKeys}) {
    if (files && files.length > 0) {
        const headerContents = ['Poster', 'Title', 'Data'];
        const rows = files.map(i => <FileRow key={i['key']} file={i}/>);
        return <SelectableTable
            headerContents={headerContents}
            selectOn={selectOn}
            onSelect={onSelect}
            selectedKeys={selectedKeys}
            footer={footer}
            rows={rows}
        />;
    } else if (files) {
        return <Panel>No results!</Panel>
    } else if (files === undefined) {
        return <ErrorMessage>Could not search!</ErrorMessage>
    }

    return <Placeholder lines={3}/>
}

export function FileRowTagIcon({file}) {
    if (file.tags && file.tags.length) {
        return <TagIcon/>;
    }
}

export function SearchViewButton({headlines}) {
    const {view, setView} = useSearchView();

    if (headlines) {
        // Cycle: cards -> headline -> list
        if (view === 'headline') {
            return <IconButton icon='list' label='Switch to list view' onClick={() => setView('list')}/>;
        } else if (view === 'list') {
            return <IconButton icon='th' label='Switch to cards view' onClick={() => setView('cards')}/>;
        }
        return <IconButton icon={IconArticle} label='Switch to headline view' onClick={() => setView('headline')}/>;
    }

    // Cycle: cards -> list
    if (view === 'list') {
        return <IconButton icon='th' label='Switch to cards view' onClick={() => setView('cards')}/>;
    }
    return <IconButton icon={IconLayoutList} label='Switch to list view' onClick={() => setView('list')}/>;
}

export function FilesView(
    {
        files,
        activePage,
        totalPages,
        selectElem,
        selectedKeys,
        onSelect,
        setPage,
        headlines = false,
    },
) {
    const {view} = useSearchView();

    const paginator = <center style={{marginTop: '2em'}}>
        <Paginator activePage={activePage} totalPages={totalPages} onPageChange={setPage}/>
    </center>;

    let body;
    if (view === 'list') {
        const footer = selectElem ?
            <>
                <Table.HeaderCell colSpan='3'>{selectElem}</Table.HeaderCell>
            </> : null;
        body = <FileTable
            files={files}
            selectOn={true}
            onSelect={onSelect}
            footer={footer}
            selectedKeys={selectedKeys || []}
        />;
    } else if (view === 'headline') {
        body = <Headlines results={files}/>;
    } else {
        body = <FileCards files={files}/>;
    }

    const viewButton = <SearchViewButton headlines={headlines}/>

    return {
        body,
        paginator,
        viewButton,
    }
}

export function SearchFilter({filters = [], modalHeader, size = 'medium'}) {
    const {filter, setFilter} = useSearchFilter();
    const [open, setOpen] = useState(false);

    const handleOpen = (e) => {
        if (e) {
            e.preventDefault();
        }
        setOpen(true);
    }

    const handleClear = (e) => {
        if (e) {
            e.preventDefault();
        }
        setFilter(null);
        setOpen(false);
    }

    const filterFields = filters.map(
        i => <Radio
            key={i['text']}
            label={i['text']}
            checked={filter === i['value']}
            onChange={() => setFilter(i['value'])}
        />
    );

    // Use violet color when filter has been applied.
    const buttonColor = filter ? 'violet' : 'grey';

    if (filters && filters.length > 0) {
        return <>
            <Modal open={open} onClose={() => setOpen(false)} closeIcon>
                {modalHeader || <Modal.Header>Filter</Modal.Header>}
                <Modal.Content>
                    <Stack gap='xs'>
                        {filterFields}
                    </Stack>
                </Modal.Content>
                <Modal.Actions>
                    <Button role='cancel' onClick={handleClear}>Clear</Button>
                    <Button role='cancel' onClick={() => setOpen(false)}>Close</Button>
                </Modal.Actions>
            </Modal>
            <IconButton icon='filter' label='Filter' onClick={handleOpen} color={buttonColor} size={size}/>
        </>
    }

    return <></>
}

export function TagsQuerySelector({onChange, showAny = true}) {
    // Creates modal that the User can use to manipulate the tag query params.
    const {activeTags, anyTag, setTags, setAnyTag} = useSearch();

    const localOnChange = (tagNames, newAnyTag) => {
        if (newAnyTag) {
            setAnyTag(true);
        } else {
            setTags(tagNames);
        }
        if (onChange) {
            onChange(tagNames, newAnyTag);
        }
    }

    return <TagsSelector hideGroup={true}
                         hideEdit={true}
                         showAny={showAny}
                         active={anyTag || activeTags && activeTags.length > 0}
                         selectedTagNames={activeTags}
                         anyTag={anyTag}
                         onChange={localOnChange}
                         filterByOverlap={true}
                         style={{marginLeft: '0.3em', marginTop: '0.3em'}}
    />
}

// see `filterToMimetypes`
export const fileMimetypeFilterOptions = [
    {key: 'video', text: 'Video', value: 'video'},
    {key: 'archive', text: 'Archive', value: 'archive'},
    {key: 'pdf', text: 'PDF', value: 'pdf'},
    {key: 'ebook', text: 'eBook', value: 'ebook'},
    {key: 'doc', text: 'Document', value: 'doc'},
    {key: 'audio', text: 'Audio', value: 'audio'},
    {key: 'image', text: 'Image', value: 'image'},
    {key: 'zip', text: 'ZIP', value: 'zip'},
    {key: 'model', text: '3D Model', value: 'model'},
    {key: 'software', text: 'Software', value: 'software'},
];

export const docMimetypeFilterOptions = [
    {key: 'pdf', text: 'PDF', value: 'pdf'},
    {key: 'epub', text: 'EPUB', value: 'epub'},
    {key: 'comic', text: 'Comic', value: 'comic'},
    {key: 'mobi', text: 'MOBI', value: 'mobi'},
];

export function FileSearchFilterButton({size = 'medium'}) {
    return <SearchFilter filters={fileMimetypeFilterOptions} size={size}/>
}

export function DocSearchFilterButton({size = 'medium'}) {
    return <SearchFilter filters={docMimetypeFilterOptions} size={size}/>
}

// The app-wide default page size (matches usePages' fallback); used to reset Results Per Page on Clear All.
const DEFAULT_SEARCH_LIMIT = 24;

// A single section within the comprehensive SearchFilterModal.  Vertical spacing between sections is
// provided by the surrounding Stack.
function SearchFilterSection({header, children}) {
    return <>
        <Header as='h4' style={{marginBottom: '0.6em'}}>{header}</Header>
        {children}
    </>
}

// A comprehensive modal which combines every search option (sort, tags, file-type filter, dates, limit)
// into a single dialog.  Which sections appear is controlled by the props, so each page can show only what
// is relevant.  All state is URL-query driven (same hooks the individual controls use), so no extra wiring
// is required on the page.
export function SearchFilterModal(
    {
        open,
        onClose,
        sorts = null,
        fileFilterOptions = null,
        showDates = false,
        showTags = true,
        showLimit = true,
        showCensored = false,
        showDeep = false,
        limitOptions = [12, 24, 48, 96],
    },
) {
    // Committed (URL) state — read only; drafts below hold the user's in-progress edits.
    const {filter} = useSearchFilter();
    const {sort} = useSearchOrder();
    const {dateRange, months} = useSearchDate();
    const {activeTags, anyTag} = useSearch();
    const {censored} = useSearchCensored();
    const {deep} = useSearchDeep();
    const {limit} = usePages(DEFAULT_SEARCH_LIMIT);
    const {updateQuery} = useContext(QueryContext);

    const emptyRange = [null, null];
    const seededRange = dateRange && (dateRange[0] || dateRange[1]) ? dateRange : emptyRange;
    const seededMonths = (months || []).map(i => parseInt(i));

    // Every selection is drafted locally and only applied to the URL (which performs the search) when the
    // modal is closed — via Done, the close icon, or clicking away.
    const [draftSort, setDraftSort] = useState(null);
    const [draftFilter, setDraftFilter] = useState(null);
    const [draftTags, setDraftTags] = useState([]);
    const [draftAnyTag, setDraftAnyTag] = useState(false);
    const [draftLimit, setDraftLimit] = useState(null);
    const [draftMonths, setDraftMonths] = useState([]);
    const [draftRange, setDraftRange] = useState(emptyRange);
    const [draftCensored, setDraftCensored] = useState(false);
    const [draftDeep, setDraftDeep] = useState(false);

    // Seed the drafts from the URL each time the modal is opened.
    React.useEffect(() => {
        if (open) {
            setDraftSort(sort || null);
            setDraftFilter(filter || null);
            setDraftTags(activeTags || []);
            setDraftAnyTag(anyTag || false);
            setDraftLimit(limit);
            setDraftMonths(seededMonths);
            setDraftRange(seededRange);
            setDraftCensored(censored || false);
            setDraftDeep(deep || false);
        }
    }, [open]);

    const handleClose = () => {
        // Apply every changed draft in a SINGLE updateQuery — sequential setters would each merge against
        // the same stale searchParams and clobber one another.  Only reset pagination if something changed.
        const params = {};
        if (sorts && (draftSort || null) !== (sort || null)) {
            params.order = draftSort;
        }
        if (fileFilterOptions && (draftFilter || null) !== (filter || null)) {
            params.filter = draftFilter;
        }
        if (showTags && (draftAnyTag !== anyTag || JSON.stringify(draftTags) !== JSON.stringify(activeTags))) {
            if (draftAnyTag) {
                params.tag = [];
                params.anyTag = 'true';
            } else {
                params.tag = draftTags;
                params.anyTag = null;
            }
        }
        if (showLimit && draftLimit !== limit) {
            params.l = draftLimit;
        }
        if (showDates && (JSON.stringify(draftMonths) !== JSON.stringify(seededMonths)
            || JSON.stringify(draftRange) !== JSON.stringify(seededRange))) {
            let newFromDate = null;
            let newToDate = null;
            if (draftRange[0] <= draftRange[1]) {
                newFromDate = draftRange[0];
                newToDate = draftRange[1];
            }
            params.fromDate = newFromDate;
            params.toDate = newToDate;
            params.month = draftMonths;
        }
        if (showCensored && draftCensored !== censored) {
            params.censored = draftCensored ? 'true' : null;
        }
        if (showDeep && draftDeep !== deep) {
            params.deep = draftDeep ? 'true' : null;
        }
        if (Object.keys(params).length > 0) {
            params.o = 0;
            updateQuery(params);
        }
        if (onClose) {
            onClose();
        }
    }

    const handleClearAll = () => {
        // Reset the form only; nothing is applied until the modal is closed.
        setDraftSort(null);
        setDraftFilter(null);
        setDraftTags([]);
        setDraftAnyTag(false);
        setDraftLimit(DEFAULT_SEARCH_LIMIT);
        setDraftMonths([]);
        setDraftRange(emptyRange);
        setDraftCensored(false);
        setDraftDeep(false);
    }

    // Sort section (operates on the draft).
    const sortKey = draftSort ? draftSort.replace(/^-/, '') : (sorts ? sorts[0]['value'] : null);
    const desc = draftSort ? draftSort.startsWith('-') : true;
    const sortButtons = sorts && sorts.map(o =>
        <Button key={o['value']}
                color={o['value'] === sortKey ? 'violet' : undefined}
                onClick={() => setDraftSort(desc ? `-${o['value']}` : o['value'])}
                style={{margin: '0.2em'}}
        >{o['text']}</Button>
    );
    const directionToggle = <Button icon={desc ? IconSortDescending : IconSortAscending}
                                    onClick={() => {
                                        const base = sortKey || sorts[0]['value'];
                                        setDraftSort(desc ? base : `-${base}`);
                                    }}>
        {desc ? 'Descending' : 'Ascending'}
    </Button>;

    // File-type filter section (single-select radios; clicking the active one clears it).  Wraps so more
    // options fit on each line.
    const filterFields = fileFilterOptions && fileFilterOptions.map(i =>
        <Radio key={i['value']}
               label={i['text']}
               checked={draftFilter === i['value']}
               onChange={() => setDraftFilter(draftFilter === i['value'] ? null : i['value'])}
        />
    );

    // Results-per-page as buttons (matches the Sort By buttons and avoids a dropdown menu being clipped by
    // the scrolling modal content).
    const limitButtons = limitOptions.map(i =>
        <Button key={i}
                color={(draftLimit || limitOptions[0]) === i ? 'violet' : undefined}
                onClick={() => setDraftLimit(i)}
                style={{margin: '0.2em'}}
        >{i}</Button>
    );

    return <Modal open={open} onClose={handleClose} closeIcon size='small'>
        <Modal.Header>Search Filters</Modal.Header>
        <Modal.Content>
            <Stack gap='lg'>
                {sorts &&
                    <SearchFilterSection header='Sort By'>
                        <div style={{marginBottom: '1em'}}>{directionToggle}</div>
                        <div>{sortButtons}</div>
                    </SearchFilterSection>}

                {fileFilterOptions &&
                    <SearchFilterSection header='File Type'>
                        <Group gap='md'>{filterFields}</Group>
                    </SearchFilterSection>}

                {(showTags || showLimit) &&
                    <Group align='flex-start' grow wrap='wrap'>
                        {showTags &&
                            <div style={{minWidth: 220}}>
                                <SearchFilterSection header='Tags'>
                                    <TagsSelector hideGroup hideEdit showAny
                                                  active={draftAnyTag || (draftTags && draftTags.length > 0)}
                                                  selectedTagNames={draftTags}
                                                  anyTag={draftAnyTag}
                                                  filterByOverlap={true}
                                                  onChange={(tagNames, newAnyTag) => {
                                                      if (newAnyTag) {
                                                          setDraftAnyTag(true);
                                                          setDraftTags([]);
                                                      } else {
                                                          setDraftAnyTag(false);
                                                          setDraftTags(tagNames);
                                                      }
                                                  }}
                                                  style={{marginLeft: '0.3em', marginTop: '0.3em'}}
                                    />
                                </SearchFilterSection>
                            </div>}
                        {showLimit &&
                            <div style={{minWidth: 160}}>
                                <SearchFilterSection header='Results Per Page'>
                                    <div>{limitButtons}</div>
                                </SearchFilterSection>
                            </div>}
                    </Group>}

                {showCensored &&
                    <SearchFilterSection header='Availability'>
                        <Toggle label='Only censored (no longer available to download)'
                                checked={draftCensored}
                                onChange={setDraftCensored}
                        />
                    </SearchFilterSection>}

                {showDeep &&
                    <SearchFilterSection header='Search Depth'>
                        <Toggle label='Deep search (captions, document text; slower)'
                                checked={draftDeep}
                                onChange={setDraftDeep}
                        />
                    </SearchFilterSection>}

                {showDates &&
                    <SearchFilterSection header='Published Date'>
                        <MonthsForm monthsSelected={draftMonths} setMonthsSelected={setDraftMonths}/>
                        <Divider/>
                        <DateRangeForm dateRange={draftRange} setDateRange={setDraftRange}/>
                    </SearchFilterSection>}
            </Stack>
        </Modal.Content>
        <Modal.Actions>
            <Button role='cancel' onClick={handleClearAll} style={{marginRight: 'auto'}}>Clear All</Button>
            <Button role='primary' onClick={handleClose}>Done</Button>
        </Modal.Actions>
    </Modal>
}

// The trigger button which opens the comprehensive SearchFilterModal.  Turns violet and displays a count
// badge when any of its filters are active.
export function SearchFilterButton(
    {
        sorts = null,
        fileFilterOptions = null,
        showDates = false,
        showTags = true,
        showLimit = true,
        showCensored = false,
        showDeep = false,
        limitOptions = [12, 24, 48, 96],
        size = 'medium',
        content = 'Filter',
    },
) {
    const [open, setOpen] = useState(false);
    const {filter} = useSearchFilter();
    const {sort} = useSearchOrder();
    const {dateRange, months} = useSearchDate();
    const {activeTags, anyTag} = useSearch();
    const {censored} = useSearchCensored();
    const {deep} = useSearchDeep();

    let count = 0;
    if (fileFilterOptions && filter) {
        count += 1;
    }
    if (sorts && sort) {
        count += 1;
    }
    if (showTags && ((activeTags && activeTags.length > 0) || anyTag)) {
        count += 1;
    }
    if (showDates && ((months && months.length > 0) || !dateRangeIsEmpty(dateRange))) {
        count += 1;
    }
    if (showCensored && censored) {
        count += 1;
    }
    if (showDeep && deep) {
        count += 1;
    }
    const active = count > 0;

    return <>
        <Button icon='filter' color={active ? 'violet' : 'grey'} size={size} onClick={() => setOpen(true)}>
            {content}
            {count > 0 &&
                <Label style={{marginLeft: '0.7em'}}>{count}</Label>}
        </Button>
        <SearchFilterModal
            open={open}
            onClose={() => setOpen(false)}
            sorts={sorts}
            fileFilterOptions={fileFilterOptions}
            showDates={showDates}
            showTags={showTags}
            showLimit={showLimit}
            showCensored={showCensored}
            showDeep={showDeep}
            limitOptions={limitOptions}
        />
    </>
}

// The single-line search control row shared by the Videos/Archives/Docs result pages:
//   [ view toggle ] [ search input (grows) ] [ Filter button ]
// The text input is managed locally and only submits its value on enter/clear.  Filter options are
// forwarded to the SearchFilterButton so each page shows only the sections relevant to it.
export function SearchControlBar(
    {
        searchStr,
        setSearchStr,
        placeholder = 'Search...',
        inputRef,
        viewButton,
        sorts = null,
        fileFilterOptions = null,
        showDates = false,
        showCensored = false,
        showDeep = false,
    },
) {
    const [localSearchStr, setLocalSearchStr] = useState(searchStr || '');

    const searchInput = <SearchInput
        searchStr={localSearchStr}
        onChange={setLocalSearchStr}
        onClear={() => setLocalSearchStr(null)}
        onSubmit={setSearchStr}
        placeholder={placeholder}
        inputRef={inputRef}
    />;

    return <div style={{display: 'flex', alignItems: 'center', gap: '0.5em', marginBottom: '1em'}}>
        {viewButton}
        <div style={{flexGrow: 1, minWidth: 0}}>{searchInput}</div>
        <SearchFilterButton sorts={sorts} fileFilterOptions={fileFilterOptions} showDates={showDates}
                            showCensored={showCensored} showDeep={showDeep}/>
    </div>
}

// Reminds the user that the fast search only matches titles/authors/descriptions.  Used by the module
// pages (Videos/Archives/Docs), which have no deep estimate, so it shows whenever a fast search is
// active; FilesSearchView has a count-aware variant.
export function DeepSearchHint({searchStr, files}) {
    const {deep} = useSearchDeep();
    const {updateQuery} = useContext(QueryContext);

    if (!searchStr || deep || !Array.isArray(files)) {
        return null;
    }

    return <Panel>
        {files.length === 0 ? 'Not finding what you need?' : 'More results may be available in deep search.'}
        <Button role='primary'
                onClick={() => updateQuery({deep: 'true', o: 0})}
                style={{marginLeft: '1em'}}
        >Try deep search</Button>
    </Panel>
}

export function FilesSearchView({
                                    showView = true,
                                    emptySearch = false,
                                    model,
                                    deepEstimate = null,
                                }) {

    const {searchFiles, total, searchStr, pages} = useSearchFiles(24, emptySearch, model);
    const {deep} = useSearchDeep();
    const {updateQuery} = useContext(QueryContext);

    const {body, paginator, viewButton} = FilesView(
        {
            files: searchFiles,
            activePage: pages.activePage,
            totalPages: pages.totalPages,
            selectElem: null,
            selectedKeys: null,
            onSelect: null,
            setPage: pages.setPage,
            headlines: true,
        },
    );

    // The default search only matches titles/authors/descriptions; offer deep search when it would find
    // more.  `deepEstimate` comes from the search estimates; without it, fall back to a generic hint on
    // zero results.
    let deepHint = null;
    if (Boolean(searchStr) && !deep && searchFiles) {
        const moreCount = deepEstimate !== null && deepEstimate !== undefined && total !== null
            ? deepEstimate - total : null;
        // Enable deep search and reset pagination in a single update (like the filter modal does), so the
        // user starts at page 1 of the deep results.
        const deepButton = <Button role='primary'
                                   onClick={() => updateQuery({deep: 'true', o: 0})}
                                   style={{marginLeft: '1em'}}
        >Try deep search</Button>;
        if (searchFiles.length === 0 && (moreCount === null || moreCount > 0)) {
            deepHint = <Panel>
                {moreCount > 0
                    ? `No results in fast search.  ${moreCount} result${moreCount === 1 ? '' : 's'} available in deep search.`
                    : 'Not finding what you need?'}
                {deepButton}
            </Panel>;
        } else if (searchFiles.length > 0 && moreCount > 0) {
            deepHint = <Panel>
                {`${moreCount} more result${moreCount === 1 ? '' : 's'} available in deep search.`}
                {deepButton}
            </Panel>;
        }
    }

    return <>
        {showView && <div style={{marginBottom: '1em'}}>{viewButton}</div>}
        {body}
        {deepHint}
        {paginator}
    </>
}

function getPhaseLabel(status) {
    switch (status) {
        case 'counting':
            return 'Counting';
        case 'comparing':
        case 'upserting':
        case 'deleting':
            return 'Inserting';
        case 'modeling':
            return 'Modeling';
        case 'indexing':
            return 'Indexing';
        case 'cleanup':
            return 'Cleanup';
        case 'planning':
            return 'Move: Planning';
        case 'moving':
            return 'Move: Moving';
        case 'reverting':
            return 'Reverting';
        case 'reorganizing':
            return 'Reorganizing';
        case 'batch_reorganizing':
            return 'Batch Reorganizing';
        case 'error':
            return 'Error';
        default:
            return null;
    }
}

// Map backend status to refresh phase number (1-5)
function getRefreshPhase(status) {
    switch (status) {
        case 'counting':
            return 1;
        case 'comparing':
        case 'upserting':
        case 'deleting':
            return 2;
        case 'modeling':
            return 3;
        case 'indexing':
            return 4;
        case 'cleanup':
            return 5;
        default:
            return 0;
    }
}

// Check if this is a global refresh (full media directory)
function isGlobalRefresh(progress) {
    if (!progress || progress.status === 'idle') return false;
    if (progress.task_type !== 'refresh') return false;

    // Global refresh has a single path ending with the media directory name
    const paths = progress.paths || [];
    return paths.length === 1 && (paths[0].endsWith('/wrolpi') || paths[0] === '/media/wrolpi');
}

const REFRESH_PHASES = [
    {key: 1, icon: 'search', title: 'Counting', description: 'Finding files'},
    {key: 2, icon: 'disk', title: 'Inserting', description: 'Updating database'},
    {key: 3, icon: 'settings', title: 'Modeling', description: 'Extracting metadata'},
    {key: 4, icon: 'book', title: 'Indexing', description: 'Building search index'},
    {key: 5, icon: 'check circle', title: 'Cleanup', description: 'Finalizing'},
];

// Replaces Semantic's Step.Group/Step: a row of phase markers, brightness/weight (via the active
// border) carrying the current stage rather than a bespoke component from the shared library.
function RefreshStepItem({phase, isActive, isCompleted, isDisabled, description}) {
    return <div style={{
        display: 'flex', alignItems: 'center', gap: 8, flex: '1 1 160px', padding: '0.5em 0.75em',
        opacity: isDisabled ? 0.5 : 1,
        borderBottom: isActive ? '2px solid var(--blue)' : '2px solid transparent',
    }}>
        <Icon name={phase.icon} size='large'
              style={{color: isCompleted ? 'var(--green)' : isActive ? 'var(--blue)' : 'var(--muted)'}}/>
        <div>
            <div style={{fontWeight: 600, fontSize: 13}}>{phase.title}</div>
            <div style={{fontSize: 12, color: 'var(--muted)'}}>{isActive || isCompleted ? description : ''}</div>
        </div>
    </div>
}

export function RefreshSteps({progress}) {
    const currentPhase = getRefreshPhase(progress?.status);
    const {operation_processed, operation_total, status} = progress || {};

    if (currentPhase === 0) {
        return null;
    }

    return <div style={{display: 'flex', flexWrap: 'wrap', border: '1px solid var(--border)'}}>
        {REFRESH_PHASES.map(phase => {
            const isCompleted = phase.key < currentPhase;
            const isActive = phase.key === currentPhase;
            const isDisabled = phase.key > currentPhase;

            // Determine description for active phase
            let description = phase.description;
            if (isActive) {
                if (operation_total > 0) {
                    description = `${operation_processed?.toLocaleString()} / ${operation_total?.toLocaleString()}`;
                } else if (status === 'comparing') {
                    description = 'Comparing files...';
                } else if (status === 'upserting') {
                    description = 'Updating files...';
                } else if (status === 'deleting') {
                    description = 'Removing deleted...';
                }
            }

            return <RefreshStepItem key={phase.key} phase={phase} isActive={isActive} isCompleted={isCompleted}
                                    isDisabled={isDisabled} description={description}/>
        })}
    </div>
}

function RefreshProgressBar({status, operation_total, operation_processed, operation_percent, error}) {
    const phaseLabel = getPhaseLabel(status);

    if (!phaseLabel) {
        return null;
    }

    // Show error state
    if (status === 'error' && error) {
        return <Progress percent={100} color='red' label={`Error: ${error}`}/>;
    }

    let label = `${phaseLabel}`;
    if (operation_total > 0) {
        label = `${label} (${operation_processed.toLocaleString()} / ${operation_total.toLocaleString()})`;
    }

    return <Progress percent={operation_percent || 0} color='violet' label={label}/>;
}

export function FilesRefreshProgress() {
    const {status: progress} = useFileWorkerStatus();

    if (!progress || progress.status === 'idle') {
        return null;
    }

    const {status, operation_total, operation_processed, operation_percent, error} = progress;

    // Show Steps component AND progress bar for global refresh operations
    if (isGlobalRefresh(progress)) {
        return <>
            <RefreshSteps progress={progress}/>
            <RefreshProgressBar
                status={status}
                operation_total={operation_total}
                operation_processed={operation_processed}
                operation_percent={operation_percent}
                error={error}
            />
        </>;
    }

    // Show just progress bar for other operations (moves, reorganize, targeted refresh)
    return <RefreshProgressBar
        status={status}
        operation_total={operation_total}
        operation_processed={operation_processed}
        operation_percent={operation_percent}
        error={error}
    />;
}

function FilesPage() {
    useTitle('Files');

    return <>
        <FilesRefreshProgress/>
        <FileBrowser/>

        <HandPointMessage>
            <p>You can also view your media directory at <a href={FILES_MEDIA_URI}>{FILES_MEDIA_URI}</a></p>
        </HandPointMessage>
    </>;
}

export function FilesRoute() {
    return <PageContainer>
        <Routes>
            <Route path='/' exact element={<FilesPage/>}/>
        </Routes>
    </PageContainer>;
}

const useRefresh = () => {
    const wrolModeEnabled = useWROLMode();
    const globalRefreshActive = useStatusFlag('global_refresh_active');
    const [loading, setLoading] = React.useState(false);
    const [globalRefreshLoading, setGlobalRefreshLoading] = React.useState(false);
    const prevGlobalRefreshActive = React.useRef(false);

    const localRefreshFiles = async (paths) => {
        setLoading(true);
        try {
            await refreshFiles(paths);

            // Check if this was a global refresh (no paths = refresh all)
            // If so, set globalRefreshLoading and schedule a fallback timeout
            if (!paths || paths.length === 0) {
                setGlobalRefreshLoading(true);
                setTimeout(() => {
                    setGlobalRefreshLoading(false);
                }, 10000);
            }
        } finally {
            setLoading(false);
        }
    }

    // Clear globalRefreshLoading when flag transitions from true to false
    React.useEffect(() => {
        if (prevGlobalRefreshActive.current && !globalRefreshActive) {
            setGlobalRefreshLoading(false);
        }
        prevGlobalRefreshActive.current = globalRefreshActive;
    }, [globalRefreshActive]);

    const isGlobalRefreshing = globalRefreshLoading || globalRefreshActive;

    return {
        globalRefreshing: isGlobalRefreshing,
        loading,
        wrolModeEnabled,
        refreshFiles: localRefreshFiles,
    }
}

export function FilesRefreshButton({paths, showLabel}) {
    const {globalRefreshing, loading, wrolModeEnabled, refreshFiles} = useRefresh();
    const disabled = wrolModeEnabled || globalRefreshing;
    const busy = loading || globalRefreshing;

    if (showLabel) {
        return <Button role='cancel' icon='refresh' loading={busy} disabled={disabled}
                       onClick={() => refreshFiles(paths)}>Refresh</Button>;
    }
    return <IconButton role='cancel' icon='refresh' label='Refresh' loading={busy} disabled={disabled}
                       onClick={() => refreshFiles(paths)}/>;
}
