import React, {useEffect, useState} from 'react';
import {Link, Route, Routes, useLocation, useNavigate, useParams, useSearchParams} from "react-router";
import {deleteFileGroups, getDocStatistics, tagFileGroup, untagFileGroup} from "../api";
import {Media} from "../contexts/contexts";
import {
    APIButton,
    BackButton,
    DirectoryLink,
    encodeMediaPath,
    ErrorMessage,
    humanFileSize,
    isoDatetimeToAgoPopup,
    PageContainer,
    PreviewPath,
    SearchInput,
    TabLinks,
    toLocaleString,
    useTitle
} from "./Common";
import {Button, ButtonGroup, Group, Header, Loading, Panel, Statistic, StatisticGroup, Tabs} from "./ui";
import {BulkTagModal} from "./BulkTagModal";
import {TaggedDeleteConfirmModal} from "./TaggedDeleteConfirmModal";
import {DeepSearchHint, docMimetypeFilterOptions, FilesView, SearchControlBar} from "./Files";
import {useAuthors, useDoc, useOneQuery, useSearchDocs, useSubjects} from "../hooks/customHooks";
import {TagsSelector} from "../Tags";
import {toast} from "./ui";
import {CollectionTable} from "./collections/CollectionTable";
import {AddToPlaylistButton} from "./AddToPlaylist";
import {CbzViewer} from "./CbzViewer";
import _ from "lodash";

function DocsPage() {
    useTitle('Documents');
    const searchInputRef = React.useRef();

    const {
        docs,
        totalPages,
        activePage,
        setPage,
        searchStr,
        setSearchStr,
        author,
        subject,
        fetchDocs,
    } = useSearchDocs();

    const [selectedDocs, setSelectedDocs] = useState([]);
    const [bulkTagOpen, setBulkTagOpen] = useState(false);
    const [taggedFileGroups, setTaggedFileGroups] = useState(null);

    const onSelect = (path, checked) => {
        if (checked && path) {
            setSelectedDocs([...selectedDocs, path]);
        } else if (path) {
            setSelectedDocs(selectedDocs.filter(i => i !== path));
        }
    }

    const onDelete = async (force = false) => {
        const fileGroupIds = docs.filter(i => selectedDocs.indexOf(i['primary_path']) >= 0).map(i => i['id']);
        const result = await deleteFileGroups(fileGroupIds, force);
        if (result && result.tagged) {
            setTaggedFileGroups(result.file_groups);
            return;
        }
        await fetchDocs();
        setSelectedDocs([]);
    }

    const invertSelection = () => {
        const newSelectedDocs = docs.map(doc => doc['key']).filter(i => selectedDocs.indexOf(i) < 0);
        setSelectedDocs(newSelectedDocs);
    }

    const clearSelection = (e) => {
        if (e) e.preventDefault();
        setSelectedDocs([]);
    }

    const onBulkTagComplete = async () => {
        await fetchDocs();
        setSelectedDocs([]);
    }

    const selectElm = <div style={{marginTop: '0.5em'}}>
        <Button color='violet' disabled={_.isEmpty(selectedDocs)}
                onClick={() => setBulkTagOpen(true)}>Tag</Button>
        <APIButton
            role='danger'
            disabled={_.isEmpty(selectedDocs)}
            confirmButton='Delete'
            confirmContent='Are you sure you want to delete these documents? This cannot be undone.'
            onClick={() => onDelete(false)}
            obeyWROLMode={true}
        >Delete</APIButton>
        <Button role='cancel' onClick={invertSelection} disabled={_.isEmpty(docs)}>Invert</Button>
        <Button role='cancel' onClick={clearSelection}
                disabled={_.isEmpty(docs) || _.isEmpty(selectedDocs)}>Clear</Button>
        <BulkTagModal
            open={bulkTagOpen}
            onClose={() => setBulkTagOpen(false)}
            paths={selectedDocs}
            onComplete={onBulkTagComplete}
        />
    </div>;

    let docOrders = [
        {value: 'published_datetime', text: 'Published Date', short: 'P.Date'},
        {value: 'size', text: 'Size'},
        {value: 'title', text: 'Title'},
    ];
    if (searchStr) {
        docOrders = [{value: 'rank', text: 'Rank'}, ...docOrders];
    }

    const {body, paginator, viewButton} = FilesView(
        {
            files: docs,
            activePage: activePage,
            totalPages: totalPages,
            selectElem: selectElm,
            selectedKeys: selectedDocs,
            onSelect: onSelect,
            setPage: setPage,
        },
    );

    return <>
        {author && <Header as='h1'>Author: {author}</Header>}
        {subject && <Header as='h1'>Subject: {subject}</Header>}
        <SearchControlBar
            searchStr={searchStr}
            setSearchStr={setSearchStr}
            placeholder='Search Documents...'
            inputRef={searchInputRef}
            viewButton={viewButton}
            sorts={docOrders}
            fileFilterOptions={docMimetypeFilterOptions}
            showDeep={true}
        />
        {body}
        <DeepSearchHint searchStr={searchStr} files={docs}/>
        {paginator}
        <TaggedDeleteConfirmModal
            open={taggedFileGroups !== null}
            taggedFileGroups={taggedFileGroups}
            onCancel={() => setTaggedFileGroups(null)}
            onConfirm={async () => {
                setTaggedFileGroups(null);
                await onDelete(true);
            }}
        />
    </>;
}

