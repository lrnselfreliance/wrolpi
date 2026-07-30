import React, {useContext, useEffect, useState, forwardRef, HTMLAttributes, CSSProperties} from 'react';
import {ThemeContext} from "../contexts/contexts";
import {
    Accordion as SAccordion,
    AccordionContent as SAccordionContent,
    AccordionTitle as SAccordionTitle,
    Breadcrumb as SBreadcrumb,
    Button as SButton,
    ButtonGroup as SButtonGroup,
    Card as SCard,
    Divider as SDivider,
    Form as SForm,
    FormField as SFormField,
    FormGroup as SFormGroup,
    FormInput as SFormInput,
    Header as SHeader,
    Icon as SIcon,
    List as SList,
    ListContent as SListContent,
    ListDescription as SListDescription,
    ListHeader as SListHeader,
    ListIcon as SListIcon,
    ListItem as SListItem,
    Loader as SLoader,
    Menu as SMenu,
    MenuItem as SMenuItem,
    MenuHeader as SMenuHeader,
    MenuMenu as SMenuMenu,
    Modal as SModal,
    ModalActions as SModalActions,
    ModalContent as SModalContent,
    ModalDescription as SModalDescription,
    ModalHeader as SModalHeader,
    Placeholder as SPlaceholder,
    Popup as SPopup,
    Progress as SProgress,
    Ref as SRef,
    Segment as SSegment,
    Statistic as SStatistic,
    StatisticGroup as SStatisticGroup,
    Tab as STab,
    Table as STable,
    TableBody as STableBody,
    TableCell as STableCell,
    TableFooter as STableFooter,
    TableHeader as STableHeader,
    TableHeaderCell as STableHeaderCell,
    TableRow as STableRow,
    TabPane as STabPane,
    TextArea as STextArea,
    AccordionContentProps,
    AccordionProps,
    AccordionTitleProps,
    BreadcrumbProps,
    ButtonProps,
    ButtonGroupProps,
    CardProps as SCardProps,
    DividerProps,
    FormProps,
    FormFieldProps,
    FormGroupProps,
    FormInputProps,
    HeaderProps,
    IconProps,
    ListProps,
    ListItemProps,
    ListIconProps,
    ListContentProps,
    ListHeaderProps,
    ListDescriptionProps,
    LoaderProps,
    MenuProps,
    MenuItemProps,
    MenuMenuProps,
    ModalProps,
    ModalActionsProps,
    ModalContentProps,
    ModalDescriptionProps,
    ModalHeaderProps,
    PlaceholderProps,
    PopupProps,
    ProgressProps,
    SegmentProps,
    StatisticProps,
    StatisticGroupProps,
    TabProps,
    TableProps,
    TableBodyProps,
    TableCellProps,
    TableFooterProps,
    TableHeaderProps,
    TableHeaderCellProps,
    TableRowProps,
    TabPaneProps,
    TextAreaProps,
} from "semantic-ui-react";
import {MantineProvider} from "@mantine/core";
import {Notifications} from "@mantine/notifications";
import {cssVariablesResolver, mantineTheme} from "../themes/mantine";
import {ColorToSemanticHexColor} from "./Vars";
import _ from "lodash";
import {ThemeContextValue, ThemeName, SavedThemeName} from "../types/theme";

export const darkTheme = 'dark';
export const lightTheme = 'light';
export const nightTheme = 'night';
export const amberTheme = 'amber';
export const defaultTheme = lightTheme;
export const systemTheme = 'system';
export const themeSessionKey = 'color-scheme';

// Every theme a user can apply, in the order the theme picker offers them.
export const themeNames: ThemeName[] = [lightTheme, darkTheme, nightTheme, amberTheme];
// Themes built on a dark background.  Semantic components are `inverted` in these.
const darkThemes: ThemeName[] = [darkTheme, nightTheme, amberTheme];
// Themes a user must choose deliberately; `prefers-color-scheme` never picks them.
const explicitOnlyThemes: ThemeName[] = [nightTheme, amberTheme];

