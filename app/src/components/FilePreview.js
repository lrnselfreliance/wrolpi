import React from "react";
import _ from "lodash";
import {
    Button as SButton,
    Grid,
    Header as SHeader,
    Image,
    Modal,
    ModalActions,
    ModalContent,
    ModalHeader
} from "semantic-ui-react";
import {TagsProvider, TagsSelector} from "../Tags";
import {Media} from "../contexts/contexts";
import {encodeMediaPath} from "./Common";
import {addTag, fetchFile, removeTag} from "../api";
import {StlViewer} from "react-stl-viewer";

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
    if (previewFile['primary_path']) {
        return `/epub.html?url=download/${encodeMediaPath(previewFile['primary_path'])}`;
    } else {
        return `/epub.html?url=download/${encodeMediaPath(previewFile['path'])}`;
    }
}

function getIframeModal(previewFile) {
    const url = getMediaPathURL(previewFile);
    return <ModalContent>
        <div className='full-height'>
            <iframe title='textModal' src={url}
                    style={{
                        height: '100%', width: '100%', border: 'none', position: 'absolute', top: 0,
                    }}/>
        </div>
    </ModalContent>
}

function getImageModal(previewFile) {
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

function getEpubModal(previewFile) {
    const downloadURL = getDownloadPathURL(previewFile);
    const viewerUrl = `/epub.html?url=${downloadURL}`;
    return <ModalContent>
        <div className='full-height'>
            <iframe title='textModal' src={viewerUrl}
                    style={{
                        height: '100%', width: '100%', border: 'none', position: 'absolute', top: 0,
                    }}/>
        </div>
    </ModalContent>
}

function getVideoModal(previewFile) {
    const url = getMediaPathURL(previewFile);
    const path = previewFile.primary_path ?? previewFile.path;
    const name = path.replace(/^.*[\\\/]/, '');
    const type = previewFile.mimetype ? previewFile.mimetype : 'video/mp4';
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
                <source src={url} type={type}/>
            </video>
        </ModalContent>
    </React.Fragment>
}

function getAudioModal(previewFile) {
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

function getSTLModal(previewFile) {
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

export const FilePreviewContext = React.createContext({
    previewFile: null,
    setPreviewFile: null,
    previewModal: null,
    setPreviewModal: null,
    setCallbacks: null,
});

const MAXIMUM_TEXT_SIZE = 5_000_000;

export function FilePreviewWrapper({children}) {
    const [previewFile, setPreviewFile] = React.useState(null);
    const [previewModal, setPreviewModal] = React.useState(null);
    const [callbacks, setCallbacks] = React.useState(null);

    const localFetchFile = async () => {
        // Get the file again with its Tags.
        const {path, primary_path} = previewFile;
        try {
            const file = await fetchFile(primary_path ?? path);
            setPreviewFile(file);
        } finally {
            await handleCallbacks();
        }
    };

    const handleClose = () => {
        setPreviewModal(null);
        setPreviewFile(null);
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
        await addTag(previewFile, name);
        await localFetchFile();
    }

    const localRemoveTag = async (name) => {
        await removeTag(previewFile, name);
        await localFetchFile();
    }

    function setModalContent(content, url, downloadURL) {
        let openButton;
        if (url) {
            openButton = <SButton color='blue' as='a' href={url}>Open</SButton>;
        }
        const closeButton = <SButton onClick={handleClose}>Close</SButton>;
        const tagsDisplay = <TagsProvider>
            <TagsSelector selectedTagNames={previewFile['tags']} onAdd={localAddTag} onRemove={localRemoveTag}/>
        </TagsProvider>;
        let downloadButton;
        if (downloadURL) {
            downloadButton = <SButton color='yellow' as='a' href={downloadURL} floated='left'>
                Download
            </SButton>;
        }

        setPreviewModal(<Modal closeIcon
                               size='fullscreen'
                               open={true}
                               onClose={handleClose}
        >
            {content}
            <ModalActions>
                <Media at='mobile'>
                    <Grid>
                        <Grid.Row>
                            <Grid.Column width={6}>{downloadButton}</Grid.Column>
                            <Grid.Column width={5}>{openButton}</Grid.Column>
                            <Grid.Column width={5}>{closeButton}</Grid.Column>
                        </Grid.Row>
                        <Grid.Row>
                            <Grid.Column width={16}>{tagsDisplay}</Grid.Column>
                        </Grid.Row>
                    </Grid>
                </Media>
                <Media greaterThanOrEqual='tablet'>
                    <Grid>
                        <Grid.Row>
                            <Grid.Column width={2}>{downloadButton}</Grid.Column>
                            <Grid.Column width={10}>{tagsDisplay}</Grid.Column>
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
            return;
        }

        if (previewFile && !_.isEmpty(previewFile)) {
            const {mimetype, size} = previewFile;
            const path = previewFile['primary_path'] || previewFile['path'];
            const lowerPath = path.toLowerCase();
            console.debug(`useFilePreview path=${previewFile['path']} mimetype=${mimetype}`);
            const url = getMediaPathURL(previewFile);
            const downloadURL = getDownloadPathURL(previewFile);
            if (mimetype.startsWith('text/') && size > MAXIMUM_TEXT_SIZE) {
                // Large text files should be downloaded.
                window.open(downloadURL);
            } else if (mimetype.startsWith('text/') || mimetype.startsWith('application/json')) {
                setModalContent(getIframeModal(previewFile), url, downloadURL);
            } else if (mimetype.startsWith('video/')) {
                setModalContent(getVideoModal(previewFile), url, downloadURL);
            } else if (mimetype.startsWith('audio/')) {
                setModalContent(getAudioModal(previewFile), url, downloadURL);
            } else if (mimetype.startsWith('application/epub')) {
                const viewerURL = getEpubViewerURL(previewFile);
                setModalContent(getEpubModal(previewFile), viewerURL, downloadURL);
            } else if (mimetype.startsWith('application/pdf')) {
                setModalContent(getIframeModal(previewFile), url, downloadURL);
            } else if (mimetype.startsWith('image/')) {
                setModalContent(getImageModal(previewFile), url);
            } else if (mimetype.startsWith('model/stl')) {
                setModalContent(getSTLModal(previewFile), null, downloadURL);
            } else if (mimetype.startsWith('application/octet-stream') && lowerPath.endsWith('.mp3')) {
                setModalContent(getAudioModal(previewFile), url, downloadURL);
            } else if (mimetype.startsWith('application/octet-stream') && lowerPath.endsWith('.stl')) {
                setModalContent(getSTLModal(previewFile), null, downloadURL);
            } else {
                // No special handler for this file type, just open it.
                window.open(downloadURL);
            }
        }
    }, [previewFile]);

    const value = {previewFile, setPreviewFile, previewModal, setPreviewModal, setCallbacks};

    return <FilePreviewContext.Provider value={value}>
        {children}
        {previewModal}
    </FilePreviewContext.Provider>
}
