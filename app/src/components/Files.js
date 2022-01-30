import React from "react";
import FileBrowser from 'react-keyed-file-browser';
import {Button, Confirm, Header, Icon, Modal} from "semantic-ui-react";
import 'react-keyed-file-browser/dist/react-keyed-file-browser.css';
import {deleteFile, getFiles} from "../api";
import {humanFileSize, secondsToDateTime} from "./Common";

const icons = {
    File: <Icon name='file'/>,
    Folder: <Icon name='folder'/>,
    FolderOpen: <Icon name='folder open'/>,
    Image: <Icon name='file image'/>,
    PDF: <Icon name='file pdf'/>,
};

class Files extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            deleteOpen: false,
            files: [],
            openFolders: [],
            previewOpen: false,
            selectedFile: null,
        };
    }

    async componentDidMount() {
        await this.fetchFiles();
    }

    fetchFiles = async () => {
        let {files} = await getFiles(this.state.openFolders);
        for (let i = 0; i < files.length; i++) {
            files[i]['modified'] = secondsToDateTime(files[i]['modified']);
        }
        this.setState({files: files});
    }

    handleFolderChange = async (file, browserProps) => {
        let openFolders = Object.keys(browserProps.openFolders);
        this.setState({openFolders}, this.fetchFiles);
    }

    onDownloadFile = async () => {
        // Open file in new tab/window.
        window.open(`/media/${this.state.selectedFile.key}`);
    }

    onSelectFile = async (file) => {
        this.setState({selectedFile: file}, this.openPreview);
    }

    onDeleteFile = async () => {
        await deleteFile(this.state.selectedFile.key);
        await this.fetchFiles();
        this.closePreview();
    }

    openPreview = () => {
        this.setState({previewOpen: true});
    }

    closePreview = () => {
        this.setState({previewOpen: false, selectedFile: null, deleteOpen: false});
    }

    openDelete = () => {
        this.setState({deleteOpen: true});
    }

    closeDelete = () => {
        this.setState({deleteOpen: false});
    }

    render() {
        return <>
            {this.state.selectedFile &&
                <Modal closeIcon
                       open={this.state.previewOpen}
                       onClose={this.closePreview}
                >
                    <Modal.Header><Icon name='file'/>File Preview</Modal.Header>
                    <Modal.Content>
                        <Header>{this.state.selectedFile.name}</Header>
                        <p>{humanFileSize(this.state.selectedFile.size)}</p>
                    </Modal.Content>
                    <Modal.Actions>
                        <Button color='red' onClick={this.openDelete} floated='left'>Delete</Button>
                        <Confirm
                            open={this.state.deleteOpen}
                            content={`Are you sure you want to delete ${this.state.selectedFile.key}`}
                            onCancel={this.closeDelete}
                            onConfirm={this.onDeleteFile}
                        />
                        <Button color='green' onClick={this.onDownloadFile}>Download</Button>
                    </Modal.Actions>
                </Modal>}
            <FileBrowser
                showActionBar={false}
                canFilter={false}
                files={this.state.files}
                icons={icons}
                onFolderOpen={this.handleFolderChange}
                onFolderClose={this.handleFolderChange}
                onSelectFile={this.onSelectFile}
                detailRenderer={() => <></>} // Hide the preview that the 3rd party provided.
            />
        </>
    }
}

export function FilesRoute(props) {
    return (
        <Files/>
    );
}
