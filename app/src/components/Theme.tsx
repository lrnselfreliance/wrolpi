import React, {useContext, useEffect, useState, forwardRef, HTMLAttributes, CSSProperties} from 'react';
import {ThemeContext} from "../contexts/contexts";
import {
    Accordion as SAccordion,
    Breadcrumb as SBreadcrumb,
    Button as SButton,
    Card as SCard,
    Divider as SDivider,
    Form as SForm,
    FormField as SFormField,
    FormGroup as SFormGroup,
    FormInput as SFormInput,
    Header as SHeader,
    Icon as SIcon,
    Loader as SLoader,
    Menu as SMenu,
    Modal as SModal,
    ModalActions as SModalActions,
    ModalContent as SModalContent,
    ModalDescription as SModalDescription,
    ModalHeader as SModalHeader,
    Placeholder as SPlaceholder,
    Popup as SPopup,
    Progress as SProgress,
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
    AccordionProps,
    BreadcrumbProps,
    ButtonProps,
    CardProps as SCardProps,
    DividerProps,
    FormProps,
    FormFieldProps,
    FormGroupProps,
    FormInputProps,
    HeaderProps,
    IconProps,
    LoaderProps,
    MenuProps,
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
import {ColorToSemanticHexColor} from "./Common";
import _ from "lodash";
import {ThemeContextValue, ThemeName, SavedThemeName} from "../types/theme";

export const darkTheme = 'dark';
export const lightTheme = 'light';
export const defaultTheme = lightTheme;
export const systemTheme = 'system';
export const themeSessionKey = 'color-scheme';

interface ThemeProviderProps {
    children: React.ReactNode;
}

export function ThemeProvider({children, ...props}: ThemeProviderProps) {
    if (!_.isEmpty(props)) {
        console.log(props);
        console.error('ThemeWrapper does not support props!');
    }

    // Properties to manipulate elements with theme.
    // Invert when Semantic supports it.  Example: <Menu {...i}>
    const [i, setI] = useState<{inverted?: boolean}>({});
    // Invert style when Semantic does not support it.  Example: <p {...s}>This paragraph changes style</p>
    const [s, setS] = useState<{style?: CSSProperties}>({});
    // Invert text when Semantic does not support it.
    const [t, setT] = useState<{style?: CSSProperties}>({});
    const [inverted, setInverted] = useState<string>('');

    // theme can be one of [darkTheme, lightTheme]
    const [theme, setTheme] = useState<ThemeName>(lightTheme);
    // savedTheme can be one of [null, darkTheme, lightTheme, systemTheme]
    const [savedTheme, setSavedTheme] = useState<SavedThemeName>(
        localStorage.getItem('color-scheme') as SavedThemeName
    );

    const setDarkTheme = (save = false) => {
        console.debug('setDarkTheme');
        setI({inverted: true});
        setS({style: {backgroundColor: '#1B1C1D', color: '#dddddd'}});
        setT({style: {color: '#eeeeee'}});
        setInverted('inverted');
        setTheme(darkTheme);
        document.body.style.background = '#171616';
        if (save) {
            saveTheme(darkTheme);
        }
    }

    const setLightTheme = (save = false) => {
        console.debug('setLightTheme');
        setI({inverted: undefined});
        setS({});
        setT({});
        setInverted('');
        setTheme(lightTheme);
        document.body.style.background = '#FFFFFF';
        if (save) {
            saveTheme(lightTheme);
        }
    }

    const saveTheme = (value: ThemeName) => {
        setSavedTheme(value);
        localStorage.setItem(themeSessionKey, value);
    }

    const cycleSavedTheme = (e?: React.MouseEvent) => {
        // Cycle: System -> Dark -> Light
        if (e) {
            e.preventDefault();
        }
        if (savedTheme === systemTheme || savedTheme == null) {
            saveTheme(darkTheme);
        } else if (savedTheme === darkTheme) {
            saveTheme(lightTheme);
        } else if (savedTheme === lightTheme) {
            saveTheme(systemTheme as ThemeName);
        } else {
            console.error(`Unknown theme! savedTheme=${savedTheme}`);
        }
        applyTheme();
    }

    const matchTheme = (): ThemeName => {
        // Returns darkTheme if saved theme is dark, lightTheme if saved theme is dark,
        // darkTheme if system prefers dark, otherwise lightTheme.
        const colorScheme = localStorage.getItem(themeSessionKey);
        setSavedTheme(colorScheme as SavedThemeName);
        if (colorScheme === darkTheme) {
            return darkTheme;
        } else if (colorScheme === lightTheme) {
            return lightTheme
        }
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? darkTheme : lightTheme;
    }

    const applyTheme = () => {
        const match = matchTheme();
        if (match === darkTheme) {
            setDarkTheme();
        } else {
            setLightTheme();
        }
    };

    useEffect(() => {
        applyTheme();
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyTheme);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const themeValue: ThemeContextValue = {
        i, // Used for Semantic elements which support "inverted".
        s, // Used to invert the style some elements.
        t, // Used to invert text.
        inverted, // Used to add "invert" to className.
        theme,
        savedTheme,
        setDarkTheme,
        setLightTheme,
        cycleSavedTheme,
    };

    return <ThemeContext.Provider value={themeValue}>
        {children}
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

export function Accordion(props: AccordionProps) {
    const {i, inverted} = useContext(ThemeContext);
    const mergedProps = defaultGrey({...i, ...props}, !!inverted);
    return <SAccordion {...mergedProps}/>
}

export const Button = forwardRef<any, ButtonProps>((props, ref) => {
    const {i, inverted} = useContext(ThemeContext);
    const mergedProps = defaultGrey({...i, ...props}, !!inverted);
    return <SButton ref={ref} {...mergedProps}/>
});
Button.displayName = 'Button';

export function Divider(props: DividerProps) {
    const {i} = useContext(ThemeContext);
    return <SDivider {...i} {...props}/>
}

export function Header(props: HeaderProps) {
    const {t} = useContext(ThemeContext);
    return <SHeader {...t} {...props}/>
}

export function Icon(props: IconProps) {
    const {i} = useContext(ThemeContext);
    return <SIcon {...i} {...props}/>
}

export function Loader(props: LoaderProps) {
    const {i} = useContext(ThemeContext);
    return <SLoader {...i} {...props}/>
}

export function Menu(props: MenuProps) {
    const {i} = useContext(ThemeContext);
    return <SMenu {...i} {...props}/>
}

export function Placeholder(props: PlaceholderProps) {
    const {i} = useContext(ThemeContext);
    return <SPlaceholder {...i} {...props}/>
}

export function Popup(props: PopupProps) {
    const {i} = useContext(ThemeContext);
    return <SPopup {...i} style={{border: '1px solid grey'}} {...props}/>
}

export function Progress(props: ProgressProps) {
    const {i} = useContext(ThemeContext);
    return <SProgress {...i} {...props}/>
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