export const isDarkTheme = (theme: ThemeName): boolean => darkThemes.includes(theme);

const isThemeName = (value: unknown): value is ThemeName => themeNames.includes(value as ThemeName);

/** Resolve the saved preference to the theme that should be applied right now. */
export const resolveTheme = (saved: SavedThemeName): ThemeName => {
    if (isThemeName(saved)) {
        return saved;
    }
    // `system`, null, or a value written by an older version.
    const prefersDark = typeof window.matchMedia === 'function'
        && window.matchMedia('(prefers-color-scheme: dark)').matches;
    return prefersDark ? darkTheme : lightTheme;
}

const readSavedTheme = (): SavedThemeName => {
    try {
        const value = localStorage.getItem(themeSessionKey);
        if (isThemeName(value) || value === systemTheme) {
            return value;
        }
    } catch (e) {
        // localStorage can throw when cookies/storage are blocked.
        console.error('Unable to read the saved theme', e);
    }
    return null;
}

interface ThemeProviderProps {
    children: React.ReactNode;
}

export function ThemeProvider({children, ...props}: ThemeProviderProps) {
    if (!_.isEmpty(props)) {
        console.log(props);
        console.error('ThemeWrapper does not support props!');
    }

    // savedTheme is the user's preference: a theme name, `system`, or null (never chosen).
    const [savedTheme, setSavedTheme] = useState<SavedThemeName>(readSavedTheme);
    // theme is what is currently applied.
    const [theme, setThemeName] = useState<ThemeName>(() => resolveTheme(readSavedTheme()));

    // `data-theme` on <html> is what the token CSS keys off of.  index.html stamps it before
    // first paint from the same localStorage value, so the first render already matches.
    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme);
    }, [theme]);

    // Follow the OS preference only while the user has not chosen a specific theme.
    useEffect(() => {
        if (isThemeName(savedTheme) || typeof window.matchMedia !== 'function') {
            return;
        }
        const query = window.matchMedia('(prefers-color-scheme: dark)');
        const onChange = () => setThemeName(resolveTheme(savedTheme));
        query.addEventListener('change', onChange);
        return () => query.removeEventListener('change', onChange);
    }, [savedTheme]);

    const saveTheme = (value: SavedThemeName) => {
        setSavedTheme(value);
        try {
            if (value === null) {
                localStorage.removeItem(themeSessionKey);
            } else {
                localStorage.setItem(themeSessionKey, value);
            }
        } catch (e) {
            console.error('Unable to save the theme', e);
        }
    }

    /** Apply and persist a theme.  Pass `system` to follow the OS preference. */
    const setTheme = (value: SavedThemeName) => {
        if (value !== systemTheme && value !== null && !isThemeName(value)) {
            console.error(`Unknown theme! ${value}`);
            return;
        }
        saveTheme(value);
        setThemeName(resolveTheme(value));
    }

    // Retained for callers written against the old two-theme API.
    const setDarkTheme = (save = false) => {
        setThemeName(darkTheme);
        if (save) saveTheme(darkTheme);
    }

    const setLightTheme = (save = false) => {
        setThemeName(lightTheme);
        if (save) saveTheme(lightTheme);
    }

    const cycleSavedTheme = (e?: React.MouseEvent) => {
        // Cycle: System -> Light -> Dark -> Night -> Amber -> System
        if (e) {
            e.preventDefault();
        }
        const order: SavedThemeName[] = [systemTheme, ...themeNames];
        const current = order.indexOf(isThemeName(savedTheme) ? savedTheme : systemTheme);
        setTheme(order[(current + 1) % order.length]);
    }

    const dark = isDarkTheme(theme);

    // Compatibility layer for components which have not been migrated to tokens yet.  Semantic
    // has no concept of the night/amber themes, so they reuse its dark treatment while pulling
    // their colors from the tokens.  These values disappear with the last Semantic component.
    const i = dark ? {inverted: true} : {inverted: undefined};
    const inverted = dark ? 'inverted' : '';
    let s: {style?: CSSProperties} = {};
    let t: {style?: CSSProperties} = {};
    if (theme === darkTheme) {
        s = {style: {backgroundColor: '#1B1C1D', color: '#dddddd'}};
        t = {style: {color: '#eeeeee'}};
    } else if (explicitOnlyThemes.includes(theme)) {
        s = {style: {backgroundColor: 'var(--panel)', color: 'var(--text)'}};
        t = {style: {color: 'var(--text)'}};
    }

    const themeValue: ThemeContextValue = {
        i, // Used for Semantic elements which support "inverted".
        s, // Used to invert the style some elements.
        t, // Used to invert text.
        inverted, // Used to add "invert" to className.
        theme,
        savedTheme,
        isDark: dark,
        setTheme,
        setDarkTheme,
        setLightTheme,
        cycleSavedTheme,
    };

    // Mantine's own scheme decides the surfaces its internals use (overlays, scrollbars,
    // focus rings).  Night and amber are neither of its two schemes, so they ride on dark
    // and take their actual colors from our tokens.  This is the theme `base` flag.
    return <ThemeContext.Provider value={themeValue}>
        <MantineProvider
            theme={mantineTheme}
            cssVariablesResolver={cssVariablesResolver}
            forceColorScheme={dark ? 'dark' : 'light'}
        >
            <Notifications position='bottom-right' limit={5}/>
            {children}
        </MantineProvider>
    </ThemeContext.Provider>
}

