import React, {useContext} from "react";
import {
    CardContent,
    CardDescription,
    CardHeader,
    CardMeta,
    Container,
    Dropdown,
    Image,
    Label,
    PlaceholderLine,
    TableCell,
    TableHeaderCell,
} from "semantic-ui-react";
import {
    CardGroupCentered,
    CardPosterLink,
    cardTitleWrapper,
    ExternalCardLink,
    FileIcon,
    humanFileSize,
    isoDatetimeToString,
    mimetypeColor,
    PageContainer,
    Paginator,
    PreviewLink,
    textEllipsis,
    useTitle
} from "./Common";
import {useQuery, useSearchFiles} from "../hooks/customHooks";
import {Route, Routes} from "react-router-dom";
import {CardPlacholder} from "./Placeholder";
import {ArchiveCard, ArchiveRowCells} from "./Archive";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {StatusContext, ThemeContext} from "../contexts/contexts";
import {Button, Card, CardIcon, Icon, Placeholder, Segment} from "./Theme";
import {SelectableTable} from "./Tables";
import {VideoCard, VideoRowCells} from "./Videos";
import _ from 'lodash';
import {FileBrowser} from "./FileBrowser";
import {refreshDirectoryFiles, refreshFiles} from "../api";
import {useSubscribeEventName} from "../Events";
import {FilePreviewContext} from "./FilePreview";
import {TagsContext} from "../Tags";


export function FilesPage() {
    useTitle('Files');

    return <FileBrowser/>;
}

function EbookCard({file}) {
    const {s} = useContext(ThemeContext);
    let {data} = file;

    const downloadUrl = `/download/${encodeURIComponent(file.primary_path)}`;
    const isEpub = file['mimetype'].startsWith('application/epub');
    const viewerUrl = isEpub ? `/epub.html?url=${downloadUrl}` : null;

    let cover = <FileIcon file={file}/>;
    if (data && data.cover_path) {
        const coverSrc = `/media/${encodeURIComponent(data.cover_path)}`;
        cover = <CardPosterLink poster_url={coverSrc}/>;
    }

    const color = mimetypeColor(file.mimetype);
    return <Card color={color}>
        <PreviewLink file={file}>
            {cover}
        </PreviewLink>
        <CardContent {...s}>
            <CardHeader>
                <Container textAlign='left'>
                    <ExternalCardLink to={viewerUrl || downloadUrl}>
                        {data ? data.title : file.title}
                    </ExternalCardLink>
                </Container>
            </CardHeader>
            <CardMeta>
                {data.creator ? <b {...s}>{data.creator}</b> : null}
                {file.size && <p {...s}>{humanFileSize(file.size)}</p>}
            </CardMeta>
        </CardContent>
    </Card>

}

function ImageCard({file}) {
    const {s} = useContext(ThemeContext);
    const {setPreviewFile} = React.useContext(FilePreviewContext);
    const url = `/media/${encodeURIComponent(file.primary_path)}`;

    let poster = <FileIcon file={file}/>;
    if (file.size && file.size < 50000000) {
        // Image is less than 5mb, use it.
        poster = <Image wrapped
                        src={url}
                        style={{position: 'relative', width: '100%'}}
                        onClick={() => setPreviewFile(file)}
        />
    }

    return <Card color={mimetypeColor(file.mimetype)}>
        <PreviewLink file={file}>
            {poster}
        </PreviewLink>
        <CardContent {...s}>
            <CardHeader>
                <ExternalCardLink to={url} className='no-link-underscore card-link'>
                    <p>{textEllipsis(file.title || file.stem || file.primary_path)}</p>
                </ExternalCardLink>
            </CardHeader>
            <CardMeta {...s}>
                <p>{isoDatetimeToString(file.modified / 1000)}</p>
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

    if (file.model === 'video') {
        return <VideoCard key={file['primary_path']} file={file}/>;
    } else if (file.model === 'archive') {
        return <ArchiveCard key={file['primary_path']} file={file}/>;
    } else if (file.mimetype && file.mimetype.startsWith('image/')) {
        return <ImageCard key={file['primary_path']} file={file}/>;
    } else if (isEbookType) {
        return <EbookCard key={file['primary_path']} file={file}/>;
    }

    const {data} = file;
    let author;
    if (data) {
        author = data['author'];
    }
    const downloadUrl = `/download/${encodeURIComponent(file.primary_path)}`;
    const color = mimetypeColor(file.mimetype);
    const size = file.size !== null && file.size !== undefined ? humanFileSize(file.size) : null;

    return <Card color={color}>
        <PreviewLink file={file}>
            <CardIcon>
                <FileIcon file={file}/>
            </CardIcon>
        </PreviewLink>
        <CardContent {...s}>
            <CardHeader>
                <ExternalCardLink to={downloadUrl}>
                    {cardTitleWrapper(file.title || file.name || file.primary_path)}
                </ExternalCardLink>
            </CardHeader>
            {author && <b {...s}>{author}</b>}
            <p>{isoDatetimeToString(file.modified)}</p>
            <p>{size}</p>
        </CardContent>
    </Card>
}

