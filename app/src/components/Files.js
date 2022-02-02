import React from "react";
import FileBrowser from 'react-keyed-file-browser';
import {Button, Confirm, Header, Icon, Modal} from "semantic-ui-react";
import 'react-keyed-file-browser/dist/react-keyed-file-browser.css';
import {deleteFile, refreshFiles} from "../api";
import {Paginator, humanFileSize, PageContainer, SearchInput, TabLinks} from "./Common";
import {useBrowseFiles, useSearchFiles} from "../hooks/customHooks";
import {Route} from "react-router-dom";

const icons = {
    File: <Icon name='file'/>,
    Folder: <Icon name='folder'/>,
    FolderOpen: <Icon name='folder open'/>,
    Image: <Icon name='file image'/>,
    PDF: <Icon name='file pdf'/>,
};

export function Files(props) {
    const {searchFiles, setPage, totalPages, activePage, searchStr, setSearchStr} = useSearchFiles(50);
    const {browseFiles, setOpenFolders, fetchFiles} = useBrowseFiles();

    const [deleteOpen, setDeleteOpen] = React.useState(false);
    const [previewOpen, setPreviewOpen] = React.useState(false);
    const [selectedFile, setSelectedFile] = React.useState(null);

    const handleFolderChange = async (file, browserProps) => {
        let openFolders = Object.keys(browserProps.openFolders);
        setOpenFolders(openFolders);
    }

    const onDownloadFile = async () => {
        // Open file in new tab/window.
        window.open(`/media/${selectedFile.key}`);
    }

    const onSelectFile = async (file) => {
        setSelectedFile(file);
        openPreview();
    }

    const onDeleteFile = async () => {
        await deleteFile(selectedFile.key);
        await fetchFiles();
        closePreview();
    }

    const openPreview = () => {
        setPreviewOpen(true);
    }

    const closePreview = () => {
        setPreviewOpen(false);
        setSelectedFile(null);
        setDeleteOpen(false);
    }

    const openDelete = () => {
        setDeleteOpen(true);
    }

    const closeDelete = () => {
        setDeleteOpen(false);
    }

    let selectedModal = <></>;
    if (selectedFile) {
        selectedModal = (
            <Modal closeIcon
                   open={previewOpen}
                   onClose={closePreview}
            >
                <Modal.Header><Icon name='file'/>File Preview</Modal.Header>
                <Modal.Content>
                    <Header>{selectedFile.name}</Header>
                    <p>{humanFileSize(selectedFile.size)}</p>
                </Modal.Content>
                <Modal.Actions>
                    <Button color='red' onClick={openDelete} floated='left'>Delete</Button>
                    <Confirm
                        open={deleteOpen}
                        content={`Are you sure you want to delete ${selectedFile.key}`}
                        onCancel={closeDelete}
                        onConfirm={onDeleteFile}
                    />
                    <Button color='green' onClick={onDownloadFile}>Download</Button>
                </Modal.Actions>
            </Modal>);
    }

    let browser;
    let pagination = null;
    if (searchStr) {
        browser = (<FileBrowser
            showActionBar={false}
            canFilter={false}
            files={searchFiles}
            icons={icons}
            onSelectFile={onSelectFile}
            detailRenderer={() => <></>} // Hide the preview that the 3rd party provided.
        />);
        pagination = (
            <div style={{marginTop: '3em', textAlign: 'center'}}>
                <Paginator
                    activePage={activePage}
                    changePage={setPage}
                    totalPages={totalPages}
                />
            </div>);
    } else {
        browser = (<FileBrowser
            showActionBar={false}
            canFilter={false}
            files={browseFiles}
            icons={icons}
            onFolderOpen={handleFolderChange}
            onFolderClose={handleFolderChange}
            onSelectFile={onSelectFile}
            detailRenderer={() => <></>} // Hide the preview that the 3rd party provided.
        />);
    }

    return <>
        <SearchInput initValue={searchStr} onSubmit={setSearchStr}/>
        {selectedModal}
        {browser}
        {pagination}
    </>
}

function ManageFiles(props) {
    return (<>
        <Button secondary
                id='refresh_files'
                onClick={refreshFiles}>
            Refresh Files
        </Button>
        <label htmlFor='refresh_files'>
            Find and index any new files.
        </label>
    </>)
}

export function FilesRoute(props) {
    const links = [
        {text: 'Files', to: '/files', exact: true, key: 'files'},
        {text: 'Manage', to: '/files/manage', exact: true, key: 'manage'},
    ];

    return (
        <PageContainer>
            <TabLinks links={links}/>
            <Route path='/files' exact component={Files}/>
            <Route path='/files/manage' exact component={ManageFiles}/>
        </PageContainer>
    );
}