// Simple wrappers for Semantic UI elements to use the current theme.

const invertedNull = <T extends {inverted?: boolean | null}>(props: T): T => {
    if (props['inverted'] === true) {
        return {...props, inverted: null};
    }
    return props;
}

const defaultGrey = <T extends object>(props: T, inverted: boolean): T => {
    // Some elements look softer when grey, use grey only if another color is not provided.
    if (inverted) {
        return {color: 'grey', ...props} as T;
    }
    return props;
}

// ----------------------------------------------------------------------------
// Accordion Compound Component
// ----------------------------------------------------------------------------

type AccordionTitleComponent = React.FC<AccordionTitleProps>;
type AccordionContentComponent = React.FC<AccordionContentProps>;

interface AccordionComponent extends React.FC<AccordionProps> {
    Title: AccordionTitleComponent;
    Content: AccordionContentComponent;
}

const AccordionTitle: AccordionTitleComponent = (props) => {
    return <SAccordionTitle {...props}/>
};

const AccordionContent: AccordionContentComponent = (props) => {
    return <SAccordionContent {...props}/>
};

const AccordionBase: React.FC<AccordionProps> = (props) => {
    const {i, inverted} = useContext(ThemeContext);
    const mergedProps = defaultGrey({...i, ...props}, !!inverted);
    return <SAccordion {...mergedProps}/>
};

export const Accordion: AccordionComponent = Object.assign(AccordionBase, {
    Title: AccordionTitle,
    Content: AccordionContent,
});

// ----------------------------------------------------------------------------
// Button Compound Component
// ----------------------------------------------------------------------------

type ButtonGroupComponent = React.FC<ButtonGroupProps>;

interface ButtonComponent extends React.ForwardRefExoticComponent<ButtonProps & React.RefAttributes<any>> {
    Group: ButtonGroupComponent;
}

const ButtonGroup: ButtonGroupComponent = (props) => {
    return <SButtonGroup {...props}/>
};

