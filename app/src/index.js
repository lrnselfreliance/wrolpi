import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import * as serviceWorkerRegistration from './serviceWorkerRegistration';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App/>);

// Register the service worker so the app installs as a PWA and works offline (production build only).
serviceWorkerRegistration.register();
