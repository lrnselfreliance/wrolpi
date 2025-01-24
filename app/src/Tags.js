import React, {useEffect} from "react";
import {ApiDownError, deleteTag, getTags, saveTag} from "./api";
import {Dimmer, Divider, Form, Grid, GridColumn, GridRow, Label, TableCell, TableRow,} from "semantic-ui-react";
import {
    APIButton,
    contrastingColor,
    ErrorMessage,
    fuzzyMatch,
    getDistinctColor,
    scrollToTopOfElement
} from "./components/Common";
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
import {Media, QueryContext, ThemeContext} from "./contexts/contexts";
import {Link, useNavigate} from "react-router-dom";
import {TagPlaceholder} from "./components/Placeholder";
import {SortableTable} from "./components/SortableTable";

export const TagsContext = React.createContext({
    NameToTagLabel: null,
    TagsGroup: null,
    TagsLinkGroup: null,
    SingleTag: null,
    fetchTags: null,
    findTagByName: null,
    fuzzyMatchTagsByName: null,
    tagNames: [],
    tags: [],
});

const DEFAULT_TAG_COLOR = '#000000';

export function useTags() {
    const [tags, setTags] = React.useState(null);
    const [tagNames, setTagNames] = React.useState(null);
    const {getLocationStr} = React.useContext(QueryContext);

    const fetchTags = async () => {
        if (window.apiDown) { // apiDown is set in useStatus
            return;
        }
        try {
            const t = await getTags();
            setTags(t);
            setTagNames(t.map(i => i['name']));
        } catch (e) {
            setTags(undefined);
            setTagNames(undefined);
            if (e instanceof ApiDownError) {
                // API is down, do not log this error.
                return;
            }
            // Ignore SyntaxError because they happen when the API is down.
            if (!(e instanceof SyntaxError)) {
                console.error(e);
            }
        }
    }

    React.useEffect(() => {
        if (!window.apiDown) {
            // Fetch tags when the API comes back up.
            fetchTags();
        }
    }, [window.apiDown]);

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

    const fuzzyMatchTagsByName = (name) => {
        const lowerName = name.toLowerCase();
        if (!tags || tags.length === 0) {
            return []
        }

        return tags.filter(i => i.name.toLowerCase().includes(name)
            || fuzzyMatch(lowerName, i.name.toLowerCase(), 2))
    }

    const NameToTagLabel = ({name, to, ...props}) => {
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

    const TagLabelLink = ({name, props}) => {
        const to = getLocationStr({tag: name}, '/search');
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

    const SingleTag = ({name, ...props}) => {
        return <Label.Group tag {...props}><NameToTagLabel name={name}/></Label.Group>
    }

    useEffect(() => {
        setTags([]);
        fetchTags();
    }, []);

    return {
        tags,
        tagNames,
        NameToTagLabel,
        TagsGroup,
        TagsLinkGroup,
        fetchTags,
        findTagByName,
        SingleTag,
        fuzzyMatchTagsByName
    }
}

export const useTagsInterval = () => {
    const tagsValue = useTags();
    const {fetchTags} = tagsValue;

    useRecurringTimeout(fetchTags, 30_000);

    return tagsValue
}

function EditTagRow({tag, onDelete, onEdit}) {
    const {SingleTag} = React.useContext(TagsContext);
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
    const countColor = (file_group_count + zim_entry_count) > 0 ? 'black' : 'grey';
    const countLabel = <Label color={countColor}>{file_group_count + zim_entry_count}</Label>;

    return <TableRow>
        <TableCell>{deleteConfirm}</TableCell>
        <TableCell>{editButton}</TableCell>
        <TableCell><SingleTag name={name}/></TableCell>
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

    // Return a random, but distinct Hex color.
    const getRandomColor = () => getDistinctColor((tags || []).map(i => i.color));

    const [open, setOpen] = React.useState(false);
    const [tagId, setTagId] = React.useState(null);
    const [tagName, setTagName] = React.useState('');
    const [tagColor, setTagColor] = React.useState(DEFAULT_TAG_COLOR);
    const textColor = contrastingColor(tagColor);
    const [tagNameError, setTagNameError] = React.useState(null);
    const disabled = !!!tagName || !!tagNameError;

    const setRandomColor = () => setTagColor(getRandomColor());

    // Open modal with random color.
    React.useEffect(() => {
        setRandomColor();
    }, [open]);

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
        // Change suggested color after save.
        setRandomColor();
    }

    const handleTagNameChange = (e, {value}) => {
        setTagName(value);
        // Tag names cannot contain these characters.
        const tagNameRegex = /[,<>:|"\\?*%!\n\r]/;
        setTagNameError(tagNameRegex.test(value) ? {content: 'Invalid Tag Name'} : null);
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
                               error={tagNameError}
                               onChange={handleTagNameChange}
                    />
                </Form>

                <HexColorPicker color={tagColor} onChange={setTagColor} style={{marginTop: '1em'}}/>

                <Grid>
                    <Grid.Row columns={2}>
                        <Grid.Column>
                            <Button
                                color='orange'
                                onClick={setRandomColor}
                                style={{marginTop: '2em'}}
                                type='button'
                            >Random</Button>
                        </Grid.Column>
                        <Grid.Column textAlign='right'>
                            <APIButton
                                color='violet'
                                size='big'
                                onClick={localSaveTag}
                                style={{marginTop: '2em'}}
                                disabled={disabled}
                            >Save</APIButton>
                        </Grid.Column>
                    </Grid.Row>
                </Grid>

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
                                  showAny = false,
                                  selectedTagNames = [],
                                  anyTag = false,
                                  onAdd = _.noop,
                                  onRemove = _.noop,
                                  onChange = _.noop,  // Expects to send: (tagNames, anyTag)
                                  closeAfterLimit = true,
                                  limit = null,
                                  disabled = false,
                              }) {
    // A button which displays a modal in which the user can add or remove tags.

    const {tagNames, TagsGroup} = React.useContext(TagsContext);
    const [open, setOpen] = React.useState(false);
    const [loading, setLoading] = React.useState(false);
    const [localTags, setLocalTags] = React.useState(selectedTagNames);

    const active = anyTag || (selectedTagNames && selectedTagNames.length > 0);

    const handleOpen = (e) => {
        if (e) {
            e.preventDefault();
        }
        setOpen(true);
    }

    const addTag = (name) => {
        setLoading(true);
        try {
            const newTags = [...(localTags || []), name];
            if (limit !== null && newTags.length > limit) {
                return;
            }
            setLocalTags(newTags);
            onAdd(name);
            onChange(newTags, null);
            if (closeAfterLimit && newTags && limit && newTags.length >= limit) {
                setOpen(false);
            }
        } finally {
            setLoading(false);
        }
    }

    const removeTag = (name) => {
        setLoading(true);
        try {
            const newTags = localTags.filter(i => i !== name);
            setLocalTags(newTags)
            onRemove(name);
            onChange(newTags, null);
        } finally {
            setLoading(false);
        }
    }

    const clearLocalTags = () => {
        if (!anyTag && (!localTags || (localTags && localTags.length === 0))) {
            console.debug('No tags to clear');
            return
        }

        console.debug('Clearing selected tags');
        onChange([], null);
        setLocalTags([]);
        setOpen(false);
    }

    const localOnAnyTag = () => {
        console.debug('Setting any tag');
        onChange([], true);
        setOpen(false);
    }

    const selectedTagsGroup = <TagsGroup tagNames={localTags} onClick={removeTag}/>;
    const unusedTags = _.difference(tagNames, localTags);
    const unusedTagsGroup = <TagsGroup tagNames={unusedTags} onClick={addTag}/>;
    const emptySelectedTags = limit === 1 ? 'Add only one tag below' : 'Add one or more tags below';

    return <>
        <Button
            icon={active ? 'tags' : 'tag'}
            color={active ? 'violet' : undefined}
            onClick={handleOpen}
            type="button"
            disabled={disabled}
        />
        <Modal closeIcon
               open={open}
               onOpen={(e) => handleOpen(e)}
               onClose={() => setOpen(false)}>
            <ModalContent>
                {loading && <Dimmer active><Loader/></Dimmer>}
                <Header as='h4'>Applied Tags</Header>

                {localTags && localTags.length > 0 ? selectedTagsGroup : emptySelectedTags}

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
                            {showAny && <Button color='violet' onClick={localOnAnyTag} floated='right'>Any</Button>}
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
                                 showAny = false,
                                 hideGroup = false,
                                 selectedTagNames = [],
                                 anyTag = false,
                                 onAdd = _.noop,
                                 onRemove = _.noop,
                                 onChange = _.noop,
                                 closeAfterLimit = true,
                                 limit = null,
                                 disabled = false,
                             }) => {
    // Provides a button to add tags to a list.  Displays the tags of that list.
    const {TagsLinkGroup} = React.useContext(TagsContext);

    if (!TagsLinkGroup) {
        // Tags have not been fetched.
        return <></>;
    }

    const button = <AddTagsButton
        hideEdit={hideEdit}
        showAny={showAny}
        selectedTagNames={selectedTagNames}
        onAdd={onAdd}
        onRemove={onRemove}
        onChange={onChange}
        closeAfterLimit={closeAfterLimit}
        anyTag={anyTag}
        limit={limit}
        disabled={disabled}
    />;

    if (hideGroup) {
        return button;
    }

    return <Grid columns={2}>
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
