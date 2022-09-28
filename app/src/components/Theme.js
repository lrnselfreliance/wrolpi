import React, {useContext, useEffect, useState} from 'react';
import {darkTheme, lightTheme, ThemeContext} from "../contexts/contexts";
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

export function ThemeWrapper({children, ...props}) {
    if (Object.keys(props).length > 0) {
        console.log(props);
        console.error('ThemeWrapper does not support props!');
    }

    const [i, setI] = useState({});
    const [s, setS] = useState({});
    const [t, setT] = useState({});
    const [theme, setTheme] = useState();

    const setDarkTheme = (save = false) => {
        console.debug('setDarkTheme');
        setI({inverted: true});
        setS({style: {backgroundColor: '#1B1C1D', color: '#dddddd'}});
        setT({style: {color: '#dddddd'}});
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
        setTheme(lightTheme);
        document.body.style.background = '#FFFFFF';
        if (save) {
            saveTheme(lightTheme);
        }
    }

    const saveTheme = (value) => {
        console.debug('saveTheme', value);
        localStorage.setItem('color-scheme', value);
    }

    useEffect(() => {
        const colorScheme = localStorage.getItem('color-scheme');
        if (colorScheme === darkTheme) {
            // User saved dark theme.
            setDarkTheme();
        } else if (colorScheme === lightTheme) {
            // User saved light theme.
            setLightTheme();
        } else {
            // No saved theme, use the systems color scheme first, if no system theme, use dark.
            window.matchMedia('(prefers-color-scheme: dark)').matches ? setDarkTheme() : setLightTheme();
        }
        // Add listener to match the system theme.
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener(
            'change', (e) => e.matches ? setDarkTheme() : setLightTheme());
    }, []);

    const themeValue = {i, s, t, theme, setDarkTheme, setLightTheme};

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

export function Button(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <BUTTON {...props}/>
}

export function Accordion(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
    return <ACCORDION {...props}/>
}

export function Header(props) {
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
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
    const {i} = useContext(ThemeContext);
    props = {...i, ...props};
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