export function FileCards({files}) {
    if (!_.isEmpty(files)) {
        return <CardGroupCentered>
            {files.map(i => <FileCard key={i['primary_path']} file={i}/>)}
        </CardGroupCentered>
    } else if (files && files.length === 0) {
        return <Segment>No results!</Segment>
    } else {
        return <CardGroupCentered><CardPlacholder/></CardGroupCentered>
    }
}

function ImageRowCells({file}) {
    const url = `/media/${encodeURIComponent(file.primary_path)}`;

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
    </React.Fragment>
}

export function EbookRowCells({file}) {
    const {data} = file;

    let cover = <CardIcon><FileIcon file={file}/></CardIcon>;
    if (data && data.cover_path) {
        const coverSrc = `/media/${encodeURIComponent(data.cover_path)}`;
        cover = <Image wrapped src={coverSrc} width='50px'/>;
    }

    // Fragment for SelectableRow
    return <React.Fragment>
        <TableCell>
            <center>{cover}</center>
        </TableCell>
        <TableCell>
            <PreviewLink file={file}>
                {textEllipsis(file.title || file.stem)}
            </PreviewLink>
        </TableCell>
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
            <PreviewLink file={file}>{textEllipsis(file.title)}</PreviewLink>
        </TableCell>
    </React.Fragment>
}

export function FileTable({files, selectOn, onSelect, footer, selectedKeys}) {
    if (!files) {
        return <Placeholder>
            <PlaceholderLine/>
            <PlaceholderLine/>
            <PlaceholderLine/>
        </Placeholder>
    } else if (files && files.length > 0) {
        const headerContents = ['Poster', 'Title'];
        const rows = files.map(i => <FileRow key={i['key']} file={i}/>);
        return <SelectableTable
            headerContents={headerContents}
            selectOn={selectOn}
            onSelect={onSelect}
            selectedKeys={selectedKeys}
            footer={footer}
            rows={rows}
        />;
    } else {
        return <Segment>No results!</Segment>
    }
}

export function FileRowTagIcon({file}) {
    if (file.tags && file.tags.length) {
        return <Label circular color='green' style={{padding: '0.5em', marginRight: '0.5em'}}>
            <Icon name='tag' style={{margin: 0}}/>
        </Label>;
    }
}

export function FilesView({
                              files,
                              limit,
                              setLimit,
                              showLimit = false,
                              activePage,
                              totalPages,
                              view,
                              setView,
                              showView = true,
                              showSelect = false,
                              selectElem,
                              selectedKeys,
                              onSelect,
                              setPage,
                              menuColumnsCount,
                              menuColumns,
                              filterOptions,
                              activeFilters,
                              setFilters,
                              multipleFilters,
                              filterPlaceholder,
                          }) {

    let selectButton;
    const [selectOn, setSelectOn] = React.useState(false);
    const toggleSelectOn = () => setSelectOn(!selectOn);
    const selectButtonDisabled = view !== 'list';
    if (showSelect && selectOn) {
        selectButton = <Button active disabled={selectButtonDisabled} icon='checkmark box'
                               onClick={toggleSelectOn}/>;
    } else if (showSelect) {
        selectButton = <Button icon='checkmark box' disabled={selectButtonDisabled}
                               onClick={toggleSelectOn}/>;
    }

    let viewButton;
    if (showView) {
        if (view === 'list') {
            viewButton = <Button icon='th' onClick={() => setView('cards')}/>;
        } else {
            viewButton = <Button icon='browser' onClick={() => setView('list')}/>;
        }
    }

    let limitDropdown;
    const limitOptions = [
        {key: 12, value: 12, text: '12'},
        {key: 24, value: 24, text: '24'},
        {key: 48, value: 48, text: '48'},
        {key: 96, value: 96, text: '96'},
    ];
    if (showLimit) {
        limitDropdown = <Dropdown
            compact
            selection
            placeholder='Limit'
            options={limitOptions}
            value={parseInt(limit || limitOptions[0]['value'])}
            onChange={(e, {value}) => setLimit(value)}
        />
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
        body = <FileTable files={files} selectOn={selectOn}
                          onSelect={onSelect} footer={footer} selectedKeys={selectedKeys}/>;
    } else {
        body = <FileCards files={files}/>;
    }

    const filtersDropdown = <Dropdown selection clearable search
                                      multiple={multipleFilters || undefined}
                                      options={filterOptions || []}
                                      placeholder={filterPlaceholder || 'Files Types'}
                                      onChange={(e, {value}) => setFilters(value)}
                                      style={{marginLeft: '0.3em', marginTop: '0.3em'}}
                                      value={activeFilters}
    />;

    return <>
        <Grid columns={menuColumnsCount || 1} stackable>
            <Grid.Column mobile={16} computer={12}>
                {selectButton}
                {viewButton}
                {limitDropdown}
                <TagsFilesGroupDropdown/>
                {filterOptions && filtersDropdown}
            </Grid.Column>
            {menuColumns}
        </Grid>
        {body}
        {paginator}
    </>
}

