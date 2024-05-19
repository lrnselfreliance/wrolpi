import {Button, Header, Icon, Modal, ModalActions, ModalContent, ModalHeader, Placeholder, Table} from "./Theme";
import {
    Checkbox,
    Form,
    IconGroup,
    Input,
    PlaceholderLine,
    TableBody,
    TableCell,
    TableFooter,
    TableHeader,
    TableHeaderCell,
    TableRow
} from "semantic-ui-react";
import {APIButton, DirectorySearch, ErrorMessage, FileIcon, humanFileSize, useIsIgnoredDirectory} from "./Common";
import React, {useEffect, useState} from "react";
import {deleteFile, ignoreDirectory, makeDirectory, movePaths, renamePath, unignoreDirectory} from "../api";
import _ from 'lodash';
import {SortableTable} from "./SortableTable";
import {useBrowseFiles, useMediaDirectory, useWROLMode} from "../hooks/customHooks";
import {FileRowTagIcon, FilesRefreshButton} from "./Files";
import {FilePreviewContext} from "./FilePreview";
import {SettingsContext} from "../contexts/contexts";

function depthIndentation(path) {
    // Repeated spaces for every folder a path is in.
    const depth = (path.match(/\//g) || []).length;
    return '\xa0\xa0\xa0\xa0'.repeat(depth);
}

export function pathDirectory(path) {
    // Return the full path of the path's directory.
    // pathDirectory('/some/directory/file.txt') -> '/some/directory'
    return path.substring(0, path.lastIndexOf('/'));
}

export function pathName(path) {
    // Return the file's name.
    // pathName('/some/directory/file.txt') -> 'file.txt'
    // pathName('/some/directory') -> 'directory'
    if (path.endsWith('/')) {
        // Path is a directory, return its name.
        path = path.substring(0, path.length - 1);
    }
    return path.substring(path.lastIndexOf('/') + 1);
}

export function splitPathParentAndName(path) {
    if (path.endsWith('/')) {
        // Path is a directory, return its name.
        path = path.substring(0, path.length - 1);
    }
    const slashIndex = path.lastIndexOf('/');
    return [path.substring(0, slashIndex), path.substring(slashIndex + 1, path.length)];
}

function Folder({folder, onFolderClick, sortData, selectedPaths, onFileClick, onSelect, disabled}) {
    // Creates a single table row for a folder, or a row for itself and indented rows for its children.
    let {path, children, is_empty} = folder;
    const ignored = useIsIgnoredDirectory(path);
    const pathWithNoTrailingSlash = path.substring(0, path.length - 1);
    const name = path.substring(pathWithNoTrailingSlash.lastIndexOf('/') + 1);
    const f = <TableRow key={path} disabled={disabled}>
        <TableCell collapsing>
            <Checkbox checked={selectedPaths.indexOf(folder['path']) >= 0} onChange={() => onSelect(folder['path'])}/>
        </TableCell>
        <TableCell onClick={() => onFolderClick(path)} className='file-path' colSpan={2} disabled={is_empty}>
            {depthIndentation(pathWithNoTrailingSlash)}
            {is_empty ? <Icon name='folder outline'/> : <Icon name='folder'/>}
            {ignored && <Icon name='eye slash' color='red'/>}
            {name}
        </TableCell>
    </TableRow>;
    if (children) {
        // Folder has children, recursively display them.
        children = sortData(children);
        let childPaths = [];
        _.forEach(children, (p, k) => {
            childPaths = [...childPaths,
                <Path key={k} path={p} onFolderClick={onFolderClick} sortData={sortData} onFileClick={onFileClick}
                      selectedPaths={selectedPaths} onSelect={onSelect} disabled={disabled}/>];
        });
        return <React.Fragment>
            {f}
            {childPaths}
        </React.Fragment>
    } else {
        // Folder has no children.
        return f;
    }
}

function File({file, onFileClick, selectedPaths, onSelect, disabled}) {
    const {path, size} = file;
    return <TableRow key={path} disabled={disabled}>
        <TableCell collapsing>
            <Checkbox checked={selectedPaths.indexOf(path) >= 0} onChange={() => onSelect(path)}/>
        </TableCell>
        <TableCell onClick={() => onFileClick(file)} className='file-path'>
            {depthIndentation(path)}
            <FileRowTagIcon file={file}/>
            {/*null size to make icon the correct size*/}
            <FileIcon file={file} size={null}/>
            {pathName(path)}
        </TableCell>
        <TableCell collapsing textAlign='right'>
            {humanFileSize(size)}
        </TableCell>
    </TableRow>
}

function Path({path, onFolderClick, onFileClick, sortData, selectedPaths, onSelect, disabled}) {
    if (path['path'].endsWith('/')) {
        return <Folder
            folder={path}
            onFolderClick={onFolderClick}
            sortData={sortData}
            selectedPaths={selectedPaths}
            onSelect={onSelect}
            onFileClick={onFileClick}
            disabled={disabled}
        />
    } else {
        return <File
            file={path}
            onFileClick={onFileClick}
            selectedPaths={selectedPaths}
            onSelect={onSelect}
            disabled={disabled}
        />
    }
}

export function FileBrowser() {
    const [selectedPaths, setSelectedPaths] = React.useState([]);
    const [renameOpen, setRenameOpen] = React.useState(false);
    const [moveOpen, setMoveOpen] = React.useState(false);
    const [makeDirectoryOpen, setMakeDirectoryOpen] = React.useState(false);
    const [ignoreDirectoryOpen, setIgnoreDirectoryOpen] = React.useState(false);
    const [pending, setPending] = React.useState(false);
    // Only true if only one path is selected, and it is a directory.
    const [singleDirectorySelected, setSingleDirectorySelected] = React.useState(false);
    // Only true if single directory is selected, and it is in settings['ignored_directories']
    const [isDirectoryIgnored, setIsDirectoryIgnored] = React.useState(false);

    const {settings, fetchSettings} = React.useContext(SettingsContext);

    const selectedPathsCount = selectedPaths ? selectedPaths.length : 0;

    const {browseFiles, openFolders, setOpenFolders, fetchFiles} = useBrowseFiles();
    const wrolModeEnabled = useWROLMode();

    const headers = [
        {key: 'select', text: ''},
        {key: 'path', text: 'Path', sortBy: i => i['path'].toLowerCase()},
        {key: 'size', text: 'Size', sortBy: 'size'},
    ];

    const {setPreviewFile, setCallbacks} = React.useContext(FilePreviewContext);

    useEffect(() => {
        // Fetch files after tagging.
        setCallbacks([() => fetchFiles(openFolders)]);

        return () => setCallbacks(null);
    }, []);

    useEffect(() => {
        if (selectedPaths.length === 1 && selectedPaths[0].endsWith('/')) {
            setSingleDirectorySelected(true);
            if (!_.isEmpty(settings)) {
                // Used to toggle between ignore/un-ignore (eye/eye lash) icon.
                const directory = selectedPaths[0].slice(0, -1);
                setIsDirectoryIgnored(settings['ignored_directories'].indexOf(directory) >= 0);
            }
        } else {
            setSingleDirectorySelected(false);
        }
    }, [selectedPaths, settings]);

    const onIgnore = async () => {
        setIgnoreDirectoryOpen(false);
        await fetchSettings();
    }

    const onSelect = (path) => {
        let newSelectedPaths;
        // Select or deselect if the paths was previously selected.
        if (selectedPathsCount && selectedPaths.indexOf(path) >= 0) {
            newSelectedPaths = selectedPaths.filter(i => i !== path);
        } else {
            newSelectedPaths = [...selectedPaths, path];
        }
        setSelectedPaths(newSelectedPaths);
        console.debug('selectedPaths', newSelectedPaths);
    }

    const onDelete = async () => {
        await deleteFile(selectedPaths);
        await reset();
    };

    const handleMakeDirectory = async () => {
        setMakeDirectoryOpen(false);
        await reset();
    }

    const reset = async () => {
        setSelectedPaths([]);
        setPending(true);
        try {
            await fetchFiles();
        } finally {
            setPending(false);
        }
    }

    const footer = <TableFooter fullWidth>
        <TableRow>
            <TableHeaderCell colSpan={3}>
                <FilesRefreshButton paths={selectedPaths}/>
                <APIButton
                    icon='trash'
                    color='red'
                    confirmContent='Are you sure you want to delete these files?'
                    confirmButton='Delete'
                    onClick={onDelete}
                    disabled={selectedPathsCount === 0}
                    obeyWROLMode={true}
                />
                <Button icon='text cursor'
                        color='yellow'
                        onClick={() => setRenameOpen(true)}
                        disabled={wrolModeEnabled || selectedPathsCount !== 1}
                />
                {selectedPathsCount === 1 ?
                    <RenameModal
                        open={renameOpen}
                        onClose={() => setRenameOpen(false)}
                        onPending={setPending}
                        path={selectedPaths[0]}
                        onSubmit={reset}
                    /> : null}
                <Button icon='move'
                        color='violet'
                        disabled={wrolModeEnabled || selectedPathsCount === 0}
                        onClick={() => setMoveOpen(true)}
                />
                {selectedPathsCount > 0 ?
                    <MoveModal open={moveOpen}
                               onClose={() => setMoveOpen(false)}
                               paths={selectedPaths}
                               onSubmit={reset}
                    /> : null}
                <Button
                    color='blue'
                    onClick={() => setMakeDirectoryOpen(true)}
                    disabled={wrolModeEnabled}
                    style={{paddingLeft: '1em', paddingRight: '0.8em'}}
                >
                    <IconGroup>
                        <Icon name='folder'/>
                        <Icon corner name='add'/>
                    </IconGroup>
                </Button>
                <MakeDirectoryModal
                    open={makeDirectoryOpen}
                    onClose={() => setMakeDirectoryOpen(false)}
                    parent={selectedPaths.length ? selectedPaths[0] : null}
                    onSubmit={handleMakeDirectory}
                />
                <Button
                    color='grey'
                    icon={isDirectoryIgnored ? 'eye' : 'eye slash'}
                    disabled={!singleDirectorySelected || wrolModeEnabled}
                    onClick={() => setIgnoreDirectoryOpen(true)}
                />
                <IgnoreDirectoryModal
                    open={ignoreDirectoryOpen}
                    onClose={onIgnore}
                    onSubmit={onIgnore}
                    directory={selectedPaths.length === 1 ? selectedPaths[0] : null}
                    ignored={isDirectoryIgnored}
                />
            </TableHeaderCell>
        </TableRow>
    </TableFooter>;

    const onFolderClick = async (folder) => {
        let newFolders;
        if (openFolders.indexOf(folder) >= 0) {
            // Remove the folder that was clicked on, as well as its sub-folders.
            newFolders = openFolders.filter(i => !i.startsWith(folder));
        } else {
            // Add the new folder to the opened folders.
            newFolders = [...openFolders, folder];
        }
        console.debug(`newFolders=${newFolders}`);
        setOpenFolders(newFolders);
    }

    if (browseFiles === null) {
        return <Placeholder>
            <PlaceholderLine/>
            <PlaceholderLine/>
        </Placeholder>;
    } else if (browseFiles === undefined) {
        return <ErrorMessage>Could not fetch files</ErrorMessage>
    }

    return <>
        <SortableTable
            tableProps={{unstackable: true}}
            data={browseFiles}
            tableHeaders={headers}
            defaultSortColumn='path'
            rowKey='path'
            rowFunc={(i, sortData) => <Path
                key={i['key']}
                path={i}
                onFolderClick={onFolderClick}
                onFileClick={(i) => setPreviewFile(i)}
                sortData={sortData}
                selectedPaths={selectedPaths}
                onSelect={onSelect}
                disabled={pending}
            />}
            footer={footer}
        />
    </>
}

export function RenameModal({open, onClose, path, onSubmit, onPending}) {
    const [parent, name] = splitPathParentAndName(path);
    const [value, setValue] = React.useState(name);
    const disabled = value === name;

    const handleInputChange = (e, props) => {
        if (e) {
            e.preventDefault();
        }
        setValue(props.value);
    }

    const handleSubmit = async (e) => {
        if (e) {
            e.preventDefault();
        }
        try {
            console.log(`Renaming: ${path} to ${value}`);
            onPending(true);
            await renamePath(path, value);
        } finally {
            onClose();
            onPending(false);
            if (onSubmit) {
                await onSubmit();
            }
        }
    }

    useEffect(() => {
        setValue(pathName(path));
    }, [path]);

    return <Modal closeIcon
                  open={open}
                  onClose={onClose}
    >
        <ModalHeader>Rename: {name}</ModalHeader>
        <ModalContent>
            <Form onSubmit={handleSubmit}>
                <Header as='h4'>New Name</Header>
                <pre>{parent ? parent + '/' : null}{value}</pre>

                <Input fluid
                       label='Name'
                       value={value}
                       onChange={handleInputChange}
                />
            </Form>
        </ModalContent>
        <ModalActions>
            <Button
                color='violet'
                disabled={disabled}
                onClick={handleSubmit}
            >
                Rename
            </Button>
            <Button
                onClick={() => setValue(name)}
                floated='left'
            >
                Reset
            </Button>
        </ModalActions>
    </Modal>
}

export function MoveModal({open, paths, onClose, onSubmit}) {
    const [destination, setDestination] = React.useState('');
    const [pending, setPending] = React.useState(false);

    const handleDirectory = (value) => {
        setDestination(value);
    }

    const handleMove = async () => {
        try {
            setPending(true);
            await movePaths(destination, paths);
            onClose();
        } catch (e) {
            console.error(e);
            setPending(false);
        }
        if (onSubmit) {
            await onSubmit();
        }
    }

    const fileCell = i => <TableCell>
        <pre style={{marginTop: 0, marginBottom: 0}}>{i}</pre>
    </TableCell>;

    const destinationRows = paths.map(i => <TableRow key={i}>
        {fileCell(i)}
        {destination ? fileCell(destination + '/' + pathName(i)) : fileCell(pathName(i))}
    </TableRow>);

    return <Modal closeIcon
                  onClose={onClose}
                  open={open}
    >
        <ModalHeader>Move Files/Directories</ModalHeader>
        <ModalContent>
            <p>Search for a directory to move your files into:</p>
            <DirectorySearch onSelect={handleDirectory} disabled={pending}/>

            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHeaderCell>Source</TableHeaderCell>
                        <TableHeaderCell>Destination</TableHeaderCell>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {destinationRows}
                </TableBody>
            </Table>
        </ModalContent>
        <ModalActions>
            <Button
                color='violet'
                onClick={handleMove}
                disabled={pending}
            >Move</Button>
            <Button
                onClick={() => setDestination(null)}
                floated='left'
                disabled={pending}
            >Reset</Button>
        </ModalActions>
    </Modal>
}

export function IgnoreDirectoryModal({open, onClose, onSubmit, directory, ignored}) {
    const mediaDirectory = useMediaDirectory();
    const [pending, setPending] = React.useState(false);

    const handleIgnore = async () => {
        try {
            setPending(true);
            if (ignored) {
                await unignoreDirectory(`${mediaDirectory}/${directory}`);
            } else {
                await ignoreDirectory(`${mediaDirectory}/${directory}`);
            }
            if (onSubmit) {
                onSubmit();
            }
        } finally {
            setPending(false);
        }
    }

    const header = ignored ? 'Remove Ignore Directory' : 'Ignore Directory';
    const content = ignored ?
        'Remove ignore of the following directory?  You must refresh your files after this.'
        : 'Ignore the following directory? The files within will not be indexed and will not show in search results.';
    let submitButton = <Button primary
                               disabled={pending}
                               onClick={handleIgnore}
    >{ignored ? 'Un-ignore' : 'Ignore'}</Button>;

    return <Modal closeIcon open={open} onClose={onClose}>
        <ModalHeader>{header}</ModalHeader>
        <ModalContent>
            {content}
            <pre>{mediaDirectory}/{directory}</pre>
        </ModalContent>
        <ModalActions>
            {submitButton}
            <Button secondary floated='left' onClick={onClose}>Close</Button>
        </ModalActions>
    </Modal>
}

export function MakeDirectoryModal({open, onClose, parent, onSubmit}) {
    const [value, setValue] = useState('');
    const mediaDirectory = useMediaDirectory();

    const handleInputChange = (e, props) => {
        if (e) {
            e.preventDefault();
        }
        setValue(props.value);
    }

    const handleSubmit = async (e) => {
        if (e) {
            e.preventDefault();
        }
        try {
            const path = parent ? `${parent}/${value}` : value;
            await makeDirectory(path);
            setValue('');
            if (onSubmit) {
                await onSubmit();
            }
        } catch (e) {
            console.error(e);
        }
    }

    return <Modal closeIcon open={open} onClose={onClose}>
        <ModalHeader>Make Directory</ModalHeader>
        <ModalContent>
            <Form onSubmit={handleSubmit}>
                <pre>{mediaDirectory}/{parent}{value}</pre>
                <Input fluid
                       label='Name'
                       value={value}
                       onChange={handleInputChange}
                />
            </Form>
        </ModalContent>
        <ModalActions>
            <Button color='violet' onClick={handleSubmit}>Create</Button>
        </ModalActions>
    </Modal>
}