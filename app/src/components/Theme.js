import React, {useContext, useEffect, useState} from 'react';
import {ThemeContext} from "../contexts/contexts";
import {
    Accordion as ACCORDION,
    Button as BUTTON,
    Form as FORM,
    FormField as FORM_FIELD,
    FormGroup as FORM_GROUP,
    FormInput as FORM_INPUT,
    Header as HEADER,
    Icon as ICON,
    Loader as LOADER,
    Menu as MENU,
    Placeholder as PLACEHOLDER,
    Popup as POPUP,
    Progress as PROGRESS,
    Segment as SEGMENT,
    Statistic as STATISTIC,
    StatisticGroup as STATISTIC_GROUP,
    Tab as TAB,
    Table as TABLE,
    TabPane as TAB_PANE,
    TextArea as TEXTAREA
} from "semantic-ui-react";

export const darkTheme = 'dark';
export const lightTheme = 'light';
export const defaultTheme = lightTheme;
export const systemTheme = 'system';
export const themeSessionKey = 'color-scheme';

export function ThemeWrapper({children, ...props}) {
    if (Object.keys(props).length > 0) {
        console.log(props);
        console.error('ThemeWrapper does not support props!');
    }

    // Properties to manipulate elements with theme.
    // Example <p {...s}>This paragraph changes style</p>
    const [i, setI] = useState({});
    const [s, setS] = useState({});
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
        setT({style: {color: '#dddddd'}});
        setInverted('inverted');
        setTheme(darkTheme);
        document.body.style.background = '#1B1C1D';
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

    const setSystemTheme = () => {
        console.debug('setSystemTheme');
        saveTheme(systemTheme);
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
        t, // Used to invert text.
        s, // Used to invert the style some elements.
        inverted, // Used to add "invert" to className.
        theme,
        savedTheme,
        setDarkTheme,
        setLightTheme,
        setSystemTheme,
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

export function Button(props) {
    const {i, inverted} = useContext(ThemeContext);
    props = defaultGrey({...i, ...props}, inverted);
    return <BUTTON {...props}/>
}

export function Accordion(props) {
    const {i, inverted} = useContext(ThemeContext);
    props = defaultGrey({...i, ...props}, inverted);
    return <ACCORDION {...props}/>
}

export function Header(props) {
    const {i, inverted} = useContext(ThemeContext);
    props = defaultGrey({...i, ...props}, inverted);
    return <HEADER {...props}/>
}

export function Form(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <FORM {...props}/>
}

export function FormField(props) {
    const {i} = useContext(ThemeContext);
    props = invertedNull({...i, ...props});
    return <FORM_FIELD {...props}/>
}

export function FormGroup(props) {
    const {i} = useContext(ThemeContext);
    props = invertedNull({...i, ...props});
    return <FORM_GROUP {...props}/>
}

export function FormInput(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <FORM_INPUT {...props}/>
}

export function Icon(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <ICON {...props}/>
}

export function Loader(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <LOADER {...props}/>
}

export function Menu(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <MENU {...props}/>
}

export function Placeholder(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <PLACEHOLDER {...props}/>
}

export function Popup(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <POPUP {...props}/>
}

export function Progress(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <PROGRESS {...props}/>
}

export function Segment(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <SEGMENT {...props}/>
}

export function Statistic(props) {
    const {i, inverted} = useContext(ThemeContext);
    props = defaultGrey({...i, ...props}, inverted);
    return <STATISTIC {...props}/>
}

export function StatisticGroup(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <STATISTIC_GROUP {...props}/>
}

export function Tab(props) {
    const {i} = useContext(ThemeContext);
    props = invertedNull({...i, ...props});
    return <TAB {...props}/>
}

export function TabPane(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <TAB_PANE {...props}/>
}

export function Table(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <TABLE {...props}/>
}

export function TextArea(props) {
    const {i} = useContext(ThemeContext);
    props = invertedNull({...i, ...props});
    return <TEXTAREA {...props}/>
}

export function CardIcon(props) {
    const {inverted} = useContext(ThemeContext);
    return <center className={`card-icon ${inverted}`} {...props}/>
}
