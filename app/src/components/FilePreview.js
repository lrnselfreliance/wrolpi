import React from "react";
import _ from "lodash";
import {Grid, Header as SHeader, Image,} from "semantic-ui-react";
import {TagsSelector} from "../Tags";
import {Media} from "../contexts/contexts";
import {encodeMediaPath} from "./Common";
import {getFile, tagFileGroup, untagFileGroup} from "../api";
import {StlViewer} from "react-stl-viewer";
import {Button, Modal, ModalActions, ModalContent, ModalHeader} from "./Theme";
import {toast} from "react-semantic-toasts-2";
import {useOneQuery} from "../hooks/customHooks";
import {ShareButton} from "./Share";

function getMediaPathURL(previewFile) {
    if (previewFile['primary_path']) {
        return `/media/${encodeMediaPath(previewFile['primary_path'])}`;
    } else {
        return `/media/${encodeMediaPath(previewFile['path'])}`;
    }
}

function getDownloadPathURL(previewFile) {
    if (previewFile['primary_path']) {
        return `/download/${encodeMediaPath(previewFile['primary_path'])}`;
    } else {
        return `/download/${encodeMediaPath(previewFile['path'])}`;
    }
}

function getEpubViewerURL(previewFile) {
    let url = previewFile['primary_path'] ?? previewFile['path'];
    return `/epub/epub.html?url=/media/${encodeMediaPath(url)}`
}

function getIframePreviewModal(previewFile, url) {
    url = url || getMediaPathURL(previewFile);
    return <ModalContent>
        <div className='full-height'>
            <iframe title='textModal' src={url}
                    style={{
                        height: '100%', width: '100%', border: 'none', position: 'absolute', top: 0,
                        // Use white to avoid iframe displaying with dark-theme.
                        backgroundColor: '#ffffff',
                    }}/>
        </div>
    </ModalContent>
}

function getImagePreviewModal(previewFile) {
    const path = previewFile.primary_path ?? previewFile.path;
    const url = getMediaPathURL(previewFile);
    // Get the file name from the absolute path.
    const name = path.replace(/^.*[\\\/]/, '');
    return <React.Fragment>
        <ModalHeader>
            {name}
        </ModalHeader>
        <ModalContent>
            <a href={url}>
                <Image src={url}/>
            </a>
        </ModalContent>
    </React.Fragment>
}

function getVideoPreviewModal(previewFile) {
    const url = getMediaPathURL(previewFile);
    const path = previewFile.primary_path ?? previewFile.path;
    const name = path.replace(/^.*[\\\/]/, '');
    return <React.Fragment>
        <ModalHeader>
            {name}
        </ModalHeader>
        <ModalContent>
            <SHeader as='h5'>{path['path']}</SHeader>
            <video controls
                   autoPlay={true}
                   id="player"
                   playsInline={true}
                   style={{maxWidth: '100%'}}
            >
                <source src={url}/>
            </video>
        </ModalContent>
    </React.Fragment>
}

function getAudioPreviewModal(previewFile) {
    const url = getMediaPathURL(previewFile);
    const path = previewFile.primary_path ?? previewFile.path;
    const name = path.replace(/^.*[\\\/]/, '');
    // Some audio files may not have the correct mimetype.  Trust the suffix identifies an audio file.
    const type = previewFile['mimetype'] !== 'application/octet-stream' ? previewFile['mimetype'] : 'audio/mpeg';
    return <React.Fragment>
        <ModalHeader>
            {name}
        </ModalHeader>
        <ModalContent>
            <audio controls
                   autoPlay={true}
                   id="player"
                   playsInline={true}
                   style={{width: '90%', maxWidth: '95%'}}
            >
                <source src={url} type={type}/>
            </audio>
        </ModalContent>
    </React.Fragment>
}

function getSTLPreviewModal(previewFile) {
    const url = getMediaPathURL(previewFile);
    const path = previewFile.primary_path ?? previewFile.path;
    const name = path.replace(/^.*[\\\/]/, '');
    return <React.Fragment>
        <ModalHeader>{name}</ModalHeader>
        <ModalContent>
            <StlViewer orbitControls shadows
                       url={url}
                       style={{height: '80vw', width: '80vw'}}
                       modelProps={{color: '#7353a8'}}
            />
        </ModalContent>
    </React.Fragment>
}

