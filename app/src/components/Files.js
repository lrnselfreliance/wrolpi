import React, {useContext, useState} from "react";
import {
    CardContent,
    CardDescription,
    CardHeader,
    CardMeta,
    Checkbox,
    Container,
    Dropdown,
    Form,
    Image,
    PlaceholderLine,
    Step,
    TableCell,
    TableHeaderCell,
} from "semantic-ui-react";
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
    mimetypeColor,
    PageContainer,
    Paginator,
    PreviewLink,
    TagIcon,
    textEllipsis,
    useTitle
} from "./Common";
import {
    usePages,
    useSearchFiles,
    useSearchFilter,
    useSearchView,
    useStatusFlag,
    useWROLMode
} from "../hooks/customHooks";
import {useFileWorkerStatus} from "../contexts/FileWorkerStatusContext";
import {Route, Routes} from "react-router";
import {CardPlaceholder} from "./Placeholder";
import {ArchiveCard, ArchiveRowCells} from "./Archive";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {Media, ThemeContext} from "../contexts/contexts";
import {
    Button,
    Card,
    Icon,
    Modal,
    Placeholder,
    Popup,
    Progress,
    Segment
} from "./Theme";
import {SelectableTable} from "./Tables";
import {VideoCard, VideoRowCells} from "./Videos";
import {FileBrowser} from "./FileBrowser";
import {refreshFiles} from "../api";
import {useSubscribeEventName} from "../Events";
import {TagsSelector} from "../Tags";
import {Headlines} from "./Headline";
import {useSearch} from "./Search";
import {FILES_MEDIA_URI} from "./Vars";

function EbookCard({file}) {
    const {s} = useContext(ThemeContext);

    const downloadUrl = `/download/${encodeMediaPath(file.primary_path)}`;
    const isEpub = file['mimetype'].startsWith('application/epub');
    const viewerUrl = isEpub ? `/epub/epub.html?url=${downloadUrl}` : null;

    const color = mimetypeColor(file.mimetype);
    const title = file.title || file.stem || file.name;
    const header = <ExternalCardLink to={viewerUrl || downloadUrl} className='card-title-ellipsis'>
        {title}
    </ExternalCardLink>;
    return <Card color={color}>
        <CardPoster file={file} preview={true}/>
        <CardContent {...s}>
            <CardHeader>
                <Container textAlign='left'>
                    <Popup on='hover'
                           trigger={header}
                           content={title}/>
                </Container>
            </CardHeader>
            <CardMeta>
                {file.author ? <b {...s}>{file.author}</b> : null}
                {file.size && <p {...s}>{humanFileSize(file.size)}</p>}
            </CardMeta>
        </CardContent>
    </Card>

}

function ImageCard({file}) {
    const {s} = useContext(ThemeContext);
    const url = `/media/${encodeMediaPath(file.primary_path)}`;

    const title = file.title || file.stem || file.primary_path;
    const header = <ExternalCardLink to={url} className='no-link-underscore card-link'>
        <p>{textEllipsis(title)}</p>
    </ExternalCardLink>;
    const dt = file.published_datetime || file.published_modified_datetime || file.modified;
    return <Card color={mimetypeColor(file.mimetype)}>
        <PreviewLink file={file}>
            <CardPoster file={file}/>
        </PreviewLink>
        <CardContent {...s}>
            <CardHeader>
                <Popup on='hover'
                       trigger={header}
                       content={title}/>
            </CardHeader>
            <CardMeta {...s}>
                <p>{isoDatetimeToAgoPopup(dt, false)}</p>
            </CardMeta>
            <CardDescription {...s}>
                <p>{humanFileSize(file.size)}</p>
            </CardDescription>
        </CardContent>
    </Card>
}