export function TagsFilesGroupDropdown({onChange}) {
    // Creates a dropdown that the User can use to manipulate the tag query.
    const {searchParams, updateQuery} = useQuery();
    const activeTag = searchParams.get('tag');
    const {tags} = React.useContext(TagsContext);

    const localOnChange = (name) => {
        updateQuery({'tag': name});
        if (onChange) {
            onChange(name);
        }
    }

    let tagOptions = [];
    if (tags && tags.length) {
        for (let i = 0; i < tags.length; i++) {
            const {name} = tags[i];
            tagOptions = [...tagOptions, {key: name, text: name, value: name}];
        }

        return <Dropdown selection clearable search
                         options={tagOptions || []}
                         placeholder={'Tags'}
                         onChange={(e, {value}) => localOnChange(value)}
                         style={{marginLeft: '0.3em', marginTop: '0.3em'}}
                         value={activeTag}
        />;
    } else {
        return <React.Fragment/>
    }
}

export function FilesSearchView({
                                    showView = true,
                                    showLimit = false,
                                    showSelect = false,
                                    emptySearch = false,
                                    filterOptions,
                                    model,
                                    onSelect,
                                    setFilters,
                                }) {
    filterOptions = filterOptions || [
        {key: 'video', text: 'Video', value: 'video'},
        {key: 'archive', text: 'Archive', value: 'archive'},
        {key: 'pdf', text: 'PDF', value: 'pdf'},
        {key: 'ebook', text: 'eBook', value: 'ebook'},
        {key: 'audio', text: 'Audio', value: 'audio'},
        {key: 'image', text: 'Image', value: 'image'},
        {key: 'zip', text: 'ZIP', value: 'zip'},
    ];

    const {searchFiles, limit, setLimit, totalPages, activePage, setPage} =
        useSearchFiles(24, emptySearch, model);
    const {searchParams, updateQuery} = useQuery();
    const setView = (value) => updateQuery({view: value});
    const view = searchParams.get('view');

    const setFilter = (value) => updateQuery({'filter': value});

    return <FilesView
        files={searchFiles}
        limit={limit}
        setLimit={setLimit}
        showLimit={showLimit}
        activePage={activePage}
        totalPages={totalPages}
        view={view}
        setView={setView}
        showView={showView}
        showSelect={showSelect}
        onSelect={onSelect}
        setPage={setPage}
        filterOptions={filterOptions}
        setFilters={setFilters || setFilter}
    />
}

export function FilesRoute() {
    return <PageContainer>
        <Routes>
            <Route path='/' exact element={<FilesPage/>}/>
        </Routes>
    </PageContainer>;
}

export function FilesRefreshButton() {
    const {status} = useContext(StatusContext);
    const refreshing = status && status['flags'] && status['flags'].indexOf('refreshing') >= 0;
    const refreshingDirectory = status && status['flags'] && status['flags'].indexOf('refreshing_directory') >= 0;

    const [loading, setLoading] = React.useState(false);

    const handleClick = async () => {
        setLoading(true);
        await refreshFiles();
    }

    // Clear loading when global refresh event completes.
    useSubscribeEventName('global_refresh_completed', () => setLoading(false));

    return <Button icon
                   labelPosition='left'
                   loading={loading || refreshing || refreshingDirectory}
                   onClick={handleClick}
                   disabled={loading || refreshing}>
        <Icon name='refresh'/>
        Refresh All
    </Button>;
}

export function DirectoryRefreshButton({directory}) {
    const {status} = useContext(StatusContext);
    const refreshing = status && status['flags'] && status['flags'].indexOf('refreshing') >= 0;
    const refreshingDirectory = status && status['flags'] && status['flags'].indexOf('refreshing_directory') >= 0;

    const [loading, setLoading] = React.useState(false);

    const handleClick = async () => {
        setLoading(true);
        await refreshDirectoryFiles(directory);
    }

    // Clear loading when global refresh event completes.
    useSubscribeEventName('global_refresh_completed', () => setLoading(false));
    useSubscribeEventName('directory_refresh_completed', () => setLoading(false));

    return <Button icon
                   labelPosition='left'
                   loading={loading || refreshing || refreshingDirectory}
                   onClick={handleClick}
                   disabled={loading || refreshing || refreshingDirectory}
    >
        <Icon name='refresh'/>
        Refresh Directory
    </Button>
}
