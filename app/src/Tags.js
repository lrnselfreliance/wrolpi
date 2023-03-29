import React, {useEffect, useState} from "react";
import {addTag, deleteTag, getTags, removeTag, saveTag} from "./api";
import {
    Button as SButton,
    Confirm,
    Dimmer,
    Divider,
    Form,
    FormInput,
    Grid,
    Header,
    Label,
    LabelGroup,
    Loader,
    Loader as SLoader,
    Modal,
    Table as STable,
    TableBody,
    TableCell,
    TableHeader,
    TableHeaderCell,
    TableRow,
} from "semantic-ui-react";
import {contrastingColor, HelpPopup} from "./components/Common";
import {Segment} from "./components/Theme";
import _ from "lodash";
import {HexColorPicker} from "react-colorful";

export const TagsContext = React.createContext({
    NameToTagLabel: null,
    TagsGroup: null,
    TagsLinkGroup: null,
    fetchTags: null,
    findTagByName: null,
    tagNames: [],
    tags: [],
});

const DEFAULT_TAG_COLOR = '#000000';

export function useTags() {
    const [tags, setTags] = React.useState(null);
    const [tagNames, setTagNames] = React.useState(null);

    const fetchTags = async () => {
        try {
            const t = await getTags();
            setTags(t);
            setTagNames(t.map(i => i['name']));
        } catch (e) {
            setTags([]);
            setTagNames([]);
            console.error(e);
        }
    }

    const findTagByName = (name) => {
        if (!tags || tags.length === 0) {
            return;
        }
        for (let i = 0; i < tags.length; i++) {
            const tag = tags[i];
            if (name === tag['name']) {
                return tag;
            }
        }
    }

    const NameToTagLabel = ({name, to, ...props}) => {
        const defaultTag = <Label size='large'>{name}</Label>;
        const tag = findTagByName(name);
        if (tag !== null && tag !== undefined) {
            const tagColor = tag['color'] || DEFAULT_TAG_COLOR;
            const textColor = contrastingColor(tagColor);
            const style = {...props['style'], backgroundColor: tagColor, color: textColor};
            return <Label
                size='large'
                {...props} // onClick passed here.
                style={style}
                className='clickable'
            >
                {name}
            </Label>;
        }

        // No tags have been fetched.
        return defaultTag;
    }

    const TagsGroup = ({tagNames, onClick}) => {
        if (!tagNames || tagNames.length === 0) {
            return <React.Fragment/>;
        }
        return <Label.Group tag>
            {tagNames.map(i => <NameToTagLabel key={i} name={i} onClick={() => onClick(i)}/>)}
        </Label.Group>
    }

    const TagsLinkGroup = ({tagNames, ...props}) => {
        if (!tagNames || tagNames.length === 0) {
            return <React.Fragment/>;
        }
        return <Label.Group tag>
            {tagNames.map(i =>
                <a key={i} href={`/?tag=${i}`} style={{marginLeft: '0.3em', marginRight: '0.3em'}}>
                    <NameToTagLabel name={i} {...props}/>
                </a>
            )}
        </Label.Group>
    }

    useEffect(() => {
        setTags([]);
        fetchTags();
    }, []);

    return {tags, tagNames, NameToTagLabel, TagsGroup, TagsLinkGroup, fetchTags, findTagByName}
}

function EditTagLabel({tag, onDelete, onEdit}) {
    const {NameToTagLabel} = React.useContext(TagsContext);
    const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
    const {name, color, id} = tag;

    return <TableRow>
        <TableCell>
            <SButton color='red' onClick={() => setConfirmDeleteOpen(true)} icon='trash'/>
            <Confirm
                id={`confirm${name}`}
                open={confirmDeleteOpen}
                content={`Are you sure you want to delete: ${name}?`}
                confirmButton='Delete'
                onCancel={() => setConfirmDeleteOpen(false)}
                onConfirm={async () => onDelete(id, name)}
            />
        </TableCell>
        <TableCell>
            <SButton primary onClick={() => onEdit(name, color, id)} icon='edit'/>
        </TableCell>
        <TableCell>
            <LabelGroup tag>
                <NameToTagLabel name={name}/>
            </LabelGroup>
        </TableCell>
    </TableRow>
}