function FileCard({file}) {
    const {s} = useContext(ThemeContext);

    const isEbookType = file.mimetype && (
        file.mimetype.startsWith('application/epub') || file.mimetype.startsWith('application/x-mobipocket-ebook')
    );

    if (file.model === 'video' && 'video' in file) {
        return <VideoCard key={file['primary_path']} file={file}/>;
    } else if (file.model === 'archive') {
        return <ArchiveCard key={file['primary_path']} file={file}/>;
    } else if (file.mimetype && file.mimetype.startsWith('image/')) {
        return <ImageCard key={file['primary_path']} file={file}/>;
    } else if (isEbookType) {
        return <EbookCard key={file['primary_path']} file={file}/>;
    }

    const author = file.author;
    const color = mimetypeColor(file.mimetype);
    const size = file.size !== null && file.size !== undefined ? humanFileSize(file.size) : null;

    const title = file.title || file.name || file.primary_path;
    const dt = file.published_datetime || file.published_modified_datetime || file.modified;
    return <Card color={color}>
        <CardPoster file={file}/>
        <CardContent {...s}>
            <CardHeader>
                <PreviewLink file={file}>
                    <Popup on='hover'
                           trigger={<span className='card-title-ellipsis'>{title}</span>}
                           content={title}/>
                </PreviewLink>
            </CardHeader>
            {author && <b {...s}>{author}</b>}
            <p>{isoDatetimeToAgoPopup(dt, false)}</p>
            <p>{size}</p>
        </CardContent>
    </Card>
}

export function FileCards({files}) {
    if (files && files.length >= 1) {
        return <CardGroupCentered>
            {files.map(i => <FileCard key={i['primary_path']} file={i}/>)}
        </CardGroupCentered>
    } else if (files && files.length === 0) {
        return <Segment>No results!</Segment>
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
        poster = <Image wrapped src={url} width='50px'/>;
    }

    // Fragment for SelectableRow
    return <React.Fragment>
        <TableCell>
            <center>
                {poster}
            </center>
        </TableCell>
        <TableCell>
            <PreviewLink file={file}>
                <p>{textEllipsis(file.title || file.stem || file.primary_path)}</p>
            </PreviewLink>
        </TableCell>
        <TableCell>{humanFileSize(file.size)}</TableCell>
    </React.Fragment>
}

export function EbookRowCells({file}) {
    let cover = <Card.Icon><FileIcon file={file}/></Card.Icon>;
    const posterPath = findPosterPath(file);
    if (posterPath) {
        const coverSrc = `/media/${encodeMediaPath(posterPath)}`;
        cover = <Image wrapped src={coverSrc} width='50px'/>;
    }

    // Fragment for SelectableRow
    return <React.Fragment>
        <TableCell>
            <center>{cover}</center>
        </TableCell>
        <TableCell>
            <PreviewLink file={file}>
                <FileRowTagIcon file={file}/>
                {textEllipsis(file.title || file.stem)}
            </PreviewLink>
        </TableCell>
        <TableCell>{humanFileSize(file.size)}</TableCell>
    </React.Fragment>
}

function FileRow({file}) {
    const isEbookType = file.mimetype && (
        file.mimetype.startsWith('application/epub') || file.mimetype.startsWith('application/x-mobipocket-ebook')
    );

    if (file.model === 'video' && 'video' in file) {
        return <VideoRowCells file={file}/>;
    } else if (file.model === 'archive') {
        return <ArchiveRowCells file={file}/>;
    } else if (file.mimetype && file.mimetype.startsWith('image/')) {
        return <ImageRowCells file={file}/>;
    } else if (isEbookType) {
        return <EbookRowCells key={file['primary_path']} file={file}/>;
    }

    // Fragment for SelectableRow
    return <React.Fragment>
        <TableCell>
            <center><FileIcon file={file} size='large'/></center>
        </TableCell>
        <TableCell>
            <FileRowTagIcon file={file}/>
            <PreviewLink file={file}>{textEllipsis(file.title || file.name || file.stem)}</PreviewLink>
        </TableCell>
        <TableCell/>
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
        return <Segment>No results!</Segment>
    } else if (files === undefined) {
        return <ErrorMessage>Could not search!</ErrorMessage>
    }

    return <Placeholder>
        <PlaceholderLine/>
        <PlaceholderLine/>
        <PlaceholderLine/>
    </Placeholder>
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
            return <Button icon='list' onClick={() => setView('list')}/>;
        } else if (view === 'list') {
            return <Button icon='th' onClick={() => setView('cards')}/>;
        }
        return <Button icon='searchengin' onClick={() => setView('headline')}/>;
    }

    // Cycle: cards -> list
    if (view === 'list') {
        return <Button icon='th' onClick={() => setView('cards')}/>;
    }
    return <Button icon='browser' onClick={() => setView('list')}/>;
}

