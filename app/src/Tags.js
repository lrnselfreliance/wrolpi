import React, {useEffect, useState} from "react";
import {deleteTag, getTags, saveTag} from "./api";
import {
    Button as SButton,
    Confirm,
    Dimmer,
    Divider,
    Dropdown,
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
import {contrastingColor} from "./components/Common";
import {Segment} from "./components/Theme";
import _ from "lodash";
import {HexColorPicker} from "react-colorful";
import {useRecurringTimeout} from "./hooks/customHooks";

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
                className={props.onClick ? 'clickable' : null}
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

export const useTagsInterval = () => {
    const tagsValue = useTags();
    const {fetchTags} = tagsValue;

    useRecurringTimeout(fetchTags, 30_000);

    return tagsValue
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

    const localOnClose = () => {
        setOpen(false);
        setTagName('');
        setTagColor(null);
        setTagId(null);
    }

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
               onClose={localOnClose}
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

                <SButton color='violet'
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
        <SButton onClick={() => setOpen(true)} color='violet'>
            Edit
        </SButton>
    </>
}

export function AddTagsButton({selectedTagNames = [], onToggle = _.noop, onAdd = _.noop, onRemove = _.noop}) {
    // A button which displays a modal in which the user can add or remove tags.

    const {tagNames, TagsGroup} = React.useContext(TagsContext);
    const [open, setOpen] = React.useState(false);
    const [loading, setLoading] = React.useState(false);
    const [localTags, setLocalTags] = React.useState(selectedTagNames);

    const handleOpen = (e) => {
        if (e) {
            e.preventDefault();
        }
        setOpen(true);
    }

    const addTag = (name) => {
        setLoading(true);
        try {
            const newTags = [...localTags, name];
            setLocalTags(newTags);
            onToggle(newTags);
            onAdd(name);
        } finally {
            setLoading(false);
        }
    }

    const removeTag = (name) => {
        setLoading(true);
        try {
            const newTags = localTags.filter(i => i !== name);
            setLocalTags(newTags);
            onToggle(newTags);
            onRemove(name);
        } finally {
            setLoading(false);
        }
    }

    const selectedTagsGroup = <TagsGroup tagNames={localTags} onClick={removeTag}/>;
    const unusedTags = _.difference(tagNames, localTags);
    const unusedTagsGroup = <TagsGroup tagNames={unusedTags} onClick={addTag}/>;

    return <>
        <SButton icon='tag' onClick={handleOpen} color='violet'/>
        <Modal closeIcon
               open={open}
               onOpen={(e) => handleOpen(e)}
               onClose={() => setOpen(false)}>
            <Modal.Content>
                {loading && <Dimmer active><SLoader/></Dimmer>}
                <Header as='h4'>Applied Tags</Header>

                {localTags && localTags.length > 0 ? selectedTagsGroup : 'Add tags below'}

                <Divider/>

                {unusedTags && unusedTags.length > 0 ? unusedTagsGroup : 'You have no tags'}
            </Modal.Content>
            <Modal.Actions>
                <EditTagsModal/>
            </Modal.Actions>
        </Modal>
    </>
}

export const taggedImageLabel = {corner: 'left', icon: 'tag', color: 'green'};

export const TagsSelector = ({selectedTagNames = [], onToggle = _.noop, onAdd = _.noop, onRemove = _.noop}) => {
    // Provides a button to add tags to a list.  Displays the tags of that list.
    const {TagsLinkGroup} = React.useContext(TagsContext);

    if (!TagsLinkGroup) {
        // Tags have not been fetched.
        return <></>;
    }

    return <Grid>
        <Grid.Row>
            <Grid.Column mobile={2} computer={1}>
                <AddTagsButton selectedTagNames={selectedTagNames} onToggle={onToggle} onAdd={onAdd}
                               onRemove={onRemove}/>
            </Grid.Column>
            <Grid.Column mobile={13} computer={14}>
                <TagsLinkGroup tagNames={selectedTagNames}/>
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

export const TagsDropdown = ({value = [], onChange, ...props}) => {
    const {tagNames} = React.useContext(TagsContext);
    const [activeTags, setActiveTags] = React.useState(value);

    const handleChange = (e, {value}) => {
        if (e) {
            e.preventDefault();
        }
        if (!value) {
            setActiveTags([]);
            onChange([]);
        } else {
            setActiveTags(value);
            onChange(value);
        }
    }

    let options = [{key: null, text: '', value: ''}];
    if (tagNames && tagNames.length > 0) {
        const tagOptions = tagNames.map(i => {
            return {key: i, text: i, value: i}
        })
        options = [...options, ...tagOptions];
    }

    return <Dropdown multiple selection clearable
                     options={options}
                     placeholder='Tags'
                     onChange={handleChange}
                     value={activeTags}
                     {...props}
    />
}