function EditTagsModal() {
    const {fetchTags, tags} = React.useContext(TagsContext);

    const [open, setOpen] = useState(false);
    const [tagId, setTagId] = useState(null);
    const [tagName, setTagName] = useState('');
    const [tagColor, setTagColor] = useState(DEFAULT_TAG_COLOR);
    const textColor = contrastingColor(tagColor);

    const localDeleteTag = async (id, name) => {
        await deleteTag(id, name);
        if (fetchTags) {
            await fetchTags();
        }
    }

    const localEditTag = async (name, color, id) => {
        setTagName(name);
        setTagColor(color || DEFAULT_TAG_COLOR);
        setTagId(id);
    }

    const localSaveTag = async () => {
        await saveTag(tagName, tagColor, tagId);
        if (fetchTags) {
            await fetchTags();
        }
        setTagName('');
        setTagId(null);
        setTagColor(DEFAULT_TAG_COLOR);
    }

    let content = <Dimmer><Loader inline active/></Dimmer>;
    if (tags && tags.length) {
        content = tags.map(i => <EditTagLabel key={i['name']} tag={i} onDelete={localDeleteTag}
                                              onEdit={localEditTag}/>);
    }

    return <>
        <Modal closeIcon
               open={open}
               onOpen={() => setOpen(true)}
               onClose={() => setOpen(false)}
        >
            <Modal.Header>Edit Tags</Modal.Header>
            <Modal.Content>
                <Label.Group tag>
                    <Label size='large' style={{backgroundColor: tagColor, color: textColor}}>
                        {tagName || 'Example Tag'}
                    </Label>
                </Label.Group>

                <Form autoComplete='off'>
                    <FormInput required
                               label='Tag Name'
                               placeholder='Unique name'
                               value={tagName}
                               onChange={(e, {value}) => setTagName(value)}
                    />
                </Form>

                <HexColorPicker color={tagColor} onChange={setTagColor} style={{marginTop: '1em'}}/>

                <SButton primary
                         size='big'
                         onClick={localSaveTag}
                         style={{marginTop: '2em'}}
                         disabled={!!!tagName}
                >
                    Save
                </SButton>

                <Divider/>
                <STable striped basic='very' unstackable>
                    <TableHeader>
                        <TableRow>
                            <TableHeaderCell width={2}>Delete</TableHeaderCell>
                            <TableHeaderCell width={2}>Edit</TableHeaderCell>
                            <TableHeaderCell width={8}>Tag</TableHeaderCell>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {content}
                    </TableBody>
                </STable>
            </Modal.Content>
        </Modal>
        <SButton primary onClick={() => setOpen(true)}>
            Edit
        </SButton>
    </>
}

export function TagsModal({fileGroup, onClick}) {
    const {tags: usedTags} = fileGroup;
    const {tags: availableTags, TagsGroup} = React.useContext(TagsContext);
    const [open, setOpen] = useState(false);
    const [loading, setLoading] = useState(false);

    const localAddTag = async (name) => {
        setLoading(true);
        try {
            await addTag(fileGroup, name);
            if (onClick) {
                await onClick();
            }
            console.debug('Added tag');
        } finally {
            setLoading(false);
        }
    };

    const localRemoveTag = async (name) => {
        setLoading(true);
        try {
            await removeTag(fileGroup, name);
            if (onClick) {
                await onClick();
            }
            console.debug('Removed tag');
        } finally {
            setLoading(false);
        }
    };

    const availableTagNames = availableTags && availableTags.length ? availableTags.map(i => i['name']) : [];

    const unusedTags = _.difference(availableTagNames, usedTags);

    let availableTagsGroup = <SLoader active inline/>;
    if (unusedTags && unusedTags.length) {
        availableTagsGroup = <TagsGroup tagNames={unusedTags} onClick={localAddTag}/>;
    }

    let usedTagsGroup = 'Add tags by clicking them below';
    if (usedTags && usedTags.length) {
        // TODO sort these labels.
        usedTagsGroup = <TagsGroup tagNames={usedTags} onClick={localRemoveTag}/>;
    }

    const modal = <Modal closeIcon
                         open={open}
                         onOpen={() => setOpen(true)}
                         onClose={() => setOpen(false)}>
        <Modal.Content>
            {loading && <Dimmer active><SLoader/></Dimmer>}
            <Header as='h4'>Used Tags</Header>

            {usedTagsGroup}

            <Divider/>

            {availableTagsGroup}
        </Modal.Content>
        <Modal.Actions>
            <EditTagsModal/>
        </Modal.Actions>
    </Modal>

    return <>
        <SButton icon='tag' onClick={() => setOpen(true)}/>
        {modal}
    </>
}

export const taggedImageLabel = {corner: 'left', icon: 'tag', color: 'green'};

export const TagsDisplay = ({fileGroup, onClick}) => {
    const {TagsLinkGroup} = React.useContext(TagsContext);

    if (!fileGroup || !TagsLinkGroup) {
        return
    }

    return <Grid>
        <Grid.Row>
            <Grid.Column mobile={2} computer={1}>
                <TagsModal fileGroup={fileGroup} onClick={onClick}/>
            </Grid.Column>
            <Grid.Column mobile={13} computer={14}>
                <TagsLinkGroup tagNames={fileGroup['tags']}/>
                {_.isEmpty(fileGroup['tags']) &&
                    <HelpPopup content='Click the button to add tags' iconSize={null}/>
                }
            </Grid.Column>
        </Grid.Row>
    </Grid>
}

export const TagsDashboard = () => {
    const {tagNames, TagsLinkGroup} = React.useContext(TagsContext);

    let availableTagsGroup = <SLoader active inline/>;
    if (tagNames && tagNames.length) {
        availableTagsGroup = <TagsLinkGroup tagNames={tagNames} style={{marginTop: '0.5em'}}/>;
    }

    return <Segment>
        <Header as='h2'>Tags</Header>
        {availableTagsGroup}

        <Divider/>

        <EditTagsModal/>
    </Segment>
}
