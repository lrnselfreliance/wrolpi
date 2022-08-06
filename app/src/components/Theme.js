import React, {useContext} from 'react';
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
