import React from "react";

export const darkTheme = 'dark';
export const lightTheme = 'light';

export const SettingsContext = React.createContext({});
export const ThemeContext = React.createContext({
    theme: null,
    i: {},
    setTheme: () => {
    },
});