function DocPage() {
    const {fileGroupId} = useParams();
    const navigate = useNavigate();
    const {docFile, doc, fetchDoc} = useDoc(parseInt(fileGroupId));
    const [searchParams] = useSearchParams();
    const [taggedFileGroups, setTaggedFileGroups] = useState(null);
    // Deep-link params: `loc` = EPUB spine index, `page` = PDF page, `q` = search term.
    const locParam = searchParams.get('loc');
    const pageParam = searchParams.get('page');
    const qParam = searchParams.get('q');

    const title = docFile ? (docFile.title || docFile.name) : null;
    useTitle(title);

    const [selectedFileIndex, setSelectedFileIndex] = useState(0);

    if (docFile === null) {
        return <Panel><Loading/></Panel>;
    }
    if (docFile === undefined) {
        return <>
            <Header as='h2'>Unknown document</Header>
            <Header as='h4'>This document does not exist</Header>
        </>;
    }

    const {data, size, directory} = docFile;

    // Cover image.
    const coverPath = data && data.cover_path ? data.cover_path : null;
    const coverUrl = coverPath ? `/media/${encodeMediaPath(coverPath)}` : null;

    // Filter files to those that can be viewed inline (EPUB, PDF, comic books).
    const CBZ_EXTENSIONS = ['cbz', 'cbr', 'cbt', 'cb7'];
    const isViewableMimetype = (mt) => {
        if (!mt) return false;
        if (mt.startsWith('application/epub')) return true;
        if (mt === 'application/pdf') return true;
        if (mt.includes('cbz') || mt.includes('cbr') || mt.includes('comicbook+zip') || mt.includes('comicbook-rar')) return true;
        return false;
    };
    const viewableFiles = (docFile.files || [])
        .filter(f => isViewableMimetype(f.mimetype) || CBZ_EXTENSIONS.includes((f.path || '').toLowerCase().split('.').pop()))
        .sort((a, b) => {
            if (String(a.path) === String(docFile.primary_path)) return -1;
            if (String(b.path) === String(docFile.primary_path)) return 1;
            return 0;
        });

    const selectedFile = viewableFiles[selectedFileIndex] || viewableFiles[0];

    // Derive viewer state from the selected file (or fall back to primary).
    const activePath = selectedFile ? selectedFile.path : docFile.primary_path;
    const activeMimetype = selectedFile ? (selectedFile.mimetype || '') : (docFile.mimetype || '');
    const activeExt = (String(activePath) || '').toLowerCase().split('.').pop();

    const downloadUrl = activePath ? `/download/${encodeMediaPath(activePath)}` : null;
    const isEpub = activeMimetype.startsWith('application/epub');
    const isPdf = activeMimetype === 'application/pdf';
    const isCbz = activeMimetype.includes('cbz') || activeMimetype.includes('cbr')
        || activeMimetype.includes('comicbook+zip') || activeMimetype.includes('comicbook-rar')
        || CBZ_EXTENSIONS.includes(activeExt);
    // Build EPUB viewer URL, propagating any deep-link params through to epub.html.
    let viewerUrl = null;
    if (isEpub) {
        const epubParams = new URLSearchParams();
        epubParams.set('url', downloadUrl);
        if (locParam) epubParams.set('loc', locParam);
        if (qParam) epubParams.set('q', qParam);
        viewerUrl = `/epub/epub.html?${epubParams.toString()}`;
    }
    const openUrl = viewerUrl || (activePath ? `/media/${encodeMediaPath(activePath)}` : null);
    const canEmbed = isEpub || isPdf;
    // PDFs use the browser's built-in viewer, which honors `#page=N` fragments.
    const pdfSrc = isPdf && activePath
        ? `/media/${encodeMediaPath(activePath)}${pageParam ? `#page=${encodeURIComponent(pageParam)}` : ''}`
        : null;
    const embedUrl = isEpub ? viewerUrl : pdfSrc;

    const handleDelete = async (force = false) => {
        if (doc && doc.id) {
            const result = await deleteFileGroups([docFile.id], force);
            if (result && result.tagged) {
                setTaggedFileGroups(result.file_groups);
                return;
            }
            toast({
                type: 'success',
                title: 'Document Deleted',
                description: 'Document was successfully deleted.',
                time: 2000,
            });
            navigate(-1);
        }
    };

    const localAddTag = async (name) => {
        await tagFileGroup(docFile, name);
        await fetchDoc();
    };

    const localRemoveTag = async (name) => {
        await untagFileGroup(docFile, name);
        await fetchDoc();
    };

    const publishedDatetimeString = docFile.published_datetime
        ? isoDatetimeToAgoPopup(docFile.published_datetime, true)
        : null;

    // Format badge based on mimetype.
    const formatLabel = (overrideMt) => {
        const mt = overrideMt || activeMimetype;
        if (mt.startsWith('application/epub')) return 'EPUB';
        if (mt === 'application/x-mobipocket-ebook') return 'MOBI';
        if (mt === 'application/pdf') return 'PDF';
        if (mt.includes('wordprocessingml')) return 'DOCX';
        if (mt === 'application/msword') return 'DOC';
        if (mt.includes('opendocument.text')) return 'ODT';
        if (mt.includes('cbz') || mt.includes('comicbook+zip')) return 'CBZ';
        if (mt.includes('cbr') || mt.includes('comicbook-rar')) return 'CBR';
        if (mt.includes('cbt')) return 'CBT';
        if (mt.includes('cb7') || mt.includes('x-7z')) return 'CB7';
        return mt.split('/').pop().toUpperCase();
    };

    // About tab.
    const aboutTab = <>
        {doc && doc.description && <>
            <Header as='h3'>Description</Header>
            <p>{doc.description}</p>
        </>}

        {doc && doc.publisher && <>
            <Header as='h3'>Publisher</Header>
            <p>{doc.publisher}</p>
        </>}

        {doc && doc.language && <>
            <Header as='h3'>Language</Header>
            <p>{doc.language}</p>
        </>}

        {doc && doc.subject && <>
            <Header as='h3'>Subject</Header>
            <p><Link to={`/docs?subject=${encodeURIComponent(doc.subject)}`}>{doc.subject}</Link></p>
        </>}

        {doc && doc.page_count && <>
            <Header as='h3'>Page Count</Header>
            <p>{doc.page_count}</p>
        </>}

        <Header as='h3'>Size</Header>
        <p>{humanFileSize(size)}</p>
    </>;

    // Files tab.
    const tableStyle = {width: '100%', borderCollapse: 'separate', borderSpacing: '0 0.7em'};
    const labelStyle = {whiteSpace: 'nowrap', paddingRight: '1.5em', verticalAlign: 'top'};
    const filesTab = <table style={tableStyle}>
        <tbody>
        {docFile.files && docFile.files.map((file, idx) =>
            <tr key={idx}>
                <td style={labelStyle}>
                    <strong>{file.path.split('.').pop().toUpperCase()}</strong>
                </td>
                <td>
                    <PreviewPath path={file.path} mimetype={file.mimetype} taggable={false}>
                        {file.path}
                    </PreviewPath>
                    {file.size && <span style={{marginLeft: '1em', color: 'var(--muted)'}}>
                        ({humanFileSize(file.size)})
                    </span>}
                </td>
            </tr>
        )}
        <tr>
            <td style={labelStyle}><strong>Directory</strong></td>
            <td><DirectoryLink path={directory}/></td>
        </tr>
        </tbody>
    </table>;

    return <>
        <BackButton/>

        {isCbz && activePath && <CbzViewer path={activePath}/>}

        {canEmbed && embedUrl && !isCbz && <div style={{marginBottom: '1em'}}>
            <iframe
                src={embedUrl}
                title={docFile.title || docFile.name}
                style={{width: '100%', height: '80vh', border: '1px solid var(--border)'}}
            />
        </div>}

        <Panel>
            <Header as='h2'>{docFile.title || docFile.name}</Header>

            {docFile.author && <Header as='h3'>
                Author: <Link to={`/docs?author=${encodeURIComponent(docFile.author)}`}>{docFile.author}</Link>
            </Header>}

            <Group gap='xl' wrap='wrap'>
                <Header as='h4'>Format: {formatLabel()}{doc && doc.page_count && ` (${doc.page_count} pages)`}</Header>
                {publishedDatetimeString && <Header as='h4'>Published: {publishedDatetimeString}</Header>}
            </Group>

            {(() => {
                const formatButtons = viewableFiles.length > 1 ? <ButtonGroup>
                    {viewableFiles.map((file, idx) => {
                        const mt = file.mimetype || '';
                        let btnColor;
                        if (mt.startsWith('application/epub')) btnColor = 'yellow';
                        else if (mt === 'application/pdf') btnColor = 'red';
                        const isSelected = idx === selectedFileIndex;
                        return <Button
                            key={file.path}
                            onClick={() => setSelectedFileIndex(idx)}
                            color={isSelected ? btnColor : undefined}
                            variant={isSelected ? 'filled' : 'default'}
                        >
                            {formatLabel(file.mimetype)}
                        </Button>;
                    })}
                </ButtonGroup> : null;

                const actionButtons = <>
                    {openUrl && <Button component='a' href={openUrl} target='_blank' rel='noreferrer'
                                        color='violet' icon='expand arrows alternate'>
                        Open
                    </Button>}
                    {downloadUrl && <Button component='a' href={downloadUrl} icon='download'>
                        Download
                    </Button>}
                    <APIButton
                        role='danger'
                        confirmContent='Are you sure you want to delete this document? All files will be deleted.'
                        confirmButton='Delete'
                        onClick={() => handleDelete(false)}
                        obeyWROLMode={true}
                    >Delete</APIButton>
                    <AddToPlaylistButton fileGroupId={docFile.id}/>
                </>;

                return <>
                    <Media at='mobile'>
                        {formatButtons && <div style={{marginTop: '1em'}}>{formatButtons}</div>}
                        <div className='wrolpi-button-row' style={{marginTop: '1em'}}>
                            {actionButtons}
                        </div>
                    </Media>
                    <Media greaterThanOrEqual='tablet'>
                        {/* The row's own `margin-top` separates it from what is above; the gap
                            inside it separates the format picker from the actions, so the span
                            that used to hold them apart with `margin-right` is gone. */}
                        <div className='wrolpi-button-row' style={{marginTop: '1em'}}>
                            {formatButtons}
                            {actionButtons}
                        </div>
                    </Media>
                </>;
            })()}
        </Panel>

        <Panel>
            <TagsSelector selectedTagNames={docFile.tags} onAdd={localAddTag} onRemove={localRemoveTag}/>
        </Panel>

        <Tabs defaultValue='about'>
            <Tabs.List>
                <Tabs.Tab value='about'>About</Tabs.Tab>
                <Tabs.Tab value='files'>Files</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value='about' pt='md'>{aboutTab}</Tabs.Panel>
            <Tabs.Panel value='files' pt='md'>{filesTab}</Tabs.Panel>
        </Tabs>

        <TaggedDeleteConfirmModal
            open={taggedFileGroups !== null}
            taggedFileGroups={taggedFileGroups}
            onCancel={() => setTaggedFileGroups(null)}
            onConfirm={async () => {
                setTaggedFileGroups(null);
                await handleDelete(true);
            }}
        />
    </>;
}