const ButtonBase = forwardRef<any, ButtonProps>((props, ref) => {
    const {i, inverted} = useContext(ThemeContext);
    const mergedProps = defaultGrey({...i, ...props}, !!inverted);
    // SButton is a class component, so a forwarded `ref` would resolve to the class instance rather than the DOM
    // node. Semantic UI's Modal/Popup use the trigger's ref with `node.contains(...)`, which throws on a non-DOM
    // value. Wrap in Ref (findDOMNode) so the forwarded ref always resolves to the underlying <button> element.
    if (ref) {
        return <SRef innerRef={ref}><SButton {...mergedProps}/></SRef>
    }
    return <SButton {...mergedProps}/>
});
ButtonBase.displayName = 'ButtonBase';

export const Button: ButtonComponent = Object.assign(ButtonBase, {
    Group: ButtonGroup,
});

export function Divider(props: DividerProps) {
    const {i} = useContext(ThemeContext);
    return <SDivider {...i} {...props}/>
}

export function Header(props: HeaderProps) {
    const {t} = useContext(ThemeContext);
    // Merge the caller's style on top of the theme's text style; a bare `{...props}`
    // would let an incoming `style` prop replace (and drop) the theme's text color.
    return <SHeader {...t} {...props} style={{...t.style, ...props.style}}/>
}

export function Icon(props: IconProps) {
    const {i} = useContext(ThemeContext);
    return <SIcon {...i} {...props}/>
}

export function Loader(props: LoaderProps) {
    const {i} = useContext(ThemeContext);
    return <SLoader {...i} {...props}/>
}

// Menu is a compound component (Menu.Item / Menu.Header / Menu.Menu) so callers get the same API as Semantic's
// Menu while inheriting the theme.  The parent menu is `inverted` in dark mode so item text stays readable.
const MenuBase: React.FC<MenuProps> = (props) => {
    const {i} = useContext(ThemeContext);
    return <SMenu {...i} {...props}/>;
};

const MenuItem: React.FC<MenuItemProps> = (props) => <SMenuItem {...props}/>;
const MenuHeader: React.FC<MenuItemProps> = (props) => <SMenuHeader {...props}/>;
const MenuMenu: React.FC<MenuMenuProps> = (props) => <SMenuMenu {...props}/>;

interface MenuComponent extends React.FC<MenuProps> {
    Item: React.FC<MenuItemProps>;
    Header: React.FC<MenuItemProps>;
    Menu: React.FC<MenuMenuProps>;
}

export const Menu: MenuComponent = Object.assign(MenuBase, {
    Item: MenuItem,
    Header: MenuHeader,
    Menu: MenuMenu,
});

export function Placeholder(props: PlaceholderProps) {
    const {i} = useContext(ThemeContext);
    return <SPlaceholder {...i} {...props}/>
}

export function Popup(props: PopupProps) {
    const {i} = useContext(ThemeContext);
    return <SPopup {...i} style={{border: '1px solid grey'}} {...props}/>
}

// Bar colors that always need dark percent text (light bars in any theme).
const PROGRESS_BAR_COLORS = ['yellow', 'olive', 'teal'];
// Bar colors that need dark percent text only in dark mode (inverted makes bar lighter).
const DARK_MODE_PROGRESS_BAR_COLORS = ['grey', 'blue'];

export function Progress(props: ProgressProps) {
    const {i, inverted} = useContext(ThemeContext);
    const classes = [props.className || ''];
    if (inverted) classes.push('inverted-progress-text');
    const color = props.color as string;
    if (PROGRESS_BAR_COLORS.includes(color) || (inverted && DARK_MODE_PROGRESS_BAR_COLORS.includes(color))) {
        classes.push('light-bar-progress-text');
    }
    return <SProgress {...i} {...props} className={classes.join(' ').trim()}/>
}

export function Segment(props: SegmentProps) {
    const {i} = useContext(ThemeContext);
    return <SSegment {...i} {...props}/>
}

// Table is now a compound component - see COMPOUND COMPONENTS section below

