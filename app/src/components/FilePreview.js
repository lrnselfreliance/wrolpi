import React from "react";
import _ from "lodash";
import {Header as SHeader, Icon, Image,} from "semantic-ui-react";
import {TagsSelector} from "../Tags";
import {encodeMediaPath, isSupportedArchive} from "./Common";
import {getFile, tagFileGroup, untagFileGroup} from "../api";
import {ArchivePreviewContent} from "./ArchivePreview";
import {CbzViewer} from "./CbzViewer";
import {StlViewer} from "react-stl-viewer";
import {Button, Modal} from "./Theme";
import {toast} from "react-semantic-toasts-2";
import {useOneQuery} from "../hooks/customHooks";
import {ShareButton} from "./Share";
import {pathDirectory} from "./FileBrowser";
import {InlineErrorBoundary} from "./ErrorBoundary";
import {useLocation} from "react-router";

// Routes where file views should not be tracked
const EXCLUDED_TRACKING_ROUTES = [
    /^\/videos\/video\//,
    /^\/videos\/channel\/[^/]+\/video\//,
    /^\/archive\/\d+/
];

function shouldSkipTracking(pathname) {
    return EXCLUDED_TRACKING_ROUTES.some(pattern => pattern.test(pathname));
}

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
    return <Modal.Content>
        <div className='preview-fit'>
            <iframe title='textModal' src={url}
                    style={{
                        height: '100%', width: '100%', border: 'none',
                        // Use white to avoid iframe displaying with dark-theme.
                        backgroundColor: '#ffffff',
                    }}/>
        </div>
    </Modal.Content>
}

function getImagePreviewModal(previewFile) {
    const path = previewFile.primary_path ?? previewFile.path;
    const url = getMediaPathURL(previewFile);
    // Get the file name from the absolute path.
    const name = path.replace(/^.*[\\\/]/, '');
    return <React.Fragment>
        <Modal.Header>
            {name}
        </Modal.Header>
        <Modal.Content>
            <div className='preview-fit'>
                <a href={url}>
                    <Image src={url} style={{maxHeight: '100%', maxWidth: '100%', objectFit: 'contain'}}/>
                </a>
            </div>
        </Modal.Content>
    </React.Fragment>
}

function getVideoPreviewModal(previewFile) {
    const url = getMediaPathURL(previewFile);
    const path = previewFile.primary_path ?? previewFile.path;
    const name = path.replace(/^.*[\\\/]/, '');
    return <React.Fragment>
        <Modal.Header>
            {name}
        </Modal.Header>
        <Modal.Content>
            <SHeader as='h5'>{path['path']}</SHeader>
            <div className='preview-fit'>
                <video controls
                       autoPlay={true}
                       id="player"
                       playsInline={true}
                       style={{maxHeight: '100%', maxWidth: '100%'}}
                >
                    <source src={url}/>
                </video>
            </div>
        </Modal.Content>
    </React.Fragment>
}

function getAudioPreviewModal(previewFile) {
    const url = getMediaPathURL(previewFile);
    const path = previewFile.primary_path ?? previewFile.path;
    const name = path.replace(/^.*[\\\/]/, '');
    // Some audio files may not have the correct mimetype.  Trust the suffix identifies an audio file.
    const type = previewFile['mimetype'] !== 'application/octet-stream' ? previewFile['mimetype'] : 'audio/mpeg';
    return <React.Fragment>
        <Modal.Header>
            {name}
        </Modal.Header>
        <Modal.Content>
            <audio controls
                   autoPlay={true}
                   id="player"
                   playsInline={true}
                   style={{width: '90%', maxWidth: '95%'}}
            >
                <source src={url} type={type}/>
            </audio>
        </Modal.Content>
    </React.Fragment>
}