const AUTHOR_COLUMNS = [
    {key: 'name', label: 'Author', sortable: true, width: 10},
    {key: 'item_count', label: 'Documents', sortable: true, align: 'right', width: 6},
];

const AUTHOR_ROUTES = {
    search: '/docs',
    searchParam: 'author',
};

const SUBJECT_COLUMNS = [
    {key: 'name', label: 'Subject', sortable: true, width: 10},
    {key: 'item_count', label: 'Documents', sortable: true, align: 'right', width: 6},
];

const SUBJECT_ROUTES = {
    search: '/docs',
    searchParam: 'subject',
};

function AuthorsPage() {
    useTitle('Doc Authors');

    const [authors] = useAuthors();
    const [searchStr, setSearchStr] = useOneQuery('author');
    const searchInputRef = React.useRef();

    // No `marginBottom`: a top-level block of the page, spaced by the page's stack.
    const header = <div>
        <SearchInput
            placeholder='Author filter...'
            size='large'
            searchStr={searchStr}
            disabled={!Array.isArray(authors) || authors.length === 0}
            onClear={() => setSearchStr('')}
            onChange={setSearchStr}
            onSubmit={null}
            inputRef={searchInputRef}
        />
    </div>;

    return <>
        {header}
        <CollectionTable
            collections={authors}
            columns={AUTHOR_COLUMNS}
            routes={AUTHOR_ROUTES}
            searchStr={searchStr}
            emptyMessage='No authors found. Index some documents with author metadata!'
        />
    </>;
}