export function TextArea(props: TextAreaProps) {
    const {i} = useContext(ThemeContext);
    const mergedProps = invertedNull({...i, ...props});
    return <STextArea {...mergedProps}/>
}

// ============================================================================
// COMPOUND COMPONENTS
// ============================================================================

// ----------------------------------------------------------------------------
// Modal Compound Component
// ----------------------------------------------------------------------------

type ModalActionsComponent = React.FC<ModalActionsProps>;
type ModalContentComponent = React.FC<ModalContentProps>;
type ModalDescriptionComponent = React.FC<ModalDescriptionProps>;
type ModalHeaderComponent = React.FC<ModalHeaderProps>;

interface ModalComponent extends React.FC<ModalProps> {
    Actions: ModalActionsComponent;
    Content: ModalContentComponent;
    Description: ModalDescriptionComponent;
    Header: ModalHeaderComponent;
}

const ModalActions: ModalActionsComponent = (props) => {
    const {inverted} = useContext(ThemeContext);
    return <SModalActions {...props} className={`${inverted}`}/>
};

const ModalContent: ModalContentComponent = (props) => {
    const {inverted} = useContext(ThemeContext);
    return <SModalContent {...props} className={`${inverted}`}/>
};

const ModalDescription: ModalDescriptionComponent = (props) => {
    const {inverted} = useContext(ThemeContext);
    return <SModalDescription {...props} className={`${inverted}`}/>
};

const ModalHeader: ModalHeaderComponent = (props) => {
    const {inverted} = useContext(ThemeContext);
    return <SModalHeader {...props} className={`${inverted}`}>
        {props.children}
    </SModalHeader>
};

const ModalBase: React.FC<ModalProps> = (props) => {
    const {inverted} = useContext(ThemeContext);
    return <SModal {...props} className={`${inverted}`}/>
};

export const Modal: ModalComponent = Object.assign(ModalBase, {
    Actions: ModalActions,
    Content: ModalContent,
    Description: ModalDescription,
    Header: ModalHeader,
});

// ----------------------------------------------------------------------------
// List Compound Component
// ----------------------------------------------------------------------------
// Semantic's List supports `inverted`; the inverted class on the parent handles the item text,
// but List.Icon must also receive `inverted` so its color flips in dark mode (the parent's
// inverted class alone does not restyle the icon).

interface ListComponent extends React.FC<ListProps> {
    Item: React.FC<ListItemProps>;
    Icon: React.FC<ListIconProps>;
    Content: React.FC<ListContentProps>;
    Header: React.FC<ListHeaderProps>;
    Description: React.FC<ListDescriptionProps>;
}

const ListBase: React.FC<ListProps> = (props) => {
    const {i} = useContext(ThemeContext);
    return <SList {...i} {...props}/>
};

const ListIcon: React.FC<ListIconProps> = (props) => {
    const {i} = useContext(ThemeContext);
    return <SListIcon {...i} {...props}/>
};

export const List: ListComponent = Object.assign(ListBase, {
    Item: SListItem,
    Icon: ListIcon,
    Content: SListContent,
    Header: SListHeader,
    Description: SListDescription,
});

// ----------------------------------------------------------------------------
// Confirm Component
// ----------------------------------------------------------------------------

export interface ConfirmProps {
    open: boolean;
    header?: string;
    content?: string | React.ReactNode;
    confirmButton?: string;
    cancelButton?: string;
    onConfirm?: () => void;
    onCancel?: () => void;
    onClose?: () => void;
    size?: 'mini' | 'tiny' | 'small' | 'large' | 'fullscreen';
}

