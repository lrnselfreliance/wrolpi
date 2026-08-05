import React, {useEffect} from "react";
import {ApiDownError, deleteTag, getRecentTags, getTags, saveTag} from "./api";
import {
    APIButton,
    contrastingColor,
    ErrorMessage,
    fuzzyMatch,
    getDistinctColor,
    scrollToTopOfElement
} from "./components/Common";
import {
    Box,
    Button,
    Divider,
    Group,
    Header,
    Icon,
    IconButton,
    Label,
    Loading,
    Modal,
    Panel,
    Table,
    TextInput,
} from "./components/ui";
import _ from "lodash";
import {HexColorPicker} from "react-colorful";
import {useRecurringTimeout} from "./hooks/customHooks";
import {Media, QueryContext} from "./contexts/contexts";
import {Link, useNavigate} from "react-router";
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
            const body = await getTags();
            const t = body['tags'];
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

    // A single tag chip.  Tag colors are chosen by the user (stored per-tag), not by the
    // theme, so they are rendered with the raw hex value rather than a token -- but the
    // `wrolpi-label` className still gives them the theme's shape (and its night-mode
    // outline treatment, which keys off the same `--label-color` variable).
    const NameToTagLabel = ({name, to, ...props}) => {
        const tag = findTagByName(name);
        if (tag !== null && tag !== undefined) {
            const tagColor = tag['color'] || DEFAULT_TAG_COLOR;
            const textColor = contrastingColor(tagColor);
            const className = ['wrolpi-label', 'wrolpi-tag', props.onClick ? 'clickable' : '']
                .filter(Boolean).join(' ');
            return <span
                {...props} // onClick passed here.
                className={className}
                /*
                 * The contrasting text color goes in a custom property, not in `color`.  As
                 * `color` it was an inline declaration, which no stylesheet rule can outrank --
                 * so night, where a tag becomes an outline over a near-black page, still got
                 * the black text calculated for a bright tag's fill.  The tag was legible only
                 * by its border.  A custom property lets each theme decide instead.
                 */
                style={{...props['style'], ['--label-color']: tagColor, ['--label-text']: textColor}}
            >
                {name}
            </span>;
        }

        // No tags have been fetched.
        return <Label tag>{name}</Label>;
    }

    const TagsGroup = ({tagNames, onClick}) => {
        if (!tagNames || tagNames.length === 0) {
            return <React.Fragment/>;
        }
        return <Group gap={6}>
            {tagNames.map(i => <NameToTagLabel key={i} name={i} onClick={() => onClick(i)}/>)}
        </Group>
    }

    /*
     * The link carries no margin of its own.  It had `0.3em` either side, from when these were
     * Semantic labels that had none -- but a tag already reserves a `margin-left` in ui.css for
     * the point drawn outside its body, so that was 0.3em twice on top of the group's gap and
     * the point's own room.  Two tags sat 34.7px apart, of which the point needs 18.7px.
     *
     * Those are rendered px, measured in the browser at the default interface scale -- which is
     * what a user sees, and why they are the numbers worth recording.  The stylesheet states the
     * same margin in design px, as `1.0625rem`; 17 x 1.1 is the 18.7 above.
     */
    const TagLabelLink = ({name, props}) => {
        const to = getLocationStr({tag: name}, '/search');
        try {
            // We prefer to use Link to avoid reloading the page, check if React Router is available, so we can use it.
            useNavigate();
            return <Link to={to}>
                <NameToTagLabel name={name} {...props}/>
            </Link>
        } catch {
            // React Router is not available, use anchor.
            return <a href={to}>
                <NameToTagLabel name={name} {...props}/>
            </a>
        }
    }

    /*
     * Props here have two possible targets, and which one they take is part of the contract:
     *
     *   `style` and `className` dress the ROW.  Everything else reaches each CHIP, which is how
     *   `onClick` gets to a tag.
     *
     * `style` used to go down with the rest, so the dashboard's `marginTop` -- meant to space the
     * row below its heading -- landed on all 34 tags and became 7.7px of extra space between
     * every wrapped row of them.  `className` is named alongside it because it is the same kind
     * of thing and would fail the same way; a Mantine `Group` prop (`gap`, `wrap`, `justify`) or
     * a `data-*` meant for the row still would, so add it here rather than at a call site.
     */
    const TagsLinkGroup = ({tagNames, style, className, ...props}) => {
        if (!tagNames || tagNames.length === 0) {
            return <React.Fragment/>;
        }

        return <Group gap={6} style={style} className={className}>
            {tagNames.map(i => <TagLabelLink key={i} name={i} props={props}/>)}
        </Group>
    }

    const SingleTag = ({name, ...props}) => {
        return <Group gap={6} {...props}><NameToTagLabel name={name}/></Group>
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
    const {name, color, id, file_group_count, zim_entry_count, channel_count, domain_count} = tag;

    const deleteConfirm = <APIButton
        icon='trash'
        role='danger'
        confirmContent={`Are you sure you want to delete: ${name}?`}
        confirmButton='Delete'
        onClick={async () => onDelete(id, name)}
    />;
    const editButton = <IconButton icon='edit' label='Edit' role='primary'
                                   onClick={() => onEdit(name, color, id)}/>;

    // Individual count labels for tablet+
    const fileCountColor = file_group_count > 0 ? 'black' : 'grey';
    const fileCountLabel = <Label color={fileCountColor}>{file_group_count}</Label>;
    const zimCountColor = zim_entry_count > 0 ? 'black' : 'grey';
    const zimCountLabel = <Label color={zimCountColor}>{zim_entry_count}</Label>;
    const channelCountColor = channel_count > 0 ? 'black' : 'grey';
    const channelCountLabel = <Label color={channelCountColor}>{channel_count}</Label>;
    const domainCountColor = domain_count > 0 ? 'black' : 'grey';
    const domainCountLabel = <Label color={domainCountColor}>{domain_count}</Label>;

    // Combined count for mobile
    const totalCount = file_group_count + zim_entry_count + channel_count + domain_count;
    const totalCountColor = totalCount > 0 ? 'black' : 'grey';
    const totalCountLabel = <Label color={totalCountColor}>{totalCount}</Label>;

    return <Table.Row>
        <Table.Cell>{deleteConfirm}</Table.Cell>
        <Table.Cell>{editButton}</Table.Cell>
        <Table.Cell><SingleTag name={name}/></Table.Cell>
        <Media at='mobile'>
            {(className, renderChildren) => {
                return renderChildren ? <Table.Cell className={className}>{totalCountLabel}</Table.Cell> : null;
            }}
        </Media>
        <Media greaterThanOrEqual='tablet'>
            {(className, renderChildren) => {
                return renderChildren ? <>
                        <Table.Cell className={className}>{fileCountLabel}</Table.Cell>
                        <Table.Cell className={className}>{zimCountLabel}</Table.Cell>
                        <Table.Cell className={className}>{channelCountLabel}</Table.Cell>
                        <Table.Cell className={className}>{domainCountLabel}</Table.Cell>
                    </>
                    : null;
            }}
        </Media>
    </Table.Row>
}

