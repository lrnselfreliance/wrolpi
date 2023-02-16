import React from "react";
import _ from "lodash";
import {Button as SButton, Image, Modal, ModalActions, ModalContent} from "semantic-ui-react";

function getMediaPathURL(path) {
    return `/media/${encodeURIComponent(path['path'])}`;
}

function getDownloadPathURL(path) {
    return `/download/${encodeURIComponent(path['path'])}`;
}

function getEpubViewerURL(path) {
    return `/epub.html?url=download/${encodeURIComponent(path['path'])}`;
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
    return <ModalContent>
        <a href={url}>
            <Image src={url}/>
        </a>
    </ModalContent>
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
    return <ModalContent>
        <video controls
               autoPlay={true}
               id="player"
               playsInline={true}
               style={{maxWidth: '100%'}}
        >
            <source src={url} type="video/mp4"/>
        </video>
    </ModalContent>
}

export const FilePreviewContext = React.createContext({
    previewPath: null, setPreviewPath: null, previewModal: null, setPreviewModal: null,
});

export function FilePreviewWrapper({children}) {
    const [previewPath, setPreviewPath] = React.useState(null);
    const [previewModal, setPreviewModal] = React.useState(null);

    const value = {
        previewPath, setPreviewPath, previewModal, setPreviewModal,
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
                <SButton onClick={() => setPreviewPath(null)}>Close</SButton>
            </ModalActions>
        </Modal>);
    }

    React.useEffect(() => {
        setPreviewModal(null);
        if (previewPath && !_.isEmpty(previewPath)) {
            const {mimetype, size} = previewPath;
            console.debug(`useFilePreview path=${previewPath['path']} mimetype=${mimetype}`);
            const url = getMediaPathURL(previewPath);
            const downloadURL = getDownloadPathURL(previewPath);
            if (mimetype.startsWith('text/') && size >= 10000) {
                // Large text files should be downloaded.
                window.open(downloadURL);
            } else if (mimetype.startsWith('text/') || mimetype.startsWith('application/json')) {
                setModalContent(getIframeModal(previewPath), url, downloadURL);
            } else if (mimetype.startsWith('video/')) {
                setModalContent(getVideoModal(previewPath), url, downloadURL);
            } else if (mimetype.startsWith('application/epub')) {
                const viewerURL = getEpubViewerURL(previewPath);
                console.dir(previewPath);
                console.log(viewerURL);
                setModalContent(getEpubModal(previewPath), viewerURL, downloadURL);
            } else if (mimetype.startsWith('image/')) {
                setModalContent(getImageModal(previewPath), url);
            } else {
                // No special handler for this file type, just open it.
                window.open(downloadURL);
            }
        }
    }, [previewPath]);

    return <FilePreviewContext.Provider value={value}>
        {children}
        {previewModal}
    </FilePreviewContext.Provider>
}
