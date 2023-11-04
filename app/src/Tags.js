import React, {useEffect} from "react";
import {deleteTag, getTags, saveTag} from "./api";
import {
    Dimmer,
    Divider,
    Form,
    Grid,
    GridColumn,
    GridRow,
    Label,
    LabelGroup,
    TableCell,
    TableRow,
} from "semantic-ui-react";
import {APIButton, contrastingColor, ErrorMessage, scrollToTopOfElement} from "./components/Common";
import {
    Button,
    FormInput,
    Header,
    Loader,
    Modal,
    ModalActions,
    ModalContent,
    ModalHeader,
    Segment
} from "./components/Theme";
import _ from "lodash";
import {HexColorPicker} from "react-colorful";
import {useRecurringTimeout} from "./hooks/customHooks";
import {Media, ThemeContext} from "./contexts/contexts";
import {Link, useNavigate} from "react-router-dom";
import {TagPlaceholder} from "./components/Placeholder";
import {SortableTable} from "./components/SortableTable";

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
            setTags(undefined);
            setTagNames(undefined);
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

    const TagLabelLink = ({name, props}) => {
        const to = `/search?tag=${name}`;
        const style = {marginLeft: '0.3em', marginRight: '0.3em'};
        try {
            // We prefer to use Link to avoid reloading the page, check if React Router is available, so we can use it.
            useNavigate();
            return <Link to={to} style={style}>
                <NameToTagLabel name={name} {...props}/>
            </Link>
        } catch {
            // React Router is not available, use anchor.
            return <a href={to} style={style}>
                <NameToTagLabel name={name} {...props}/>
            </a>
        }
    }

    const TagsLinkGroup = ({tagNames, ...props}) => {
        if (!tagNames || tagNames.length === 0) {
            return <React.Fragment/>;
        }

        return <Label.Group tag>
            {tagNames.map(i => <TagLabelLink key={i} name={i} props={props}/>)}
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

function EditTagRow({tag, onDelete, onEdit}) {
    const {NameToTagLabel} = React.useContext(TagsContext);
    const {name, color, id, file_group_count, zim_entry_count} = tag;

    const deleteConfirm = <>
        <APIButton
            icon='trash'
            color='red'
            confirmContent={`Are you sure you want to delete: ${name}?`}
            confirmButton='Delete'
            onClick={async () => onDelete(id, name)}
        />
    </>;
    const editButton = <Button primary onClick={() => onEdit(name, color, id)} icon='edit'/>;
    const nameLabel = <LabelGroup tag>
        <NameToTagLabel name={name}/>
    </LabelGroup>;
    const countColor = (file_group_count + zim_entry_count) > 0 ? 'black' : 'grey';
    const countLabel = <Label color={countColor}>{file_group_count + zim_entry_count}</Label>;

    return <TableRow>
        <TableCell>{deleteConfirm}</TableCell>
        <TableCell>{editButton}</TableCell>
        <TableCell>{nameLabel}</TableCell>
        <Media greaterThanOrEqual='tablet'>
            {(className, renderChildren) => {
                return renderChildren ? <TableCell className={className}>
                        {countLabel}
                    </TableCell>
                    : null;
            }}
        </Media>
    </TableRow>
}

function EditTagsModal() {
    const {fetchTags, tags} = React.useContext(TagsContext);
    const {inverted} = React.useContext(ThemeContext);

    const [open, setOpen] = React.useState(false);
    const [tagId, setTagId] = React.useState(null);
    const [tagName, setTagName] = React.useState('');
    const [tagColor, setTagColor] = React.useState(DEFAULT_TAG_COLOR);
    const textColor = contrastingColor(tagColor);

    const localOnClose = () => {
        setOpen(false);
        setTagName('');
        setTagColor(DEFAULT_TAG_COLOR);
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
        // Scroll to top of Edit Modal.
        const editModalContent = document.getElementById('editModalContent');
        scrollToTopOfElement(editModalContent);
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

    const tableHeaders = [
        {key: 'delete', text: 'Delete', sortBy: null, width: 2},
        {key: 'edit', text: 'Edit', sortBy: null, width: 2},
        {key: 'name', text: 'Name', sortBy: 'name', width: 8},
        {key: 'count', text: 'Count', sortBy: i => i['file_group_count'] + i['zim_entry_count'], width: 2},
    ];
    const mobileTableHeaders = tableHeaders.slice(3);

    return <>
        <Modal closeIcon
               open={open}
               onOpen={() => setOpen(true)}
               onClose={localOnClose}
        >
            <ModalHeader>Edit Tags</ModalHeader>
            <div className={`content scrolling ${inverted}`} id='editModalContent'>
                <Label.Group tag>
                    <Label size='large' style={{backgroundColor: tagColor, color: textColor}}>
                        {tagName || 'Example Tag'}
                    </Label>
                </Label.Group>

                <Form autoComplete='off'>
                    <FormInput required
                               label={<b>Tag Name</b>}
                               placeholder='Unique name'
                               value={tagName}
                               onChange={(e, {value}) => setTagName(value)}
                    />
                </Form>

                <HexColorPicker color={tagColor} onChange={setTagColor} style={{marginTop: '1em'}}/>

                <APIButton
                    color='violet'
                    size='big'
                    onClick={localSaveTag}
                    style={{marginTop: '2em'}}
                    disabled={!!!tagName}
                >Save</APIButton>

                <Divider/>

                <Media at='mobile'>
                    <SortableTable
                        tableProps={{unstackable: true}}
                        data={tags}
                        rowFunc={(i, sortData) => <EditTagRow key={i['name']} tag={i} onDelete={localDeleteTag}
                                                              onEdit={localEditTag}/>}
                        rowKey='name'
                        tableHeaders={mobileTableHeaders}
                    />
                </Media>
                <Media greaterThanOrEqual='tablet'>
                    <SortableTable
                        tableProps={{unstackable: true}}
                        data={tags}
                        rowFunc={(i, sortData) => <EditTagRow key={i['name']} tag={i} onDelete={localDeleteTag}
                                                              onEdit={localEditTag}/>}
                        rowKey='name'
                        tableHeaders={tableHeaders}
                    />
                </Media>
            </div>
        </Modal>
        <Button onClick={() => setOpen(true)} color='violet' disabled={tags === undefined}>
            Edit
        </Button>
    </>
}

export function AddTagsButton({
                                  hideEdit,
                                  active,
                                  selectedTagNames = [],
                                  onToggle = _.noop,
                                  onAdd = _.noop,
                                  onRemove = _.noop
                              }) {
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

    const clearLocalTags = () => {
        if (!localTags || (localTags && localTags.length === 0)) {
            console.debug('No tags to clear');
            return
        }

        setLoading(true);
        try {
            for (let i = 0; i < localTags.length; i++) {
                onRemove(localTags[i]);
            }
            setLocalTags([]);
            onToggle([]);
        } finally {
            setLoading(false);
        }
    }

    const selectedTagsGroup = <TagsGroup tagNames={localTags} onClick={removeTag}/>;
    const unusedTags = _.difference(tagNames, localTags);
    const unusedTagsGroup = <TagsGroup tagNames={unusedTags} onClick={addTag}/>;

    return <>
        <Button icon={active ? 'tags' : 'tag'} onClick={handleOpen} primary={!!active}/>
        <Modal closeIcon
               open={open}
               onOpen={(e) => handleOpen(e)}
               onClose={() => setOpen(false)}>
            <ModalContent>
                {loading && <Dimmer active><Loader/></Dimmer>}
                <Header as='h4'>Applied Tags</Header>

                {localTags && localTags.length > 0 ? selectedTagsGroup : 'Add one or more tags below'}

                <Divider/>

                {unusedTags && unusedTags.length > 0 ? unusedTagsGroup : 'You have no tags'}
            </ModalContent>
            <ModalActions>
                <Grid textAlign='left'>
                    <Grid.Row>
                        <Grid.Column width={8}>
                            {!hideEdit && <EditTagsModal/>}
                        </Grid.Column>
                        <Grid.Column width={8}>
                            <Button onClick={() => setOpen(false)} floated='right'>Close</Button>
                            <Button floated='right' secondary onClick={() => clearLocalTags()}>Clear</Button>
                        </Grid.Column>
                    </Grid.Row>
                </Grid>
            </ModalActions>
        </Modal>
    </>
}

export const taggedImageLabel = {corner: 'left', icon: 'tag', color: 'green'};

export const TagsSelector = ({
                                 hideEdit = false,
                                 active,
                                 hideGroup = false,
                                 selectedTagNames = [],
                                 onToggle = _.noop,
                                 onAdd = _.noop,
                                 onRemove = _.noop
                             }) => {
    // Provides a button to add tags to a list.  Displays the tags of that list.
    const {TagsLinkGroup} = React.useContext(TagsContext);

    if (!TagsLinkGroup) {
        // Tags have not been fetched.
        return <></>;
    }

    const button = <AddTagsButton
        hideEdit={hideEdit}
        active={active}
        selectedTagNames={selectedTagNames}
        onToggle={onToggle}
        onAdd={onAdd}
        onRemove={onRemove}
    />;

    if (hideGroup) {
        return button;
    }

    return <Grid>
        <Grid.Row>
            <Grid.Column mobile={2} computer={1}>
                {button}
            </Grid.Column>
            <Grid.Column mobile={13} computer={14}>
                <TagsLinkGroup tagNames={selectedTagNames}/>
            </Grid.Column>
        </Grid.Row>
    </Grid>
}

export const TagsDashboard = () => {
    const {tagNames, TagsLinkGroup} = React.useContext(TagsContext);

    const tagPlaceholder = <GridColumn style={{width: 100}}><TagPlaceholder/></GridColumn>;
    let availableTagsGroup = <Grid columns={3}>
        <GridRow>
            {tagPlaceholder}
            {tagPlaceholder}
            {tagPlaceholder}
        </GridRow>
    </Grid>;
    if (tagNames && tagNames.length >= 1) {
        availableTagsGroup = <TagsLinkGroup tagNames={tagNames} style={{marginTop: '0.5em'}}/>;
    } else if (tagNames === undefined) {
        availableTagsGroup = <ErrorMessage>Could not fetch tags</ErrorMessage>
    }

    return <Segment>
        <Header as='h2'>Tags</Header>
        {availableTagsGroup}

        <Divider/>

        <EditTagsModal/>
    </Segment>
}

export const TagsProvider = (props) => {
    const tagsValue = useTagsInterval();

    return <TagsContext.Provider value={tagsValue}>
        {props.children}
    </TagsContext.Provider>
}
