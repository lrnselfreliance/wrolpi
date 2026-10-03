const reportWebVitals = onPerfEntry => {
    if (typeof onPerfEntry === 'function') {
        // web-vitals 3+ renamed get* to on*; 5+ replaced FID with INP.
        return import('web-vitals').then(({onCLS, onINP, onFCP, onLCP, onTTFB}) => {
            onCLS(onPerfEntry);
            onINP(onPerfEntry);
            onFCP(onPerfEntry);
            onLCP(onPerfEntry);
            onTTFB(onPerfEntry);
        });
    }
};

export default reportWebVitals;
