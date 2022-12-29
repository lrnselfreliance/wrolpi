import React, {useContext} from "react";
import FileBrowser from 'react-keyed-file-browser';
import {
    Button as SButton,
    CardContent,
    CardDescription,
    CardHeader,
    CardMeta,
    Confirm,
    Container,
    Divider,
    Dropdown,
    Header as SHeader,
    Image,
    Modal,
    PlaceholderLine,
    TableCell,
    TableHeaderCell,
} from "semantic-ui-react";
import 'react-keyed-file-browser/dist/react-keyed-file-browser.css';
import {deleteFile, refreshDirectoryFiles, refreshFiles} from "../api";
import {
    CardGroupCentered,
    CardPosterLink, cardTitleWrapper,
    isoDatetimeToString,
    ExternalCardLink,
    FileIcon,
    humanFileSize,
    isEmpty,
    mimetypeColor,
    PageContainer,
    Paginator,
    textEllipsis,
    useTitle, CardLink
} from "./Common";
import {useBrowseFiles, useQuery, useSearchFiles} from "../hooks/customHooks";
import {Route, Routes} from "react-router-dom";
import {CardPlacholder} from "./Placeholder";
import {ArchiveCard, ArchiveRowCells} from "./Archive";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {ThemeContext} from "../contexts/contexts";
import {Button, Card, CardIcon, Header, Icon, Placeholder, Segment} from "./Theme";
import {SelectableTable} from "./Tables";
import {VideoCard, VideoRowCells} from "./Videos";
import _ from 'lodash';

const icons = {
    File: <Icon name='file'/>,
    Folder: <Icon name='folder'/>,
    FolderOpen: <Icon name='folder open'/>,
    Image: <Icon name='file image'/>,
    PDF: <Icon name='file pdf'/>,
};

export function Files() {
    useTitle('Files');

    const {t} = useContext(ThemeContext);

    const {browseFiles, setOpenFolders, fetchFiles} = useBrowseFiles();

    const [deleteOpen, setDeleteOpen] = React.useState(false);
    const [selectedFile, setSelectedFile] = React.useState(null);
    const [selectedDirectory, setSelectedDirectory] = React.useState(null);

    const handleFolderChange = async (file, browserProps) => {
        let openFolders = Object.keys(browserProps.openFolders);
        setOpenFolders(openFolders);
    }

    const onSelect = async (file) => {
        // A user can only select one file or one directory.
        if (file.key.endsWith('/')) {
            setSelectedFile(null);
            setSelectedDirectory(file);
        } else {
            setSelectedDirectory(null);
            setSelectedFile(file);
        }
    }

    const onDeleteFile = async () => {
        await deleteFile(selectedFile.key);
        await fetchFiles();
    }

    const openDelete = () => {
        setDeleteOpen(true);
    }

    const closeDelete = () => {
        setDeleteOpen(false);
    }

    const clearSelection = async (e) => {
        e.preventDefault();
        setOpenFolders(null);
        setSelectedDirectory(null);
        setSelectedFile(null);
        await fetchFiles();
    }

    let clearButton = <Button
        onClick={clearSelection}
        disabled={!!!selectedFile && !!!selectedDirectory}>
        Clear
    </Button>;

    let buttons;
    if (selectedFile) {
        buttons = <>
            <ExternalCardLink to={`/download/${selectedFile.key}`}>
                <Button primary>Open</Button>
            </ExternalCardLink>
            <Confirm
                open={deleteOpen}
                onCancel={closeDelete}
                onConfirm={onDeleteFile}
                content={`Are you sure you want to delete: ${selectedFile.key}`}
                confirmButton='Delete'
            />
            <Button floated='right' color='red' onClick={openDelete}>Delete</Button>
        </>;
    } else if (selectedDirectory) {
        buttons = <>
            <DirectoryFilesRefreshButton directory={selectedDirectory.key}/>
        </>;
    } else {
        buttons = <FilesRefreshButton/>;
    }

    return <>
        {clearButton}
        {buttons}
        <Divider/>
        <div {...t}>
            <FileBrowser
                showActionBar={false}
                canFilter={false}
                files={browseFiles}
                icons={icons}
                onFolderOpen={handleFolderChange}
                onFolderClose={handleFolderChange}
                onSelect={onSelect}
                detailRenderer={() => <></>} // Hide the preview that the 3rd party provided.
            />
        </div>
    </>
}

