import React, {useEffect} from "react";
import _ from "lodash";
import {Button as SButton, Image, Modal, ModalActions, ModalContent} from "semantic-ui-react";

function getMediaPathURL(path) {
    return `/media/${encodeURIComponent(path['path'])}`;
}

function getDownloadPathURL(path) {
    return `/download/${encodeURIComponent(path['path'])}`;
}

function getEpubViewerURL(path) {
    return `/epub.html?url=${getDownloadPathURL(path)}`;
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

export function useFilePreview() {
    const [path, setPath] = React.useState(null);
    const [modal, setModal] = React.useState(null);

    function setModalContent(content, url, downloadURL) {
        setModal(<Modal closeIcon
                        size='fullscreen'
                        open={true}
                        onClose={() => setModal(null)}
        >
            {content}
            <ModalActions>
                {downloadURL &&
                    <SButton color='yellow' onClick={() => window.open(downloadURL)} floated='left'>Download</SButton>}
                <SButton color='blue' onClick={() => window.open(url)}>Open</SButton>
                <SButton onClick={() => setPath(null)}>Close</SButton>
            </ModalActions>
        </Modal>);
    }

    useEffect(() => {
        setModal(null);
        if (path && !_.isEmpty(path)) {
            const {mimetype, size} = path;
            console.debug(`useFilePreview path=${path['path']} mimetype=${mimetype}`);
            const url = getMediaPathURL(path);
            const downloadURL = getDownloadPathURL(path);
            if (mimetype.startsWith('text/') && size >= 10000) {
                // Large text files should be downloaded.
                window.open(downloadURL);
            } else if (mimetype.startsWith('text/') || mimetype.startsWith('application/json')) {
                setModalContent(getIframeModal(path), url, downloadURL);
            } else if (mimetype.startsWith('video/')) {
                setModalContent(getVideoModal(path), url, downloadURL);
            } else if (mimetype.startsWith('application/epub')) {
                const viewerURL = getEpubViewerURL(path);
                setModalContent(getEpubModal(path), viewerURL, downloadURL);
            } else if (mimetype.startsWith('image/')) {
                setModalContent(getImageModal(path), url);
            } else {
                // No special handler for this file type, just open it.
                window.open(downloadURL);
            }
        }
    }, [path]);

    return {modal, setPath};
}