function getGenericPreviewModal(previewFile) {
    // No special handler for this file type, just open it.
    const path = previewFile.primary_path ?? previewFile.path;
    const name = path.replace(/^.*[\\\/]/, '');

    return <React.Fragment>
        <ModalHeader>{name}</ModalHeader>
    </React.Fragment>
}

export const FilePreviewContext = React.createContext({
    previewFile: null,
    setPreviewFile: null,
    previewModal: null,
    setPreviewModal: null,
    setCallbacks: null,
});

const MAXIMUM_TEXT_SIZE = 5_000_000;

export function FilePreviewProvider({children}) {
    // Data about the file that is being previewed.
    const [previewFile, setPreviewFile] = React.useState(null);
    // A modal is only displayed once we have data about the file.
    const [previewModal, setPreviewModal] = React.useState(null);
    const [callbacks, setCallbacks] = React.useState(null);
    // The file path from the `preview` URL query.
    const [previewQuery, setPreviewQuery] = useOneQuery('preview');
    const [errorModalOpen, setErrorModalOpen] = React.useState(false);

    const handleErrorModalClose = () => {
        setPreviewQuery(null);
        setErrorModalOpen(false);
    }

    const errorModal = <Modal closeIcon
                              open={errorModalOpen}
                              onClose={handleErrorModalClose}
    >
        <ModalHeader>Unknown File</ModalHeader>
        <ModalContent>Cannot display preview, no such file exists: {previewQuery}</ModalContent>
        <ModalActions>
            <Button onClick={handleErrorModalClose}>Close</Button>
        </ModalActions>
    </Modal>

    React.useEffect(() => {
        if (!_.isEmpty(previewFile)) {
            // Change URL to match the file that is being previewed.
            setPreviewQuery(previewFile['primary_path'] || previewFile['path']);
        }
    }, [previewFile]);

    const initPreviewFile = async () => {
        // Get simple information about the file, preview the file.
        try {
            const file = await getFile(previewQuery);
            setPreviewFile(file);
        } catch (e) {
            console.error(e);
            setPreviewModal(errorModal);
            setErrorModalOpen(true);
        }
    }

    React.useEffect(() => {
        // Navigated to a page which has a file preview active, fetch the information about the file, then display it.
        if (previewQuery && !previewFile) {
            initPreviewFile();
        } else if (!previewQuery && (previewFile || previewModal)) {
            // User navigated back/forward and preview query is gone, close the preview.
            // Only close if there's actually a preview open (previewFile or previewModal exists).
            setPreviewFile(null);
            setPreviewModal(null);
        }
    }, [previewQuery]);

    const localFetchFile = async () => {
        // Get the file again with its Tags.
        const {path, primary_path} = previewFile;
        try {
            const file = await getFile(primary_path ?? path);
            setPreviewFile(file);
        } finally {
            await handleCallbacks();
        }
    };

    const handleClose = (e) => {
        if (e) {
            e.preventDefault();
        }
        setPreviewModal(null);
        setPreviewFile(null);
        setPreviewQuery(null);
    }

    const handleCallbacks = async () => {
        for (const callbacksKey in callbacks) {
            try {
                await callbacks[callbacksKey]();
            } catch (e) {
                console.error(e);
            }
        }
    }

    const localAddTag = async (name) => {
        await tagFileGroup(previewFile, name);
        await localFetchFile();
    }

    const localRemoveTag = async (name) => {
        await untagFileGroup(previewFile, name);
        await localFetchFile();
    }

    function setModalContent(content, url, downloadURL, path, taggable = true) {
        const openButton = url ? <Button color='blue' as='a' href={url}>Open</Button> : null;
        const closeButton = <Button onClick={handleClose}>Close</Button>;
        const tagsDisplay = taggable ?
            <TagsSelector selectedTagNames={previewFile['tags']} onAdd={localAddTag}
                          onRemove={localRemoveTag}/>
            : null;
        const downloadButton = downloadURL ?
            <Button color='yellow' as='a' href={downloadURL} floated='left'>Download</Button>
            : null;
        const pathContent = path ? <ModalContent>
                <pre>{path}</pre>
            </ModalContent>
            : null;
        console.log('Previewing', path);
        console.log('Preview Download URL', downloadURL);
        console.log('Preview Open URL', url);

        setPreviewModal(<Modal closeIcon
                               size='fullscreen'
                               open={true}
                               onClose={e => handleClose(e)}
        >
            {content}
            {pathContent}
            <ModalActions>
                <Media at='mobile'>
                    <Grid>
                        <Grid.Row>
                            <Grid.Column width={6}>{downloadButton}</Grid.Column>
                            <Grid.Column width={5}>{openButton}</Grid.Column>
                            <Grid.Column width={5}>{closeButton}</Grid.Column>
                        </Grid.Row>
                        <Grid.Row>
                            <Grid.Column width={2} style={{paddingTop: '0.5em'}}><ShareButton/></Grid.Column>
                            <Grid.Column width={14}>{tagsDisplay}</Grid.Column>
                        </Grid.Row>
                    </Grid>
                </Media>
                <Media greaterThanOrEqual='tablet'>
                    <Grid>
                        <Grid.Row>
                            <Grid.Column width={2}>{downloadButton}</Grid.Column>
                            <Grid.Column width={1} style={{paddingTop: '0.5em'}}><ShareButton/></Grid.Column>
                            <Grid.Column width={9}>{tagsDisplay}</Grid.Column>
                            <Grid.Column width={2}>{openButton}</Grid.Column>
                            <Grid.Column width={2}>{closeButton}</Grid.Column>
                        </Grid.Row>
                    </Grid>
                </Media>
            </ModalActions>
        </Modal>);
    }

    React.useEffect(() => {
        setPreviewModal(null);
        if (previewFile && !_.isObject(previewFile)) {
            console.error(`Unknown previewFile type: ${typeof previewFile}`);
            toast({
                type: 'error',
                title: 'Cannot preview file',
                description: 'Cannot preview file',
                time: 5000,
            });
            return;
        }

        if (previewFile && !_.isEmpty(previewFile)) {
            const {mimetype, size, taggable} = previewFile;
            const path = previewFile['primary_path'] || previewFile['path'];
            console.debug('Previewing file', previewFile);
            const lowerPath = path.toLowerCase();
            const url = getMediaPathURL(previewFile);
            const downloadURL = getDownloadPathURL(previewFile);

            if (mimetype.startsWith('text/') && size > MAXIMUM_TEXT_SIZE) {
                // Large text files should be downloaded.
                window.open(downloadURL);
            } else if (mimetype.startsWith('text/') || mimetype.startsWith('application/json')) {
                setModalContent(getIframePreviewModal(previewFile), url, downloadURL, path, taggable);
            } else if (mimetype.startsWith('video/')) {
                setModalContent(getVideoPreviewModal(previewFile), url, downloadURL, path, taggable);
            } else if (mimetype.startsWith('audio/')) {
                setModalContent(getAudioPreviewModal(previewFile), url, downloadURL, path, taggable);
            } else if (mimetype.startsWith('application/epub')) {
                const viewerURL = getEpubViewerURL(previewFile);
                setModalContent(getIframePreviewModal(previewFile, viewerURL), viewerURL, downloadURL, path, taggable);
            } else if (mimetype.startsWith('application/pdf')) {
                setModalContent(getIframePreviewModal(previewFile), url, downloadURL, path, taggable);
            } else if (mimetype.startsWith('image/')) {
                setModalContent(getImagePreviewModal(previewFile), url, null, path, taggable);
            } else if (mimetype.startsWith('model/stl')) {
                setModalContent(getSTLPreviewModal(previewFile), null, downloadURL, path, taggable);
            } else if (mimetype.startsWith('application/octet-stream') && lowerPath.endsWith('.mp3')) {
                setModalContent(getAudioPreviewModal(previewFile), url, downloadURL, path, taggable);
            } else if (mimetype.startsWith('application/octet-stream') && lowerPath.endsWith('.stl')) {
                setModalContent(getSTLPreviewModal(previewFile), null, downloadURL, path, taggable);
            } else {
                // No special handler for this file type, just open it.
                setModalContent(getGenericPreviewModal(previewFile), url, downloadURL, path, taggable);
            }

            // Fetch the file so `FileGroup.viewed` is set.
            try {
                getFile(path);
            } catch (e) {
                console.error(e);
                console.error('Failed to get file to set FileGroup.viewed');
            }
        }
    }, [previewFile]);

    const value = {previewFile, setPreviewFile, previewModal, setPreviewModal, setCallbacks};

    return <FilePreviewContext.Provider value={value}>
        {children}
        {previewModal}
        {errorModal}
    </FilePreviewContext.Provider>
}