function SubjectsPage() {
    useTitle('Doc Subjects');

    const [subjects] = useSubjects();
    const [searchStr, setSearchStr] = useOneQuery('subject');
    const searchInputRef = React.useRef();

    // No `marginBottom`: a top-level block of the page, spaced by the page's stack.
    const header = <div>
        <SearchInput
            placeholder='Subject filter...'
            size='large'
            searchStr={searchStr}
            disabled={!Array.isArray(subjects) || subjects.length === 0}
            onClear={() => setSearchStr('')}
            onChange={setSearchStr}
            onSubmit={null}
            inputRef={searchInputRef}
        />
    </div>;

    return <>
        {header}
        <CollectionTable
            collections={subjects}
            columns={SUBJECT_COLUMNS}
            routes={SUBJECT_ROUTES}
            searchStr={searchStr}
            emptyMessage='No subjects found. Index some documents with subject metadata!'
        />
    </>;
}

function DocsStatisticsPage() {
    useTitle('Doc Statistics');

    const [statistics, setStatistics] = useState(null);

    useEffect(() => {
        const fetchStats = async () => {
            try {
                const response = await getDocStatistics();
                if (response.ok) {
                    const data = await response.json();
                    setStatistics(data.statistics);
                }
            } catch (e) {
                setStatistics(undefined);
            }
        };
        fetchStats();
    }, []);

    if (statistics === null) {
        return <Loading/>;
    }
    if (statistics === undefined) {
        return <ErrorMessage>Unable to fetch Doc Statistics</ErrorMessage>;
    }

    return <Panel>
        <Header as='h1' style={{textAlign: 'center'}}>Documents</Header>
        <StatisticGroup>
            <Statistic value={toLocaleString(statistics.doc_count)} label='Documents'/>
            <Statistic value={toLocaleString(statistics.epub_count)} label='eBooks'/>
            <Statistic value={toLocaleString(statistics.pdf_count)} label='PDFs'/>
            <Statistic value={toLocaleString(statistics.other_count)} label='Other'/>
            <Statistic value={humanFileSize(statistics.total_size)} label='Total Size'/>
            <Statistic value={toLocaleString(statistics.author_count)} label='Authors'/>
            <Statistic value={toLocaleString(statistics.subject_count)} label='Subjects'/>
        </StatisticGroup>
    </Panel>;
}

export function DocsRoute() {
    const location = useLocation();
    const path = location.pathname;

    const links = [
        {
            text: 'Docs',
            to: '/docs',
            end: true,
            isActive: () => path === '/docs' || /^\/docs\/\d+$/.test(path)
        },
        {text: 'Subjects', to: '/docs/subjects', isActive: () => path.startsWith('/docs/subjects')},
        {text: 'Authors', to: '/docs/authors', isActive: () => path.startsWith('/docs/authors')},
        {text: 'Statistics', to: '/docs/statistics'},
    ];

    return <PageContainer>
        <TabLinks links={links}/>
        <Routes>
            <Route path='/' element={<DocsPage/>}/>
            <Route path=':fileGroupId' element={<DocPage/>}/>
            <Route path='subjects' element={<SubjectsPage/>}/>
            <Route path='authors' element={<AuthorsPage/>}/>
            <Route path='statistics' element={<DocsStatisticsPage/>}/>
        </Routes>
    </PageContainer>;
}
