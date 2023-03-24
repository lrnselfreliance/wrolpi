import React, {useEffect, useState} from "react";
import {addTag, deleteTag, getTags, postTag, removeTag} from "./api";
import {
    Button as SButton,
    Confirm,
    Dimmer,
    Divider,
    Form,
    FormField,
    FormInput,
    Grid,
    Header,
    Label,
    Loader,
    Loader as SLoader,
    Modal,
} from "semantic-ui-react";
import {contrastingColor, HelpPopup} from "./components/Common";
import {Button, Segment} from "./components/Theme";
import _ from "lodash";
import {Link} from "react-router-dom";
import {HexColorPicker} from "react-colorful";

export const TagsContext = React.createContext({tags: [], fetchTags: null});

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

    const NameToTagLabel = ({name, color, to, ...props}) => {
        if (tags && tags.length) {
            for (let i = 0; i < tags.length; i++) {
                const tag = tags[i];
                if (name === tag['name']) {
                    const textColor = contrastingColor(tag['color']);
                    const label = <Label
                        size='large'
                        style={{backgroundColor: tag['color'], color: textColor}}
                        className='clickable'
                        {...props} // onClick passed here.
                    >
                        {name}
                    </Label>;
                    return label;
                }
            }
        }

        // Could not find tag by name, or no tags have been fetched.
        return <Label size='large'>{name}</Label>;
    }

    const TagsGroup = ({tagNames, onClick}) => {
        if (!tagNames || tagNames.length === 0) {
            return <React.Fragment/>;
        }
        return <Label.Group tag>
            {tagNames.map(i => <NameToTagLabel key={i} name={i} onClick={() => onClick(i)}/>)}
        </Label.Group>
    }

    const TagsLinkGroup = ({tagNames}) => {
        if (!tagNames || tagNames.length === 0) {
            return <React.Fragment/>;
        }
        return <Label.Group tag>
            {tagNames.map(i =>
                <Link key={i} to={`/?tag=${i}`} style={{margin: '0.3em'}}>
                    <NameToTagLabel name={i}/>
                </Link>
            )}
        </Label.Group>
    }

    useEffect(() => {
        setTags([]);
        fetchTags();
    }, []);

    return {tags, tagNames, NameToTagLabel, TagsGroup, TagsLinkGroup, fetchTags}
}

function DeleteTagLabel({name, onConfirm}) {
    const {NameToTagLabel} = React.useContext(TagsContext);
    const [confirmOpen, setConfirmOpen] = useState(false);

    return <div style={{marginTop: '1em'}}>
        <SButton color='red' onClick={() => setConfirmOpen(true)} icon='close'/>
        <Confirm
            id={`confirm${name}`}
            open={confirmOpen}
            content={`Are you sure you want to delete: ${name}?`}
            confirmButton='Delete'
            onCancel={() => setConfirmOpen(false)}
            onConfirm={async () => onConfirm(name)}
        />
        <NameToTagLabel name={name}/>
        <br/>
    </div>
}

function DeleteTagModal() {
    const {fetchTags, tagNames} = React.useContext(TagsContext);

    const [open, setOpen] = useState(false);

    const localDeleteTag = async (name) => {
        await deleteTag(name);
        if (fetchTags) {
            await fetchTags();
        }
    }

    const content = tagNames && tagNames.length ?
        tagNames.map(i => <DeleteTagLabel key={i} name={i} onConfirm={localDeleteTag}/>)
        : <Dimmer><Loader inline active/></Dimmer>;

    return <>
        <Modal closeIcon
               open={open}
               onOpen={() => setOpen(true)}
               onClose={() => setOpen(false)}
        >
            <Modal.Header>Delete Tags</Modal.Header>
            <Modal.Content>
                {content}
            </Modal.Content>
        </Modal>
        <SButton color='red' onClick={() => setOpen(true)}>
            Delete
        </SButton>
    </>
}

function CreateTagModal() {
    const {fetchTags} = React.useContext(TagsContext);

    const [open, setOpen] = useState(false);
    const [tagName, setTagName] = useState('');
    const [tagColor, setTagColor] = useState('#000000');
    const textColor = contrastingColor(tagColor);

    const saveTag = async () => {
        await postTag(tagName, tagColor);
        if (fetchTags) {
            await fetchTags();
        }
        setTagName('');
    }

    return <>
        <Modal closeIcon
               open={open}
               onOpen={() => setOpen(true)}
               onClose={() => setOpen(false)}
        >
            <Modal.Header>Create New Tag</Modal.Header>
            <Modal.Content>
                <Label.Group tag>
                    <Label size='large' style={{backgroundColor: tagColor, color: textColor}}>
                        {tagName || 'Example Tag'}
                    </Label>
                </Label.Group>

                <Divider/>

                <Form autoComplete='off'>
                    <FormField>
                        <FormInput required
                                   label='Tag Name'
                                   type='text'
                                   placeholder='Unique Name'
                                   value={tagName}
                                   onChange={(e, {value}) => setTagName(value)}
                        />
                    </FormField>

                    <HexColorPicker color={tagColor} onChange={setTagColor}/>

                    <SButton primary
                             size='big'
                             onClick={saveTag}
                             style={{marginTop: '2em'}}
                             disabled={!!!tagName}
                    >
                        Save
                    </SButton>
                </Form>

            </Modal.Content>
        </Modal>

        <SButton primary onClick={() => setOpen(true)}>New</SButton>
    </>
}

export function TagsModal({fileGroup, onClick}) {
    const {tags: usedTags} = fileGroup;
    const {TagsGroup} = useTags();
    const {tags: availableTags} = React.useContext(TagsContext);
    const [open, setOpen] = useState(false);
    const [loading, setLoading] = useState(false);

    const localAddTag = async (name) => {
        setLoading(true);
        try {
            await addTag(fileGroup, name);
            await onClick();
            console.debug('Added tag');
        } finally {
            setLoading(false);
        }
    };

    const localRemoveTag = async (name) => {
        setLoading(true);
        try {
            await removeTag(fileGroup, name);
            await onClick();
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
            <DeleteTagModal/>
            <CreateTagModal/>
        </Modal.Actions>
    </Modal>

    return <>
        <Button icon='tag' onClick={() => setOpen(true)}/>
        {modal}
    </>
}

export const taggedImageLabel = {corner: 'left', icon: 'tag', color: 'green'};

export const TagsDisplay = ({fileGroup, onClick}) => {
    const {TagsLinkGroup} = useTags();

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

export const TagsSegment = () => {
    const {tagNames, TagsLinkGroup} = useTags();

    let availableTagsGroup = <SLoader active inline/>;
    if (tagNames && tagNames.length) {
        availableTagsGroup = <TagsLinkGroup tagNames={tagNames}/>;
    }
    return <Segment>
        <Header as='h2'>Tags</Header>
        {availableTagsGroup}

        <Divider/>

        <DeleteTagModal/>
        <CreateTagModal/>
    </Segment>
}
