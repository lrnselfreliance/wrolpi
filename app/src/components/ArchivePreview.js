import React from "react";
import {Icon, Loader, Message, Placeholder, PlaceholderLine} from "semantic-ui-react";
import {downloadArchiveMember, getArchiveContents} from "../api";
import {fileSuffixIconName, humanFileSize} from "./Common";
import {Modal, Segment, Table} from "./Theme";

function ArchiveEntry({entry, depth, archivePath}) {
    const [expanded, setExpanded] = React.useState(depth === 0);

    const indent = '\xa0\xa0\xa0\xa0'.repeat(depth);

    if (entry.is_dir) {
        const folderRows = expanded && entry.children ? entry.children.map((child, i) =>
            <ArchiveEntry key={child.path || i} entry={child} depth={depth + 1} archivePath={archivePath}/>
        ) : null;

        return <React.Fragment>
            <Table.Row onClick={() => setExpanded(!expanded)} style={{cursor: 'pointer'}}>
                <Table.Cell className='file-path'>
                    {indent}
                    <Icon name={expanded ? 'folder open' : 'folder'}/>
                    {entry.name}/
                </Table.Cell>
                <Table.Cell collapsing textAlign='right'>
                    &mdash;
                </Table.Cell>
            </Table.Row>
            {folderRows}
        </React.Fragment>
    }

    const handleDownload = () => {
        downloadArchiveMember(archivePath, entry.path);
    };

    return <Table.Row>
        <Table.Cell className='file-path' onClick={handleDownload} style={{cursor: 'pointer'}}>
            {indent}
            <Icon name={fileSuffixIconName(entry.name)}/>
            {entry.name}
            {' '}
            <Icon name='download' size='small' color='grey'/>
        </Table.Cell>
        <Table.Cell collapsing textAlign='right'>
            {humanFileSize(entry.size)}
        </Table.Cell>
    </Table.Row>
}

function SkeletonRows() {
    return <React.Fragment>
        {[1, 2, 3].map(i =>
            <Table.Row key={i}>
                <Table.Cell colSpan={2}>
                    <Placeholder><PlaceholderLine/></Placeholder>
                </Table.Cell>
            </Table.Row>
        )}
    </React.Fragment>
}

export function ArchivePreviewContent({previewFile}) {
    const [contents, setContents] = React.useState(null);
    const [loading, setLoading] = React.useState(true);
    const [error, setError] = React.useState(null);

    const path = previewFile['primary_path'] || previewFile['path'];

    React.useEffect(() => {
        const fetchContents = async () => {
            setLoading(true);
            setError(null);
            try {
                const result = await getArchiveContents(path);
                if (result) {
                    setContents(result);
                } else {
                    setError('Could not read archive contents.');
                }
            } catch (e) {
                setError(e.message || 'Could not read archive contents.');
            } finally {
                setLoading(false);
            }
        };
        fetchContents();
    }, [path]);

    if (error) {
        return <Modal.Content>
            <Message negative>
                <Message.Header>Cannot read archive</Message.Header>
                <p>{error}</p>
            </Message>
        </Modal.Content>
    }

    return <Modal.Content scrolling>
        {!loading && contents && <Segment>
            <Icon name='archive'/>
            <strong>{contents.total_files}</strong> files,{' '}
            <strong>{humanFileSize(contents.total_size)}</strong> total
        </Segment>}
        <Table striped selectable unstackable>
            <Table.Header>
                <Table.Row>
                    <Table.HeaderCell>Name</Table.HeaderCell>
                    <Table.HeaderCell collapsing textAlign='right'>Size</Table.HeaderCell>
                </Table.Row>
            </Table.Header>
            <Table.Body>
                {loading
                    ? <SkeletonRows/>
                    : contents && contents.entries.map((entry, i) =>
                        <ArchiveEntry key={entry.path || i} entry={entry} depth={0} archivePath={path}/>
                    )
                }
            </Table.Body>
        </Table>
    </Modal.Content>
}