function EditTagsModal() {
    const {fetchTags, tags} = React.useContext(TagsContext);

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

    const handleTagNameChange = (e) => {
        const value = e.target.value;
        setTagName(value);
        // Tag names cannot contain these characters.
        const tagNameRegex = /[,<>:|"\\?*%!\n\r]/;
        setTagNameError(tagNameRegex.test(value) ? 'Invalid Tag Name' : null);
    }

    const tableHeaders = [
        {key: 'delete', text: 'Delete', sortBy: null, width: 1},
        {key: 'edit', text: 'Edit', sortBy: null, width: 1},
        {key: 'name', text: 'Name', sortBy: 'name', width: 4},
        {key: 'files', text: 'Files', sortBy: 'file_group_count', width: 2},
        {key: 'zims', text: 'Zims', sortBy: 'zim_entry_count', width: 2},
        {key: 'channels', text: 'Channels', sortBy: 'channel_count', width: 2},
        {key: 'domains', text: 'Domains', sortBy: 'domain_count', width: 2},
    ];
    const mobileTableHeaders = [
        {key: 'delete', text: 'Delete', sortBy: null, width: 2},
        {key: 'edit', text: 'Edit', sortBy: null, width: 2},
        {key: 'name', text: 'Name', sortBy: 'name', width: 8},
        {key: 'count', text: 'Count', sortBy: i => i['file_group_count'] + i['zim_entry_count'] + i['channel_count'] + i['domain_count'], width: 4},
    ];

    return <>
        <Modal size='large' open={open} onClose={localOnClose}>
            <Modal.Header>Edit Tags</Modal.Header>
            <div id='editModalContent'>
                <Group gap={6}>
                    {/*
                      * `--label-text`, not `color`, for the same reason as the chip itself:
                      * inline `color` cannot be overridden, so in night this preview showed
                      * black text on a transparent outline over a near-black page.  It is the
                      * preview of the color being chosen, so being honest about how the tag
                      * will actually look matters here more than anywhere.
                      */}
                    <span
                        className='wrolpi-label wrolpi-tag'
                        style={{['--label-color']: tagColor, ['--label-text']: textColor}}
                    >
                        {tagName || 'Example Tag'}
                    </span>
                </Group>

                <TextInput
                    required
                    autoFocus
                    autoComplete='off'
                    label={<b>Tag Name</b>}
                    placeholder='Unique name'
                    value={tagName}
                    error={tagNameError}
                    onChange={handleTagNameChange}
                    style={{marginTop: '1em'}}
                />

                <HexColorPicker color={tagColor} onChange={setTagColor} style={{marginTop: '1em'}}/>

                <Group justify='space-between' style={{marginTop: '2em'}}>
                    <Button role='cancel' type='button' onClick={setRandomColor}>Random</Button>
                    <APIButton role='save' onClick={localSaveTag} disabled={disabled}>Save</APIButton>
                </Group>

                <Divider/>

                <Media at='mobile'>
                    <SortableTable
                        data={tags}
                        rowFunc={(i, sortData) => <EditTagRow key={i['name']} tag={i} onDelete={localDeleteTag}
                                                              onEdit={localEditTag}/>}
                        rowKey='name'
                        tableHeaders={mobileTableHeaders}
                    />
                </Media>
                <Media greaterThanOrEqual='tablet'>
                    <SortableTable
                        data={tags}
                        rowFunc={(i, sortData) => <EditTagRow key={i['name']} tag={i} onDelete={localDeleteTag}
                                                              onEdit={localEditTag}/>}
                        rowKey='name'
                        tableHeaders={tableHeaders}
                    />
                </Media>
            </div>
        </Modal>
        <Button role='primary' onClick={() => setOpen(true)} disabled={tags === undefined}>
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
                                  filterByOverlap = false,
                              }) {
    // A button which displays a modal in which the user can add or remove tags.

    const {tagNames, TagsGroup} = React.useContext(TagsContext);
    const [open, setOpen] = React.useState(false);
    const [loading, setLoading] = React.useState(false);
    const [localTags, setLocalTags] = React.useState(selectedTagNames);
    const [filterText, setFilterText] = React.useState('');
    const [frequentTags, setFrequentTags] = React.useState([]);
    const [frequentTagsLabel, setFrequentTagsLabel] = React.useState('Recent Tags');
    const [hasSelectedTag, setHasSelectedTag] = React.useState(false);
    const [overlappingTags, setOverlappingTags] = React.useState(null);
    const filterInputRef = React.useRef(null);

    // Sync localTags with selectedTagNames when it changes from parent
    React.useEffect(() => {
        setLocalTags(selectedTagNames);
    }, [selectedTagNames]);

    const fetchOverlappingFilter = React.useCallback((currentTags) => {
        if (filterByOverlap && currentTags && currentTags.length > 0) {
            getTags(currentTags).then(body => {
                setOverlappingTags(body['overlapping_tag_names'] || []);
            });
        } else {
            setOverlappingTags(null);
        }
    }, [filterByOverlap]);

    React.useEffect(() => {
        if (open) {
            setFilterText('');
            setHasSelectedTag(false);
            fetchOverlappingFilter(selectedTagNames);
            if (!filterByOverlap) {
                if (selectedTagNames && selectedTagNames.length === 1) {
                    setHasSelectedTag(true);
                    getTags(selectedTagNames[0]).then(body => {
                        const coTags = body['overlapping_tag_names'] || [];
                        if (coTags.length > 0) {
                            setFrequentTags(coTags);
                            setFrequentTagsLabel('Frequent Tags');
                        } else {
                            setFrequentTags([]);
                            setFrequentTagsLabel('Recent Tags');
                        }
                    });
                } else if (!selectedTagNames || selectedTagNames.length === 0) {
                    setFrequentTagsLabel('Recent Tags');
                    getRecentTags().then(names => setFrequentTags(names));
                } else {
                    setFrequentTags([]);
                }
            }
            const timeout = setTimeout(() => {
                if (filterInputRef.current && window.innerWidth >= 700) {
                    filterInputRef.current.focus();
                }
            }, 100);
            return () => clearTimeout(timeout);
        }
    }, [open]);

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
            setFilterText('');
            onAdd(name);
            onChange(newTags, null);
            fetchOverlappingFilter(newTags);
            if (!filterByOverlap && !hasSelectedTag) {
                setHasSelectedTag(true);
                getTags(name).then(body => {
                    const coTags = body['overlapping_tag_names'] || [];
                    if (coTags.length > 0) {
                        setFrequentTags(coTags);
                        setFrequentTagsLabel('Frequent Tags');
                    } else {
                        setFrequentTags([]);
                    }
                });
            }
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
            fetchOverlappingFilter(newTags);
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
    let unusedTags = _.difference(tagNames, localTags);
    if (overlappingTags !== null) {
        unusedTags = unusedTags.filter(name => overlappingTags.includes(name));
    }
    const filteredUnusedTags = filterText
        ? unusedTags.filter(name => name.toLowerCase().includes(filterText.toLowerCase()))
        : unusedTags;
    const unusedTagsGroup = <TagsGroup tagNames={filteredUnusedTags} onClick={addTag}/>;
    const emptySelectedTags = limit === 1 ? 'Add only one tag below' : 'Add one or more tags below';
    const visibleFrequentTags = frequentTags.filter(name => !(localTags || []).includes(name));
    const hideFrequentTags = filterByOverlap && localTags && localTags.length > 0;

    return <>
        <IconButton
            icon={active ? 'tags' : 'tag'}
            label={active ? 'Tags applied' : 'Add tag'}
            role='primary'
            onClick={handleOpen}
            type='button'
            disabled={disabled}
        />
        <Modal size='small' open={open} onClose={() => setOpen(false)}>
            <Modal.Content>
                {loading && <Loading size='xs'>Updating tags…</Loading>}
                <Header as='h4'>Applied Tags</Header>

                {localTags && localTags.length > 0 ? selectedTagsGroup : emptySelectedTags}

                {!hideFrequentTags && visibleFrequentTags.length > 0 && <>
                    <Divider/>
                    <Header as='h5'>{frequentTagsLabel}</Header>
                    <TagsGroup tagNames={visibleFrequentTags} onClick={addTag}/>
                </>}

                <Divider/>

                <TextInput
                    ref={filterInputRef}
                    placeholder='Filter tags...'
                    value={filterText}
                    onChange={(e) => setFilterText(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter' && filteredUnusedTags.length === 1) {
                            e.preventDefault();
                            addTag(filteredUnusedTags[0]);
                        }
                    }}
                    leftSection={<Icon name='search'/>}
                    style={{marginBottom: '0.5em'}}
                />

                {unusedTags && unusedTags.length > 0
                    ? unusedTagsGroup
                    : (overlappingTags !== null && tagNames.length > 0
                        ? 'No overlapping tags'
                        : 'You have no tags')}
            </Modal.Content>
            <Modal.Actions>
                <Group justify='space-between'>
                    <Box>
                        {!hideEdit && <EditTagsModal/>}
                    </Box>
                    <Group gap={8}>
                        <Button role='cancel' onClick={() => clearLocalTags()}>Clear</Button>
                        {showAny && <Button role='primary' onClick={localOnAnyTag}>Any</Button>}
                        <Button role='cancel' onClick={() => setOpen(false)}>Close</Button>
                    </Group>
                </Group>
            </Modal.Actions>
        </Modal>
    </>
}


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
                                 filterByOverlap = false,
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
        filterByOverlap={filterByOverlap}
    />;

    if (hideGroup) {
        return button;
    }

    return <Group align='flex-start' wrap='nowrap' gap={8}>
        {button}
        <Box style={{flex: 1}}>
            <TagsLinkGroup tagNames={selectedTagNames}/>
        </Box>
    </Group>
}

export const TagsDashboard = () => {
    const {tagNames, TagsLinkGroup} = React.useContext(TagsContext);

    const tagPlaceholder = <Box style={{width: 100}}><TagPlaceholder/></Box>;
    let availableTagsGroup = <Group gap={12}>
        {tagPlaceholder}
        {tagPlaceholder}
        {tagPlaceholder}
    </Group>;
    if (tagNames && tagNames.length >= 1) {
        availableTagsGroup = <TagsLinkGroup tagNames={tagNames} style={{marginTop: '0.5em'}}/>;
    } else if (tagNames === undefined) {
        availableTagsGroup = <ErrorMessage>Could not fetch tags</ErrorMessage>
    }

    return <Panel>
        <Header as='h2'>Tags</Header>
        {availableTagsGroup}

        <Divider/>

        <EditTagsModal/>
    </Panel>
}

export const TagsProvider = (props) => {
    const tagsValue = useTagsInterval();

    return <TagsContext.Provider value={tagsValue}>
        {props.children}
    </TagsContext.Provider>
}
