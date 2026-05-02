import React from 'react';
import {PageContainer, TabLinks} from "../Common";
import {Route, Routes} from "react-router";
import {DownloadsPage} from "./Downloads";
import {SettingsPage} from "./Settings";
import {StatusPage} from "./Status";
import {ControllerPage} from "./ControllerPage";
import {ExtensionPage} from "./ExtensionPage";

export default function AdminRoute() {

    const links = [
        {text: 'Downloads', to: '/admin', key: 'admin', end: true},
        {text: 'Settings', to: '/admin/settings', key: 'settings'},
        {text: 'Status', to: '/admin/status', key: 'status'},
        {text: 'Control', to: '/admin/controller', key: 'controller'},
        {text: 'Extension', to: '/admin/extension', key: 'extension'},
    ];

    return <PageContainer>
        <TabLinks links={links}/>
        <Routes>
            <Route path='/' exact element={<DownloadsPage/>}/>
            <Route path='settings' exact element={<SettingsPage/>}/>
            <Route path='status' exact element={<StatusPage/>}/>
            <Route path='controller' exact element={<ControllerPage/>}/>
            <Route path='extension' exact element={<ExtensionPage/>}/>
        </Routes>
    </PageContainer>
}
