import React from "react";
import _ from "lodash";
import {
    Button as SButton,
    Header as SHeader,
    Image,
    Modal,
    ModalActions,
    ModalContent,
    ModalHeader
} from "semantic-ui-react";

function getMediaPathURL(file) {
    if (file['primary_path']) {
        return `/media/${encodeURIComponent(file['primary_path'])}`;
    } else {
        return `/media/${encodeURIComponent(file['path'])}`;
    }
}

function getDownloadPathURL(file) {
    if (file['primary_path']) {
        return `/download/${encodeURIComponent(file['primary_path'])}`;
    } else {
        return `/download/${encodeURIComponent(file['path'])}`;
    }
}

function getEpubViewerURL(file) {
    if (file['primary_path']) {
        return `/epub.html?url=download/${encodeURIComponent(file['primary_path'])}`;
    } else {
        return `/epub.html?url=download/${encodeURIComponent(file['path'])}`;
    }
}

function getIframeModal(path) {
    const url = getMediaPathURL(path);
    return <ModalContent>
        <div className='full-height'>
            <iframe title='textModal' src={url}
                    style={{
                        height: '100%', width: '100%', border: 'none', position: 'absolute', top: 0,
                    }}/>
        </div>
    </ModalContent>
}

function getImageModal(path) {
    const url = getMediaPathURL(path);
    const name = path['path'].replace(/^.*[\\\/]/, '');
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

function getEpubModal(path) {
    const downloadURL = getDownloadPathURL(path);
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

function getVideoModal(path) {
    const url = getMediaPathURL(path);
    const name = path['path'].replace(/^.*[\\\/]/, '');
    const type = path['mimetype'] ? path['mimetype'] : 'video/mp4';
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

function getAudioModal(path) {
    const url = getMediaPathURL(path);
    const name = path['path'].replace(/^.*[\\\/]/, '');
    // Some audio files may not have the correct mimetype.  Trust the suffix identifies an audio file.
    const type = path['mimetype'] !== 'application/octet-stream' ? path['mimetype'] : 'audio/mpeg';
    return <React.Fragment>
        <ModalHeader>
            {name}
        </ModalHeader><ModalContent>
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

export const FilePreviewContext = React.createContext({
    previewFile: null, setPreviewFile: null, previewModal: null, setPreviewModal: null,
});

const MAXIMUM_TEXT_SIZE = 5_000_000;

export function FilePreviewWrapper({children}) {
    const [previewFile, setPreviewFile] = React.useState(null);
    const [previewModal, setPreviewModal] = React.useState(null);

    const value = {
        previewFile, setPreviewFile, previewModal, setPreviewModal,
    };

    function setModalContent(content, url, downloadURL) {
        setPreviewModal(<Modal closeIcon
                               size='fullscreen'
                               open={true}
                               onClose={() => setPreviewModal(null)}
        >
            {content}
            <ModalActions>
                {downloadURL &&
                    <SButton color='yellow' onClick={() => window.open(downloadURL)} floated='left'>Download</SButton>}
                <SButton color='blue' onClick={() => window.open(url)}>Open</SButton>
                <SButton onClick={() => setPreviewFile(null)}>Close</SButton>
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
            } else if (mimetype.startsWith('image/')) {
                setModalContent(getImageModal(previewFile), url);
            } else if (mimetype.startsWith('application/octet-stream') && lowerPath.endsWith('.mp3')) {
                setModalContent(getAudioModal(previewFile), url, downloadURL);
            } else {
                // No special handler for this file type, just open it.
                window.open(downloadURL);
            }
        }
    }, [previewFile]);

    return <FilePreviewContext.Provider value={value}>
        {children}
        {previewModal}
    </FilePreviewContext.Provider>
}