function ThreeMFPreviewModal({previewFile}) {
    const containerRef = React.useRef(null);
    const [dimensions, setDimensions] = React.useState(null);
    const [error, setError] = React.useState(null);
    const url = getMediaPathURL(previewFile);
    const path = previewFile.primary_path ?? previewFile.path;
    const name = path.replace(/^.*[\\\/]/, '');

    React.useEffect(() => {
        // Imperative three.js viewer — mirrors react-stl-viewer behavior for .3mf files.
        let cancelled = false;
        const container = containerRef.current;
        if (!container) return;

        let renderer, scene, camera, controls, animationId, resizeObserver, loadedGroup;
        let THREE;

        (async () => {
            try {
                THREE = await import('three');
                const {OrbitControls} = await import('three/examples/jsm/controls/OrbitControls.js');
                const {ThreeMFLoader} = await import('three/examples/jsm/loaders/3MFLoader.js');
                if (cancelled) return;

                scene = new THREE.Scene();
                // Transparent background so the modal/theme color shows through,
                // matching react-stl-viewer's behavior.

                const width = container.clientWidth || 1;
                const height = container.clientHeight || 1;

                camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 10000);
                camera.position.set(0, 0, 100);

                renderer = new THREE.WebGLRenderer({antialias: true, alpha: true});
                renderer.setClearColor(0x000000, 0);
                renderer.setPixelRatio(window.devicePixelRatio);
                renderer.setSize(width, height);
                container.appendChild(renderer.domElement);

                scene.add(new THREE.AmbientLight(0xffffff, 0.6));
                const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
                dirLight.position.set(1, 1, 1);
                scene.add(dirLight);
                const dirLight2 = new THREE.DirectionalLight(0xffffff, 0.4);
                dirLight2.position.set(-1, -1, -1);
                scene.add(dirLight2);

                controls = new OrbitControls(camera, renderer.domElement);
                controls.enableDamping = true;

                const loader = new ThreeMFLoader();
                loader.load(
                    url,
                    (group) => {
                        if (cancelled) return;
                        loadedGroup = group;

                        // Match react-stl-viewer's violet so 3MFs without authored
                        // materials are visible against either theme's background.
                        // 3MF geometry often lacks vertex normals — compute them so
                        // MeshPhongMaterial can shade faces instead of rendering flat black.
                        group.traverse((obj) => {
                            if (obj.isMesh) {
                                if (obj.geometry && !obj.geometry.attributes.normal) {
                                    obj.geometry.computeVertexNormals();
                                }
                                obj.material = new THREE.MeshPhongMaterial({
                                    color: 0x7353a8,
                                    flatShading: false,
                                });
                            }
                        });

                        scene.add(group);

                        // Frame the model: center it, then pull camera back along Z by bounding radius.
                        const box = new THREE.Box3().setFromObject(group);
                        const size = new THREE.Vector3();
                        const center = new THREE.Vector3();
                        box.getSize(size);
                        box.getCenter(center);
                        group.position.sub(center);

                        const boundingRadius = Math.max(size.x, size.y, size.z) / 2 || 1;
                        const fitDistance = boundingRadius / Math.tan((Math.PI * camera.fov) / 360);
                        camera.position.set(0, 0, fitDistance * 2.2);
                        camera.near = Math.max(0.1, fitDistance / 1000);
                        camera.far = fitDistance * 100;
                        camera.updateProjectionMatrix();
                        controls.target.set(0, 0, 0);
                        controls.update();

                        setDimensions({
                            width: size.x,
                            height: size.y,
                            length: size.z,
                            boundingRadius: size.length() / 2,
                        });
                    },
                    undefined,
                    (err) => {
                        console.error('Failed to load 3MF', err);
                        if (!cancelled) setError('Failed to load 3MF file.');
                    },
                );

                const animate = () => {
                    animationId = requestAnimationFrame(animate);
                    controls.update();
                    renderer.render(scene, camera);
                };
                animate();

                resizeObserver = new ResizeObserver(() => {
                    const w = container.clientWidth || 1;
                    const h = container.clientHeight || 1;
                    camera.aspect = w / h;
                    camera.updateProjectionMatrix();
                    renderer.setSize(w, h);
                });
                resizeObserver.observe(container);
            } catch (err) {
                console.error('3MF viewer init failed', err);
                if (!cancelled) setError('Failed to initialize 3MF viewer.');
            }
        })();

        return () => {
            cancelled = true;
            if (animationId) cancelAnimationFrame(animationId);
            if (resizeObserver) resizeObserver.disconnect();
            if (controls) controls.dispose();
            if (loadedGroup && THREE) {
                loadedGroup.traverse((obj) => {
                    if (obj.geometry) obj.geometry.dispose();
                    if (obj.material) {
                        const materials = Array.isArray(obj.material) ? obj.material : [obj.material];
                        materials.forEach((m) => {
                            if (m.map) m.map.dispose();
                            m.dispose();
                        });
                    }
                });
            }
            if (renderer) {
                renderer.dispose();
                if (renderer.domElement && renderer.domElement.parentNode) {
                    renderer.domElement.parentNode.removeChild(renderer.domElement);
                }
            }
        };
    }, [url]);

    return <React.Fragment>
        <Modal.Header>{name}</Modal.Header>
        <Modal.Content>
            {dimensions && <div style={{marginBottom: '1em', textAlign: 'center'}}>
                <b>Width:</b> {dimensions.width.toFixed(2)}
                {' | '}
                <b>Height:</b> {dimensions.height.toFixed(2)}
                {' | '}
                <b>Length:</b> {dimensions.length.toFixed(2)}
                {' | '}
                <b>Bounding Radius:</b> {dimensions.boundingRadius.toFixed(2)}
            </div>}
            {error && <div style={{color: 'red', textAlign: 'center'}}>{error}</div>}
            <InlineErrorBoundary>
                <div className='preview-fit'>
                    <div ref={containerRef} style={{height: '100%', width: '100%'}}/>
                </div>
            </InlineErrorBoundary>
        </Modal.Content>
    </React.Fragment>
}