export const Confirm: React.FC<ConfirmProps> = ({
    open,
    header,
    content,
    confirmButton = 'OK',
    cancelButton = 'Cancel',
    onConfirm,
    onCancel,
    onClose,
    size = 'tiny',
}) => {
    const {i} = useContext(ThemeContext);

    return (
        <Modal open={open} onClose={onClose} size={size} className="themed-confirm">
            {header && <Modal.Header>{header}</Modal.Header>}
            <Modal.Content>
                {typeof content === 'string' ? <p>{content}</p> : content}
            </Modal.Content>
            <Modal.Actions>
                <Button onClick={onCancel} {...i}>{cancelButton}</Button>
                <Button onClick={onConfirm} color="green" {...i}>{confirmButton}</Button>
            </Modal.Actions>
        </Modal>
    );
};

// ----------------------------------------------------------------------------
// Form Compound Component
// ----------------------------------------------------------------------------

type FormFieldComponent = React.FC<FormFieldProps>;
type FormGroupComponent = React.FC<FormGroupProps>;
type FormInputComponent = React.FC<FormInputProps>;

interface FormComponent extends React.FC<FormProps> {
    Field: FormFieldComponent;
    Group: FormGroupComponent;
    Input: FormInputComponent;
}

const FormField: FormFieldComponent = (props) => {
    const {i} = useContext(ThemeContext);
    const mergedProps = invertedNull({...i, ...props});
    return <SFormField {...mergedProps}/>
};

const FormGroup: FormGroupComponent = (props) => {
    const {i} = useContext(ThemeContext);
    const mergedProps = invertedNull({...i, ...props});
    return <SFormGroup {...mergedProps}/>
};

const FormInput: FormInputComponent = (props) => {
    const {i} = useContext(ThemeContext);
    return <SFormInput {...i} {...props}/>
};

const FormBase: React.FC<FormProps> = (props) => {
    const {i} = useContext(ThemeContext);
    return <SForm {...i} {...props}/>
};

export const Form: FormComponent = Object.assign(FormBase, {
    Field: FormField,
    Group: FormGroup,
    Input: FormInput,
});

// ----------------------------------------------------------------------------
// Card Compound Component
// ----------------------------------------------------------------------------

interface CardIconProps extends HTMLAttributes<HTMLDivElement> {
    onClick?: () => void;
    children?: React.ReactNode;
}

type CardIconComponent = React.FC<CardIconProps>;

interface CardProps extends Omit<SCardProps, 'color'> {
    color?: string;
}

interface CardComponent extends React.FC<CardProps> {
    Icon: CardIconComponent;
}

const CardIcon: CardIconComponent = ({onClick, children, ...props}) => {
    const {inverted} = useContext(ThemeContext);
    const cardIcon = <center className={`card-icon ${inverted}`} {...props}>{children}</center>;
    if (onClick) {
        return <div onClick={onClick} className='clickable'>
            {cardIcon}
        </div>
    } else {
        return cardIcon;
    }
};

const CardBase: React.FC<CardProps> = ({color, ...props}) => {
    const {inverted} = useContext(ThemeContext);

    const style: CSSProperties = props.style || {};
    const emphasisColor = ColorToSemanticHexColor(color);
    if (emphasisColor) {
        // Increase drop shadow to emphasize color.
        const borderColor = inverted ? '#888' : '#ddd';
        style.boxShadow = `0 0 0 2px ${borderColor}, 0 5px 0 0 ${emphasisColor}, 0 0px 3px 0 #d4d4d5`;
    }
    return <SCard {...props} style={style}/>
};

export const Card: CardComponent = Object.assign(CardBase, {
    Icon: CardIcon,
});

// ----------------------------------------------------------------------------
// Tab Compound Component
// ----------------------------------------------------------------------------

type TabPaneComponent = React.FC<TabPaneProps>;

interface TabComponent extends React.FC<TabProps> {
    Pane: TabPaneComponent;
}

const TabPane: TabPaneComponent = (props) => {
    const {i} = useContext(ThemeContext);
    return <STabPane {...i} {...props}/>
};

const TabBase: React.FC<TabProps> = (props) => {
    const {i} = useContext(ThemeContext);
    const mergedProps = invertedNull({...i, ...props});
    return <STab {...mergedProps}/>
};