export function SearchLimitDropdown({limits = []}) {
    const {limit, setLimit} = usePages();
    const limitOptions = limits.map(i => {
        return {key: i, value: i, text: i.toString()}
    });

    return <Dropdown fluid selection
                     placeholder='Limit'
                     options={limitOptions}
                     value={limit || limitOptions[0]['value']}
                     onChange={(e, {value}) => setLimit(value)}
    />
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
        limitOptions = [12, 24, 48, 96],
        showAnyTag = false,
    },
) {
    const {view} = useSearchView();

    let selectButton;
    const [selectOn, setSelectOn] = React.useState(false);
    const toggleSelectOn = () => setSelectOn(!selectOn);
    const selectButtonDisabled = view !== 'list';
    if (selectOn) {
        selectButton = <Button active disabled={selectButtonDisabled} icon='checkmark box'
                               onClick={toggleSelectOn}/>;
    } else {
        selectButton = <Button icon='checkmark box' disabled={selectButtonDisabled}
                               onClick={toggleSelectOn}/>;
    }

    const paginator = <center style={{marginTop: '2em'}}>
        <Paginator activePage={activePage} totalPages={totalPages} onPageChange={setPage}/>
    </center>;

    let body;
    if (view === 'list') {
        const footer = selectOn && selectElem ?
            <>
                <TableHeaderCell colSpan='3'>{selectElem}</TableHeaderCell>
            </> : null;
        body = <FileTable
            files={files}
            selectOn={selectOn}
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
    const limitDropdown = <SearchLimitDropdown limits={limitOptions}/>;
    const tagQuerySelector = <TagsQuerySelector showAny={showAnyTag}/>;

    return {
        body,
        paginator,
        selectButton,
        viewButton,
        limitDropdown,
        tagQuerySelector,
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
        i => <Form.Field key={i['text']}>
            <Checkbox radio
                      label={i['text']}
                      name='searchFilterRadioGroup'
                      checked={filter === i['value']}
                      value={i['value']}
                      onChange={() => setFilter(i['value'])}
            />
        </Form.Field>
    );

    // Use violet color when filter has been applied.
    const buttonColor = filter ? 'violet' : 'grey';

    if (filters && filters.length > 0) {
        return <>
            <Modal open={open} onOpen={() => handleOpen()} onClose={() => setOpen(false)} closeIcon>
                {modalHeader || <Modal.Header>Filter</Modal.Header>}
                <Modal.Content>
                    <Form>
                        {filterFields}
                    </Form>
                </Modal.Content>
                <Modal.Actions>
                    <Button onClick={handleClear} secondary>Clear</Button>
                    <Button onClick={() => setOpen(false)}>Close</Button>
                </Modal.Actions>
            </Modal>
            <Button
                icon='filter'
                onClick={handleOpen}
                color={buttonColor}
                size={size}
            />
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
                         style={{marginLeft: '0.3em', marginTop: '0.3em'}}
    />
}

export function FileSearchFilterButton({size = 'medium'}) {
    // see `filterToMimetypes`
    const filterOptions = [
        {key: 'video', text: 'Video', value: 'video'},
        {key: 'archive', text: 'Archive', value: 'archive'},
        {key: 'pdf', text: 'PDF', value: 'pdf'},
        {key: 'ebook', text: 'eBook', value: 'ebook'},
        {key: 'audio', text: 'Audio', value: 'audio'},
        {key: 'image', text: 'Image', value: 'image'},
        {key: 'zip', text: 'ZIP', value: 'zip'},
        {key: 'model', text: '3D Model', value: 'model'},
        {key: 'software', text: 'Software', value: 'software'},
    ];

    return <SearchFilter filters={filterOptions} size={size}/>
}

export function FilesSearchView({
                                    showView = true,
                                    showSelect = false,
                                    emptySearch = false,
                                    model,
                                }) {

    const {searchFiles, pages} = useSearchFiles(24, emptySearch, model);

    const {body, paginator, selectButton, viewButton, limitDropdown, tagQuerySelector} = FilesView(
        {
            files: searchFiles,
            activePage: pages.activePage,
            totalPages: pages.totalPages,
            selectElem: null,
            selectedKeys: null,
            onSelect: null,
            setPage: pages.setPage,
            headlines: true,
            showAnyTag: true,
        },
    );

    return <>
        <Media at='mobile'>
            <Grid>
                <Grid.Row>
                    {showSelect &&
                        <Grid.Column width={2}>{selectButton}</Grid.Column>}
                    {showView &&
                        <Grid.Column width={2}>{viewButton}</Grid.Column>}
                    <Grid.Column width={4}>{limitDropdown}</Grid.Column>
                    <Grid.Column width={2}>{tagQuerySelector}</Grid.Column>
                </Grid.Row>
            </Grid>
        </Media>
        <Media greaterThanOrEqual='tablet'>
            <Grid>
                <Grid.Row>
                    {showSelect &&
                        <Grid.Column width={1}>{selectButton}</Grid.Column>}
                    {showView &&
                        <Grid.Column width={1}>{viewButton}</Grid.Column>}
                    <Grid.Column width={2}>{limitDropdown}</Grid.Column>
                    <Grid.Column width={1}>{tagQuerySelector}</Grid.Column>
                </Grid.Row>
            </Grid>
        </Media>
        {body}
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
    {key: 2, icon: 'database', title: 'Inserting', description: 'Updating database'},
    {key: 3, icon: 'cogs', title: 'Modeling', description: 'Extracting metadata'},
    {key: 4, icon: 'book', title: 'Indexing', description: 'Building search index'},
    {key: 5, icon: 'check circle', title: 'Cleanup', description: 'Finalizing'},
];

export function RefreshSteps({progress}) {
    const currentPhase = getRefreshPhase(progress?.status);
    const {operation_processed, operation_total, status} = progress || {};

    if (currentPhase === 0) {
        return null;
    }

    return (
        <Step.Group size='mini' fluid>
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

                return (
                    <Step
                        key={phase.key}
                        active={isActive}
                        completed={isCompleted}
                        disabled={isDisabled}
                    >
                        <Icon name={isCompleted ? 'check' : phase.icon}/>
                        <Step.Content>
                            <Step.Title>{phase.title}</Step.Title>
                            <Step.Description>{isActive || isCompleted ? description : ''}</Step.Description>
                        </Step.Content>
                    </Step>
                );
            })}
        </Step.Group>
    );
}

