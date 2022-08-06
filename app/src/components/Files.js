import React, {useContext} from "react";
import FileBrowser from 'react-keyed-file-browser';
import {
    Card,
    Checkbox,
    Confirm,
    Divider,
    Dropdown,
    Image, PlaceholderLine,
    TableBody,
    TableCell,
    TableHeader,
    TableHeaderCell,
    TableRow,
} from "semantic-ui-react";
import 'react-keyed-file-browser/dist/react-keyed-file-browser.css';
import {deleteFile, refreshDirectoryFiles, refreshFiles} from "../api";
import {
    ArchiveRow,
    CardGroupCentered,
    ExternalCardLink,
    FileIcon,
    humanFileSize,
    mimetypeColor,
    PageContainer,
    Paginator,
    textEllipsis,
    uploadDate,
    VideoCard,
    VideoRow
} from "./Common";
import {useBrowseFiles, useQuery, useSearchFiles} from "../hooks/customHooks";
import {Route, Routes} from "react-router-dom";
import {CardPlacholder} from "./Placeholder";
import {ArchiveCard} from "./Archive";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {ThemeContext} from "../contexts/contexts";
import {Button, Icon, Placeholder, Segment, Table} from "./Theme";

const icons = {
    File: <Icon name='file'/>,
    Folder: <Icon name='folder'/>,
    FolderOpen: <Icon name='folder open'/>,
    Image: <Icon name='file image'/>,
    PDF: <Icon name='file pdf'/>,
};

export function Files() {
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
            <ExternalCardLink to={`/media/${selectedFile.key}`}>
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

function ImageCard({file}) {
    const {s} = useContext(ThemeContext);
    const url = `/media/${encodeURIComponent(file.path)}`;

    let poster = <center className='card-icon'><FileIcon file={file}/></center>;
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
        <Card.Content {...s}>
            <Card.Header>
                <ExternalCardLink to={url} className='no-link-underscore card-link'>
                    <p>{textEllipsis(file.title || file.stem || file.path, 100)}</p>
                </ExternalCardLink>
            </Card.Header>
            <Card.Meta {...s}>
                <p>{uploadDate(file.modified / 1000)}</p>
            </Card.Meta>
            <Card.Description {...s}>
                <p>{humanFileSize(file.size)}</p>
            </Card.Description>
        </Card.Content>
    </Card>
}

function FileCard({file}) {
    const {s} = useContext(ThemeContext);

    if (file.model === 'video' && file['video']) {
        return <VideoCard key={file['path']} file={file}/>;
    } else if (file.model === 'archive' && file['archive']) {
        return <ArchiveCard key={file['path']} file={file}/>;
    } else if (file.mimetype && file.mimetype.startsWith('image/')) {
        return <ImageCard key={file['path']} file={file}/>;
    }

    const url = `/media/${encodeURIComponent(file.path)}`;
    const color = mimetypeColor(file.mimetype);

    return <Card color={color}>
        <ExternalCardLink to={url}>
            <center className='card-icon'>
                <FileIcon file={file}/>
            </center>
        </ExternalCardLink>
        <Card.Content {...s}>
            <Card.Header>
                <ExternalCardLink to={url}>
                    {textEllipsis(file.title || file.stem || file.path)}
                </ExternalCardLink>
            </Card.Header>
        </Card.Content>
    </Card>
}

export function FileCards({files}) {
    if (files && files.length > 0) {
        return <CardGroupCentered>
            {files.map((i) => <FileCard key={i['path']} file={i}/>)}
        </CardGroupCentered>
    } else if (files && files.length === 0) {
        return <p>No files found.</p>
    } else {
        return <CardGroupCentered><CardPlacholder/></CardGroupCentered>
    }
}

function ImageRow({file, checkbox}) {
    const url = `/media/${encodeURIComponent(file.path)}`;

    let poster = <FileIcon file={file} size='large'/>;
    if (file.size && file.size < 50000000) {
        // Image is less than 5mb, use it.
        poster = <Image wrapped src={url} width='50px'/>;
    }

    return (
        <Table.Row>
            {checkbox}
            <Table.Cell>
                <center>
                    {poster}
                </center>
            </Table.Cell>
            <Table.Cell>
                <ExternalCardLink to={url}>
                    <p>{textEllipsis(file.title || file.stem || file.path, 100)}</p>
                </ExternalCardLink>
            </Table.Cell>
        </Table.Row>
    )
}

function FileRow({file, selectOn, onSelect}) {
    let checkbox;
    if (selectOn) {
        const localOnSelect = (e, {checked}) => {
            try {
                onSelect(file.key, checked);
            } catch (e) {
                console.error('No onSelect declared');
            }
        };
        checkbox = <Table.Cell>
            <Checkbox onChange={localOnSelect}/>
        </Table.Cell>
    }

    if (file.model === 'video' && 'video' in file) {
        return <VideoRow key={file['path']} file={file} checkbox={checkbox}/>;
    } else if (file.model === 'archive' && 'archive' in file) {
        return <ArchiveRow key={file['path']} file={file} checkbox={checkbox}/>;
    } else if (file.mimetype && file.mimetype.startsWith('image/')) {
        return <ImageRow key={file['path']} file={file} checkbox={checkbox}/>;
    }

    const onDownloadFile = async () => window.open(`/media/${file.key}`);

    return <TableRow>
        {checkbox}
        <TableCell>
            <center><FileIcon file={file} size='large'/></center>
        </TableCell>
        <TableCell onClick={() => onDownloadFile()}>
            {textEllipsis(file.title)}
        </TableCell>
    </TableRow>
}

export function FileTable({files, selectOn, onSelect}) {
    if (files && files.length > 0) {
        return (
            <Table unstackable striped compact='very'>
                <TableHeader>
                    <TableRow>
                        {selectOn && <TableHeaderCell/>}
                        <TableHeaderCell>Poster</TableHeaderCell>
                        <TableHeaderCell>Title</TableHeaderCell>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {files.map(i => <FileRow key={i['path']} file={i} selectOn={selectOn} onSelect={onSelect}/>)}
                </TableBody>
            </Table>
        )
    } else if (files && files.length === 0) {
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
        body = <FileTable files={files} selectOn={selectOn} onSelect={onSelect}/>;
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
                                    mimetype,
                                    model,
                                    onSelect,
                                    setFilters,
                                }) {
    const {searchFiles, limit, setLimit, totalPages, activePage, setPage} =
        useSearchFiles(24, emptySearch, mimetype, model);

    const {searchParams, updateQuery} = useQuery();
    const setView = (value) => updateQuery({view: value});
    const view = searchParams.get('view');

    const setMimetype = (value) => updateQuery({'mimetype': value});
    filterOptions = filterOptions || [
        {key: 'video', text: 'Video', value: 'video'},
        {key: 'archive', text: 'Archive', value: 'text/html'},
        {key: 'pdf', text: 'PDF', value: 'application/pdf'},
        {key: 'zip', text: 'ZIP', value: 'application/zip'},
        {key: 'image', text: 'Image', value: 'image'},
    ];

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
        setFilters={setFilters || setMimetype}
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
