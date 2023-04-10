import {Button, Icon, Placeholder} from "./Theme";
import {Checkbox, Confirm, PlaceholderLine, TableCell, TableFooter, TableHeaderCell, TableRow} from "semantic-ui-react";
import {FileIcon, humanFileSize} from "./Common";
import React, {useEffect} from "react";
import {deleteFile} from "../api";
import _ from 'lodash';
import {SortableTable} from "./SortableTable";
import {useBrowseFiles} from "../hooks/customHooks";
import {DirectoryRefreshButton, FileRowTagIcon, FilesRefreshButton} from "./Files";
import {FilePreviewContext} from "./FilePreview";

function depthIndentation(path) {
    // Repeated spaces for every folder a path is in.
    const depth = (path.match(/\//g) || []).length;
    return '\xa0\xa0\xa0\xa0'.repeat(depth);
}

function Folder({folder, onFolderClick, sortData, selectedPath, onFileClick, onSelect}) {
    // Creates a single table row for a folder, or a row for itself and indented rows for its children.
    let {path, children, is_empty} = folder;
    const pathWithNoTrailingSlash = path.substring(0, path.length - 1);
    const name = path.substring(pathWithNoTrailingSlash.lastIndexOf('/') + 1);
    const f = <TableRow key={path}>
        <TableCell collapsing>
            <Checkbox checked={selectedPath === folder['path']} onChange={() => onSelect(folder['path'])}/>
        </TableCell>
        <TableCell onClick={() => onFolderClick(path)} className='file-path' colSpan={2} disabled={is_empty}>
            {depthIndentation(pathWithNoTrailingSlash)}
            {is_empty ? <Icon name='folder outline'/> : <Icon name='folder'/>}
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
                      selectedPath={selectedPath} onSelect={onSelect}/>];
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

function File({file, onFileClick, selectedPath, onSelect}) {
    const {path, size} = file;
    const name = path.substring(path.lastIndexOf('/') + 1);
    return <TableRow key={path}>
        <TableCell collapsing>
            <Checkbox checked={selectedPath === path} onChange={() => onSelect(path)}/>
        </TableCell>
        <TableCell onClick={() => onFileClick(file)} className='file-path'>
            {depthIndentation(path)}
            <FileRowTagIcon file={file}/>
            {/*null size to make icon the correct size*/}
            <FileIcon file={file} size={null}/>
            {name}
        </TableCell>
        <TableCell collapsing textAlign='right'>
            {humanFileSize(size)}
        </TableCell>
    </TableRow>
}

function Path({path, onFolderClick, onFileClick, sortData, selectedPath, onSelect}) {
    if (path['path'].endsWith('/')) {
        return <Folder
            folder={path}
            onFolderClick={onFolderClick}
            sortData={sortData}
            selectedPath={selectedPath}
            onSelect={onSelect}
            onFileClick={onFileClick}
        />
    } else {
        return <File
            file={path}
            onFileClick={onFileClick}
            selectedPath={selectedPath}
            onSelect={onSelect}
        />
    }
}

export function FileBrowser() {
    const [selectedPath, setSelectedPath] = React.useState(null);
    const [deleteOpen, setDeleteOpen] = React.useState(false);
    const [fileSelected, setFileSelected] = React.useState(false);
    const [folderSelected, setFolderSelected] = React.useState(false);

    const {browseFiles, openFolders, setOpenFolders, fetchFiles} = useBrowseFiles();

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

    const onSelect = (path) => {
        if (path.endsWith('/') && selectedPath === path) {
            // Deselect folder.
            setFileSelected(false);
            setFolderSelected(false);
            setSelectedPath(null);
        } else if (path.endsWith('/')) {
            // Select folder.
            setFileSelected(false);
            setFolderSelected(true);
            setSelectedPath(path);
        } else if (selectedPath === path) {
            // Deselect file.
            setFileSelected(false);
            setFolderSelected(false);
            setSelectedPath(null);
        } else {
            // Select file.
            setFileSelected(true);
            setFolderSelected(false);
            setSelectedPath(path);
        }
    }

    const onDelete = async () => {
        await deleteFile(selectedPath);
        setDeleteOpen(false);
        await fetchFiles();
    };

    const footer = <TableFooter fullWidth>
        <TableRow>
            <TableHeaderCell colSpan={3}>
                {folderSelected ? <DirectoryRefreshButton directory={selectedPath}/> : <FilesRefreshButton/>}
                <Button
                    color='red'
                    onClick={() => setDeleteOpen(true)}
                    disabled={!fileSelected}
                >
                    <Icon name='close'/>
                    Delete
                </Button>
                <Confirm
                    open={deleteOpen}
                    content='Are you sure you want to delete these files?'
                    onConfirm={onDelete}
                    onCancel={() => setDeleteOpen(false)}
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
                selectedPath={selectedPath}
                onSelect={onSelect}
            />}
            footer={footer}
        />
    </>
}
