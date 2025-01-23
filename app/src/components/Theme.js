import React, {useContext, useEffect, useState} from 'react';
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
    TabPane as STabPane,
    TextArea as STextArea
} from "semantic-ui-react";
import {ColorToSemanticHexColor} from "./Common";
import _ from "lodash";

export const darkTheme = 'dark';
export const lightTheme = 'light';
export const defaultTheme = lightTheme;
export const systemTheme = 'system';
export const themeSessionKey = 'color-scheme';

export function ThemeProvider({children, ...props}) {
    if (!_.isEmpty(props)) {
        console.log(props);
        console.error('ThemeWrapper does not support props!');
    }

    // Properties to manipulate elements with theme.
    // Invert when Semantic supports it.  Example: <Menu {...i}>
    const [i, setI] = useState({});
    // Invert style when Semantic does not support it.  Example: <p {...s}>This paragraph changes style</p>
    const [s, setS] = useState({});
    // Invert text when Semantic does not support it.
    const [t, setT] = useState({});
    const [inverted, setInverted] = useState('');

    // theme can be one of [darkTheme, lightTheme]
    const [theme, setTheme] = useState(defaultTheme);
    // savedTheme can be one of [null, darkTheme, lightTheme, systemTheme]
    const [savedTheme, setSavedTheme] = useState(localStorage.getItem('color-scheme'));

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

    const saveTheme = (value) => {
        setSavedTheme(value);
        localStorage.setItem(themeSessionKey, value);
    }

    const cycleSavedTheme = (e) => {
        // Cycle: System -> Dark -> Light
        if (e) {
            e.preventDefault();
        }
        if (savedTheme === systemTheme || savedTheme == null) {
            saveTheme(darkTheme);
        } else if (savedTheme === darkTheme) {
            saveTheme(lightTheme);
        } else if (savedTheme === lightTheme) {
            saveTheme(systemTheme);
        } else {
            console.error(`Unknown theme! savedTheme=${savedTheme}`);
        }
        applyTheme();
    }

    const matchTheme = () => {
        // Returns darkTheme if saved theme is dark, lightTheme if saved theme is dark,
        // darkTheme if system prefers dark, otherwise lightTheme.
        const colorScheme = localStorage.getItem(themeSessionKey);
        setSavedTheme(colorScheme);
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
    }, []);

    const themeValue = {
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

const invertedNull = (props) => {
    if (props['inverted'] === true) {
        props['inverted'] = null;
    }
    return props;
}

const defaultGrey = (props, inverted) => {
    // Some elements look softer when grey, use grey only if another color is not provided.
    if (inverted) {
        return {color: 'grey', ...props};
    }
    return props;
}

export function Accordion(props) {
    const {i, inverted} = useContext(ThemeContext);
    props = defaultGrey({...i, ...props}, inverted);
    return <SAccordion {...props}/>
}

export const Button = React.forwardRef((props, ref) => {
    const {i, inverted} = useContext(ThemeContext);
    props = defaultGrey({...i, ...props}, inverted);
    return <SButton ref={ref} {...props}/>
});

export function Divider({...props}) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <SDivider {...props}/>
}

export function Header(props) {
    const {t} = useContext(ThemeContext);
    props = {...t, ...props};
    return <SHeader {...props}/>
}

export function Form(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <SForm {...props}/>
}

export function FormField(props) {
    const {i} = useContext(ThemeContext);
    props = invertedNull({...i, ...props});
    return <SFormField {...props}/>
}

export function FormGroup(props) {
    const {i} = useContext(ThemeContext);
    props = invertedNull({...i, ...props});
    return <SFormGroup {...props}/>
}

export function FormInput(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <SFormInput {...props}/>
}

export function Icon(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <SIcon {...props}/>
}

export function Loader(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <SLoader {...props}/>
}

export function Menu(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <SMenu {...props}/>
}

export function Modal({...props}) {
    const {inverted} = useContext(ThemeContext);
    return <SModal {...props} className={`${inverted}`}/>
}

export function ModalActions({...props}) {
    const {inverted} = useContext(ThemeContext);
    return <SModalActions {...props} className={`${inverted}`}/>
}

export function ModalContent({...props}) {
    const {inverted} = useContext(ThemeContext);
    return <SModalContent {...props} className={`${inverted}`}/>
}

export function ModalDescription({...props}) {
    const {inverted} = useContext(ThemeContext);
    return <SModalDescription {...props} className={`${inverted}`}/>
}

export function ModalHeader({...props}) {
    const {inverted} = useContext(ThemeContext);
    return <SModalHeader {...props} className={`${inverted}`}>
        {props.children}
    </SModalHeader>
}

export function Placeholder(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <SPlaceholder {...props}/>
}

export function Popup(props) {
    const {i} = useContext(ThemeContext);
    return <SPopup {...i} style={{border: '1px solid grey'}} {...props}/>
}

export function Progress(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <SProgress {...props}/>
}

export function Segment(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <SSegment {...props}/>
}

export function Statistic(props) {
    const {i, inverted} = useContext(ThemeContext);
    props = defaultGrey({...i, ...props}, inverted);
    return <SStatistic {...props}/>
}

export function StatisticGroup(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    props['style'] = {...props['style'], marginLeft: 0, marginRight: 0};
    return <SStatisticGroup {...props}/>
}

export function Tab(props) {
    const {i} = useContext(ThemeContext);
    props = invertedNull({...i, ...props});
    return <STab {...props}/>
}

export function TabPane(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <STabPane {...props}/>
}

export function Table(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <STable {...props}/>
}

export function TextArea(props) {
    const {i} = useContext(ThemeContext);
    props = invertedNull({...i, ...props});
    return <STextArea {...props}/>
}

export function CardIcon({onClick, ...props}) {
    const {inverted} = useContext(ThemeContext);
    const cardIcon = <center className={`card-icon ${inverted}`} {...props}/>;
    if (onClick) {
        return <div onClick={onClick} className='clickable'>
            {cardIcon}
        </div>
    } else {
        return cardIcon;
    }
}

export function Card({color, ...props}) {
    const {inverted} = useContext(ThemeContext);

    props['style'] = props['style'] || {};
    let emphasisColor = ColorToSemanticHexColor(color);
    if (emphasisColor) {
        // Increase drop shadow to emphasize color.
        const borderColor = inverted ? '#888' : '#ddd';
        props['style']['boxShadow'] = `0 0 0 2px ${borderColor}, 0 5px 0 0 ${emphasisColor}, 0 0px 3px 0 #d4d4d5`;
    }
    return <SCard {...props}/>
}

export function Breadcrumb({...props}) {
    const {t} = useContext(ThemeContext);
    return <SBreadcrumb {...props} {...t}/>
}

export function BreadcrumbDivider({...props}) {
    const {inverted} = useContext(ThemeContext);

    // TODO this only handles icons for now.
    let className = `divider icon ${inverted} ${props.icon || ''}`;
    return <i aria-hidden="true" className={className}></i>
}