function RefreshProgressBar({status, operation_total, operation_processed, operation_percent, error}) {
    const phaseLabel = getPhaseLabel(status);

    if (!phaseLabel) {
        return null;
    }

    // Show error state
    if (status === 'error' && error) {
        return <Progress error percent={100}>{`Error: ${error}`}</Progress>;
    }

    let label = `${phaseLabel}`;
    if (operation_total > 0) {
        label = `${label} (${operation_processed.toLocaleString()} / ${operation_total.toLocaleString()})`;
    }

    return <Progress active color='violet' percent={operation_percent || 0} progress>{label}</Progress>;
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
    const refreshing = useStatusFlag('file_worker_busy');
    const refreshingDirectory = useStatusFlag('refreshing_directory');
    const wrolModeEnabled = useWROLMode();

    const [loading, setLoading] = React.useState(false);

    const localRefreshFiles = async (paths) => {
        setLoading(true);
        await refreshFiles(paths);
    }

    // Clear loading when global refresh event completes.
    useSubscribeEventName('refresh_completed', () => setLoading(false));

    return {
        refreshing,
        refreshingDirectory,
        wrolModeEnabled,
        loading,
        refreshFiles: localRefreshFiles,
    }
}

export function FilesRefreshButton({paths}) {
    const {refreshing, refreshingDirectory, wrolModeEnabled, loading, refreshFiles} = useRefresh();

    return <Button icon='refresh'
                   loading={loading || refreshing || refreshingDirectory}
                   onClick={() => refreshFiles(paths)}
                   disabled={wrolModeEnabled || loading || refreshing}/>
        ;
}