export const Tab: TabComponent = Object.assign(TabBase, {
    Pane: TabPane,
});

// ----------------------------------------------------------------------------
// Statistic Compound Component
// ----------------------------------------------------------------------------

type StatisticGroupComponent = React.FC<StatisticGroupProps>;

interface StatisticComponent extends React.FC<StatisticProps> {
    Group: StatisticGroupComponent;
}

const StatisticGroup: StatisticGroupComponent = (props) => {
    const {i} = useContext(ThemeContext);
    const style: CSSProperties = {...props.style, marginLeft: 0, marginRight: 0};
    return <SStatisticGroup {...i} {...props} style={style}/>
};

const StatisticBase: React.FC<StatisticProps> = (props) => {
    const {i, inverted} = useContext(ThemeContext);
    const mergedProps = defaultGrey({...i, ...props}, !!inverted);
    return <SStatistic {...mergedProps}/>
};

export const Statistic: StatisticComponent = Object.assign(StatisticBase, {
    Group: StatisticGroup,
});

// ----------------------------------------------------------------------------
// Breadcrumb Compound Component
// ----------------------------------------------------------------------------

interface BreadcrumbDividerProps {
    icon?: string;
}

type BreadcrumbDividerComponent = React.FC<BreadcrumbDividerProps>;

interface BreadcrumbComponent extends React.FC<BreadcrumbProps> {
    Divider: BreadcrumbDividerComponent;
}

const BreadcrumbDivider: BreadcrumbDividerComponent = ({icon, ...props}) => {
    const {inverted} = useContext(ThemeContext);

    // TODO this only handles icons for now.
    const className = `divider icon ${inverted} ${icon || ''}`;
    return <i aria-hidden="true" className={className}></i>
};

const BreadcrumbBase: React.FC<BreadcrumbProps> = (props) => {
    const {t} = useContext(ThemeContext);
    return <SBreadcrumb {...props} {...t}/>
};

export const Breadcrumb: BreadcrumbComponent = Object.assign(BreadcrumbBase, {
    Divider: BreadcrumbDivider,
});

// ----------------------------------------------------------------------------
// Table Compound Component
// ----------------------------------------------------------------------------

type TableBodyComponent = React.FC<TableBodyProps>;
type TableCellComponent = React.FC<TableCellProps>;
type TableFooterComponent = React.FC<TableFooterProps>;
type TableHeaderComponent = React.FC<TableHeaderProps>;
type TableHeaderCellComponent = React.FC<TableHeaderCellProps>;
type TableRowComponent = React.FC<TableRowProps>;

interface TableComponent extends React.FC<TableProps> {
    Body: TableBodyComponent;
    Cell: TableCellComponent;
    Footer: TableFooterComponent;
    Header: TableHeaderComponent;
    HeaderCell: TableHeaderCellComponent;
    Row: TableRowComponent;
}

const TableBody: TableBodyComponent = (props) => {
    return <STableBody {...props}/>
};

const TableCell: TableCellComponent = (props) => {
    return <STableCell {...props}/>
};

const TableFooter: TableFooterComponent = (props) => {
    return <STableFooter {...props}/>
};

const TableHeader: TableHeaderComponent = (props) => {
    return <STableHeader {...props}/>
};

const TableHeaderCell: TableHeaderCellComponent = (props) => {
    return <STableHeaderCell {...props}/>
};

const TableRow: TableRowComponent = (props) => {
    return <STableRow {...props}/>
};

const TableBase: React.FC<TableProps> = (props) => {
    const {i} = useContext(ThemeContext);
    return <STable {...i} {...props}/>
};

export const Table: TableComponent = Object.assign(TableBase, {
    Body: TableBody,
    Cell: TableCell,
    Footer: TableFooter,
    Header: TableHeader,
    HeaderCell: TableHeaderCell,
    Row: TableRow,
});