function EbookCard({file}) {
    const {s} = useContext(ThemeContext);
    let {ebook, suffix} = file;

    const downloadUrl = `/download/${encodeURIComponent(file.path)}`;
    const isEpub = file['mimetype'].startsWith('application/epub');
    const viewerUrl = isEpub ? `/epub.html?url=${downloadUrl}` : null;

    let cover = <CardIcon><FileIcon file={file}/></CardIcon>;
    if (ebook && ebook.cover_path) {
        const coverSrc = `/media/${encodeURIComponent(ebook.cover_path)}`;
        cover = <CardPosterLink to={viewerUrl || downloadUrl} poster_url={coverSrc} external={true}/>;
    }

    suffix = suffix ? _.trimStart(suffix, '.').toUpperCase() : null;

    const downloadButton = <ExternalCardLink to={downloadUrl}>
        <SButton
            icon='download'
            content='Download'
            labelPosition='left'/>
    </ExternalCardLink>;

    const detailsButton = <Button
        icon='file alternate'
        content='Details'
        labelPosition='left'
        disabled={!ebook}
        onClick={() => setDetailsOpen(true)}
    />;
    const [detailsOpen, setDetailsOpen] = React.useState(false);
    const detailsModal = <Modal closeIcon
                                open={detailsOpen}
                                onClose={() => setDetailsOpen(false)}
                                trigger={detailsButton}
    >
        <Modal.Header><SHeader as='h1'>{ebook.title || file.title}</SHeader></Modal.Header>
        <Modal.Content>
            <SHeader as='h3'>Author: {ebook.creator}</SHeader>
            <p>{humanFileSize(ebook.size)}</p>
            <SHeader as='h5'>eBook Path</SHeader>
            <pre>{ebook ? ebook.ebook_path : file.path}</pre>
            <SHeader as='h5'>Cover Path</SHeader>
            <pre>{ebook && ebook.cover_path ? ebook.cover_path : 'N/A'}</pre>
        </Modal.Content>
        <Modal.Actions>
            {downloadButton}
        </Modal.Actions>
    </Modal>;

    const color = mimetypeColor(file.mimetype);
    return <Card color={color}>
        {cover}
        <CardContent {...s}>
            <CardHeader>
                <Container textAlign='left'>
                    <ExternalCardLink to={viewerUrl || downloadUrl}>
                        {ebook ? ebook.title : file.title}
                    </ExternalCardLink>
                </Container>
            </CardHeader>
            <CardMeta>
                <pre {...s}>{suffix}</pre>
                {detailsModal}
            </CardMeta>
        </CardContent>
    </Card>

}

function ImageCard({file}) {
    const {s} = useContext(ThemeContext);
    const url = `/media/${encodeURIComponent(file.path)}`;

    let poster = <CardIcon><FileIcon file={file}/></CardIcon>;
    if (file.size && file.size < 50000000) {
        // Image is less than 5mb, use it.
        poster = <Image wrapped
                        src={url}
                        style={{position: 'relative', width: '100%'}}
        />;
    }

    return <Card color={mimetypeColor(file.mimetype)}>
        <ExternalCardLink to={url}>
            {poster}
        </ExternalCardLink>
        <CardContent {...s}>
            <CardHeader>
                <ExternalCardLink to={url} className='no-link-underscore card-link'>
                    <p>{textEllipsis(file.title || file.stem || file.path)}</p>
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

    if (file.model === 'video' && file['video']) {
        return <VideoCard key={file['path']} file={file}/>;
    } else if (file.model === 'archive' && file['archive']) {
        return <ArchiveCard key={file['path']} file={file}/>;
    } else if (file.mimetype && file.mimetype.startsWith('image/')) {
        return <ImageCard key={file['path']} file={file}/>;
    } else if (isEbookType) {
        return <EbookCard key={file['path']} file={file}/>;
    }

    const url = `/download/${encodeURIComponent(file.path)}`;
    const color = mimetypeColor(file.mimetype);
    const size = file.size !== null && file.size !== undefined ? humanFileSize(file.size) : null;

    return <Card color={color}>
        <ExternalCardLink to={url}>
            <CardIcon>
                <FileIcon file={file}/>
            </CardIcon>
        </ExternalCardLink>
        <CardContent {...s}>
            <CardHeader>
                <ExternalCardLink to={url}>
                    {cardTitleWrapper(file.title || file.stem || file.path)}
                </ExternalCardLink>
            </CardHeader>
            <p>{isoDatetimeToString(file.modified / 1000)}</p>
            <p>{size}</p>
        </CardContent>
    </Card>
}

export function FileCards({files}) {
    if (!isEmpty(files)) {
        return <CardGroupCentered>
            {files.map(i => <FileCard key={i['path']} file={i}/>)}
        </CardGroupCentered>
    } else if (files && files.length === 0) {
        return <Header as='h4'>No files found.</Header>
    } else {
        return <CardGroupCentered><CardPlacholder/></CardGroupCentered>
    }
}

function ImageRowCells({file}) {
    const url = `/media/${encodeURIComponent(file.path)}`;

    let poster = <FileIcon file={file} size='large'/>;
    if (file.size && file.size < 50000000) {
        // Image is less than 5mb, use it.
        poster = <Image wrapped src={url} width='50px'/>;
    }

    // Fragment for SelectableRow
    return (<React.Fragment>
        <TableCell>
            <center>
                {poster}
            </center>
        </TableCell>
        <TableCell>
            <ExternalCardLink to={url}>
                <p>{textEllipsis(file.title || file.stem || file.path)}</p>
            </ExternalCardLink>
        </TableCell>
    </React.Fragment>)
}

