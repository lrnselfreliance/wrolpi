import React, {useCallback, useEffect, useRef, useState} from 'react';
import {IconArrowLeft, IconArrowRight} from '@tabler/icons-react';
import {getArchiveContents, getArchiveMemberUrl} from '../api';
import {IconButton, Label, Loading, Message} from './ui';
import {useLocalStorage} from './Common';

const IMAGE_EXTENSIONS = /\.(jpe?g|png|gif|webp|bmp|tiff?)$/i;

/**
 * Recursively flatten archive tree entries into a list of file paths.
 */
function flattenEntries(entries, prefix = '') {
    let paths = [];
    for (const entry of entries) {
        const fullPath = entry.path || (prefix ? `${prefix}/${entry.name}` : entry.name);
        if (entry.is_dir && entry.children) {
            paths = paths.concat(flattenEntries(entry.children, fullPath));
        } else if (!entry.is_dir) {
            paths.push(fullPath);
        }
    }
    return paths;
}

export function CbzViewer({path}) {
    const [pages, setPages] = useState(null);
    const [currentPage, setCurrentPage] = useState(0);
    const [rtl, setRtl] = useLocalStorage('cbzViewerRtl', false);
    const [fullscreen, setFullscreen] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        const load = async () => {
            try {
                const contents = await getArchiveContents(path);
                if (!contents) {
                    setError('Could not read archive contents.');
                    return;
                }
                const images = flattenEntries(contents.entries)
                    .filter(name => IMAGE_EXTENSIONS.test(name))
                    .sort();
                const urls = images.map(member => getArchiveMemberUrl(path, member));
                setPages(urls);
                setCurrentPage(0);
            } catch (e) {
                setError(e.message || 'Could not read archive contents.');
            }
        };
        load();
    }, [path]);

    const goNext = useCallback(() => {
        setCurrentPage(p => Math.min(p + 1, (pages?.length || 1) - 1));
    }, [pages]);

    const goPrev = useCallback(() => {
        setCurrentPage(p => Math.max(p - 1, 0));
    }, []);

    const onLeftClick = rtl ? goNext : goPrev;
    const onRightClick = rtl ? goPrev : goNext;
    const imageContainerRef = useRef(null);

    const handleFullscreen = useCallback(() => {
        setFullscreen(f => !f);
    }, []);

    useEffect(() => {
        const handleKey = (e) => {
            if (e.key === 'ArrowLeft') onLeftClick();
            else if (e.key === 'ArrowRight') onRightClick();
            else if (e.key === 'Escape') setFullscreen(false);
        };
        window.addEventListener('keydown', handleKey);
        return () => window.removeEventListener('keydown', handleKey);
    }, [onLeftClick, onRightClick]);

    if (error) {
        return <Message kind='error' title='Cannot load comic'>
            <p>{error}</p>
        </Message>;
    }
    if (!pages) return <Loading/>;
    if (pages.length === 0) {
        return <Message kind='warning' title='No images found'>
            <p>This archive does not contain any image files.</p>
        </Message>;
    }

    const hasPrev = currentPage > 0;
    const hasNext = currentPage < pages.length - 1;

    return <div style={{marginBottom: '1em'}}>
        <div ref={imageContainerRef} className='media' style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            background: 'var(--bg)',
            borderRadius: 0,
            padding: '0.5em',
            minHeight: '300px',
            position: fullscreen ? 'fixed' : 'relative',
            ...(fullscreen ? {top: 0, left: 0, right: 0, bottom: 0, zIndex: 9999} : {}),
        }}>
            <img
                src={pages[currentPage]}
                alt={`Page ${currentPage + 1}`}
                style={{
                    maxHeight: fullscreen ? '100dvh' : 'calc(100dvh - 300px)',
                    maxWidth: '100%',
                    objectFit: 'contain',
                }}
            />
            <div style={{
                position: 'absolute',
                top: 0, left: 0, right: 0, bottom: 0,
                display: 'grid',
                gridTemplateColumns: '1fr 1fr 1fr',
            }}>
                <div style={{cursor: 'pointer'}} onClick={onLeftClick}/>
                <div style={{cursor: 'pointer'}} onClick={handleFullscreen}/>
                <div style={{cursor: 'pointer'}} onClick={onRightClick}/>
            </div>
        </div>

        <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.5em',
            marginTop: '0.5em',
        }}>
            <IconButton icon={rtl ? IconArrowLeft : IconArrowRight} label='Reading direction'
                        variant={rtl ? 'filled' : 'default'} onClick={() => setRtl(r => !r)}/>
            <span style={{flex: 1}}/>
            <IconButton icon='chevron left' label='Previous page'
                        disabled={rtl ? !hasNext : !hasPrev} onClick={onLeftClick}/>
            <Label>{currentPage + 1} / {pages.length}</Label>
            <IconButton icon='chevron right' label='Next page'
                        disabled={rtl ? !hasPrev : !hasNext} onClick={onRightClick}/>
        </div>
    </div>;
}