function STLPreviewModal({previewFile}) {
    const [dimensions, setDimensions] = React.useState(null);
    const url = getMediaPathURL(previewFile);
    const path = previewFile.primary_path ?? previewFile.path;
    const name = path.replace(/^.*[\\\/]/, '');
    return <React.Fragment>
        <Modal.Header>{name}</Modal.Header>
        <Modal.Content>
            {dimensions && <div style={{marginBottom: '1em', textAlign: 'center'}}>
                <b>Width:</b> {dimensions.width.toFixed(2)}
                {' | '}
                <b>Height:</b> {dimensions.height.toFixed(2)}
                {' | '}
                <b>Length:</b> {dimensions.length.toFixed(2)}
                {' | '}
                <b>Bounding Radius:</b> {dimensions.boundingRadius.toFixed(2)}
            </div>}
            <InlineErrorBoundary>
                <div className='preview-fit'>
                    <StlViewer orbitControls shadows
                               url={url}
                               style={{height: '100%', width: '100%'}}
                               modelProps={{color: '#7353a8'}}
                               onFinishLoading={(dims) => setDimensions(dims)}
                    />
                </div>
            </InlineErrorBoundary>
        </Modal.Content>
    </React.Fragment>
}

function getGenericPreviewModal(previewFile) {
    // No special handler for this file type, just open it.
    const path = previewFile.primary_path ?? previewFile.path;
    const name = path.replace(/^.*[\\\/]/, '');

    return <React.Fragment>
        <Modal.Header>{name}</Modal.Header>
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
    const location = useLocation();

    // Determine if tracking should be skipped based on current route
    const skipTracking = shouldSkipTracking(location.pathname);

    const handleErrorModalClose = () => {
        setPreviewQuery(null);
        setErrorModalOpen(false);
    }

    const errorModal = <Modal closeIcon
                              open={errorModalOpen}
                              onClose={handleErrorModalClose}
    >
        <Modal.Header>Unknown File</Modal.Header>
        <Modal.Content>Cannot display preview, no such file exists: {previewQuery}</Modal.Content>
        <Modal.Actions>
            <Button onClick={handleErrorModalClose}>Close</Button>
        </Modal.Actions>
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
            const file = await getFile(previewQuery, skipTracking);
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
            const file = await getFile(primary_path ?? path, skipTracking);
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
        // All action buttons share `size='small'` and `icon` for consistent height across viewports.
        // Close is handled by the Modal's `closeIcon` (X in the top-right corner) — no dedicated button.
        const openButton = url
            ? <Button color='blue' as='a' href={url} size='small' icon labelPosition='left'>
                <Icon name='external'/>Open
            </Button>
            : null;
        const tagsDisplay = taggable ?
            <TagsSelector selectedTagNames={previewFile['tags']} onAdd={localAddTag}
                          onRemove={localRemoveTag}/>
            : null;
        const downloadButton = downloadURL
            ? <Button color='yellow' as='a' href={downloadURL} size='small' icon='download'/>
            : null;
        const directoryURL = path ? `/files?folders=${encodeURIComponent(pathDirectory(path))}` : null;
        const directoryButton = path ? <Button as='a' href={directoryURL} size='small' icon='folder'/> : null;
        const pathContent = path ? <Modal.Content>
                <pre>{path}</pre>
            </Modal.Content>
            : null;
        console.log('Previewing', path);
        console.log('Preview Download URL', downloadURL);
        console.log('Preview Open URL', url);

        // Single flex toolbar — same button order at every viewport size.
        // `flex-wrap: wrap` lets the tags selector drop to a second line on narrow screens
        // while the button groups stay together and in order: [file actions] [tags] [open/close].
        setPreviewModal(<Modal closeIcon
                               size='fullscreen'
                               open={true}
                               onClose={e => handleClose(e)}
        >
            {pathContent}
            <Modal.Actions>
                <div className='preview-toolbar'>
                    <div className='preview-toolbar-group'>
                        {downloadButton}
                        {directoryButton}
                        <ShareButton/>
                    </div>
                    <div className='preview-toolbar-tags'>{tagsDisplay}</div>
                    <div className='preview-toolbar-group'>
                        {openButton}
                    </div>
                </div>
            </Modal.Actions>
            {content}
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
                setModalContent(<STLPreviewModal previewFile={previewFile}/>, null, downloadURL, path, taggable);
            } else if (mimetype.startsWith('model/3mf')) {
                setModalContent(<ThreeMFPreviewModal previewFile={previewFile}/>, null, downloadURL, path, taggable);
            } else if (mimetype.startsWith('application/octet-stream') && lowerPath.endsWith('.mp3')) {
                setModalContent(getAudioPreviewModal(previewFile), url, downloadURL, path, taggable);
            } else if (mimetype.startsWith('application/octet-stream') && lowerPath.endsWith('.stl')) {
                setModalContent(<STLPreviewModal previewFile={previewFile}/>, null, downloadURL, path, taggable);
            } else if ((mimetype.startsWith('application/octet-stream') || mimetype === 'application/zip')
                && lowerPath.endsWith('.3mf')) {
                setModalContent(<ThreeMFPreviewModal previewFile={previewFile}/>, null, downloadURL, path, taggable);
            } else if (mimetype.includes('cbz') || mimetype.includes('cbr') || mimetype.includes('comicbook+zip') || mimetype.includes('comicbook-rar')
                || lowerPath.endsWith('.cbz') || lowerPath.endsWith('.cbr') || lowerPath.endsWith('.cbt') || lowerPath.endsWith('.cb7')) {
                setModalContent(<Modal.Content><CbzViewer path={path}/></Modal.Content>, null, downloadURL, path, taggable);
            } else if (isSupportedArchive(mimetype, lowerPath)) {
                setModalContent(<ArchivePreviewContent previewFile={previewFile}/>, null, downloadURL, path, taggable);
            } else {
                // No special handler for this file type, just open it.
                setModalContent(getGenericPreviewModal(previewFile), url, downloadURL, path, taggable);
            }

            // Trigger tracking for the file view (unless on an excluded route)
            if (!skipTracking) {
                getFile(path).catch(e => {
                    console.error(e);
                    console.error('Failed to get file to set FileGroup.viewed');
                });
            }
        }
    }, [previewFile, skipTracking]);

    const value = {previewFile, setPreviewFile, previewModal, setPreviewModal, setCallbacks};

    return <FilePreviewContext.Provider value={value}>
        {children}
        {previewModal}
        {errorModal}
    </FilePreviewContext.Provider>
}