export function EbookRowCells({file}) {
    const {ebook} = file;

    const downloadUrl = `/download/${encodeURIComponent(file.path)}`;
    const viewerUrl = file['mimetype'].startsWith('application/epub') ? `/epub.html?url=${downloadUrl}` : null;

    let cover = <CardIcon><FileIcon file={file}/></CardIcon>;
    if (ebook && ebook.cover_path) {
        const coverSrc = `/media/${encodeURIComponent(ebook.cover_path)}`;
        cover = <Image wrapped src={coverSrc} width='50px'/>;
    }

    // Fragment for SelectableRow
    return (<React.Fragment>
        <TableCell>
            <center>{cover}</center>
        </TableCell>
        <TableCell>
            <CardLink to={viewerUrl || downloadUrl} newTab={true}>
                {textEllipsis(ebook.title || file.title)}
            </CardLink>
        </TableCell>
    </React.Fragment>)
}

function FileRow({file}) {
    const isEbookType = file.mimetype && (
        file.mimetype.startsWith('application/epub') || file.mimetype.startsWith('application/x-mobipocket-ebook')
    );

    if (file.model === 'video' && 'video' in file) {
        return <VideoRowCells file={file}/>;
    } else if (file.model === 'archive' && 'archive' in file) {
        return <ArchiveRowCells file={file}/>;
    } else if (file.mimetype && file.mimetype.startsWith('image/')) {
        return <ImageRowCells file={file}/>;
    } else if (isEbookType) {
        return <EbookRowCells key={file['path']} file={file}/>;
    }
    const onDownloadFile = async () => window.open(`/media/${file.key}`);

    // Fragment for SelectableRow
    return <React.Fragment>
        <TableCell>
            <center><FileIcon file={file} size='large'/></center>
        </TableCell>
        <TableCell onClick={() => onDownloadFile()}>
            {textEllipsis(file.title)}
        </TableCell>
    </React.Fragment>
}

export function FileTable({files, selectOn, onSelect, footer, selectedKeys}) {
    if (!isEmpty(files)) {
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
    } else if (isEmpty(files)) {
        return <Segment><p>No results!</p></Segment>
    } else {
        return <Placeholder>
            <PlaceholderLine/>
            <PlaceholderLine/>
            <PlaceholderLine/>
        </Placeholder>
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
                <TableHeaderCell/>
                <TableHeaderCell>{selectElem}</TableHeaderCell>
            </> : null;
        body = <FileTable files={files} selectOn={selectOn}
                          onSelect={onSelect} footer={footer} selectedKeys={selectedKeys}/>;
    } else {
        body = <FileCards files={files}/>;
    }

    const filtersDropdown = <Dropdown selection clearable search
                                      multiple={multipleFilters || undefined}
                                      options={filterOptions}
                                      placeholder={filterPlaceholder || 'Filters'}
                                      onChange={(e, {value}) => setFilters(value)}
                                      style={{marginLeft: '0.3em'}}
                                      value={activeFilters}
    />;

    return <>
        <Grid columns={menuColumnsCount || 1} stackable>
            <Grid.Column mobile={8} computer={6}>
                {selectButton}
                {viewButton}
                {limitDropdown}
                {filterOptions && filtersDropdown}
            </Grid.Column>
            {menuColumns}
        </Grid>
        {body}
        {paginator}
    </>
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
        {key: 'image', text: 'Image', value: 'image'},
        {key: 'zip', text: 'ZIP', value: 'zip'},
    ];

    const {searchFiles, limit, setLimit, totalPages, activePage, setPage, filter} =
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

function FilesRefreshButton() {
    const {t} = useContext(ThemeContext);

    const [loading, setLoading] = React.useState(false);
    const [name, setName] = React.useState('refresh');

    const handleClick = async () => {
        setLoading(true);
        await refreshFiles();
        setLoading(false);
        setName('check');
    }

    return <>
        <Button icon
                labelPosition='left'
                loading={loading}
                id='refresh_files'
                onClick={handleClick}>
            <Icon name={name}/>
            Refresh Files
        </Button>
        <label htmlFor='refresh_files' {...t}>
            Find and index all files in the media directory.
        </label>
    </>;
}

function DirectoryFilesRefreshButton({directory}) {
    const {t} = useContext(ThemeContext);

    const [loading, setLoading] = React.useState(false);
    const [name, setName] = React.useState('refresh');

    const handleClick = async () => {
        setLoading(true);
        await refreshDirectoryFiles(directory);
        setLoading(false);
        setName('check');
    }

    return <>
        <Button icon primary
                labelPosition='left'
                loading={loading}
                id='refresh_files'
                onClick={handleClick}>
            <Icon name={name}/>
            Refresh Directory
        </Button>
        <label htmlFor='refresh_files' {...t}>
            Find and index all files in the directory.
        </label>
    </>;
}

export function FilesRoute() {
    return (<PageContainer>
        <Routes>
            <Route path='/' exact element={<Files/>}/>
        </Routes>
    </PageContainer>);
}
