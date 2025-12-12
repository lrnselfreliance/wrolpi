/**
 * Controller API client for WROLPi.
 *
 * These functions call the Controller service endpoints.
 * Controller handles system-level operations that need to work
 * even when the main API is down.
 */

// Controller endpoints are served under /controller/api
const CONTROLLER_BASE = '/controller/api';

/**
 * Fetch with error handling for Controller endpoints.
 */
async function controllerFetch(endpoint, options = {}) {
    const url = `${CONTROLLER_BASE}${endpoint}`;
    const response = await fetch(url, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({detail: response.statusText}));
        throw new Error(error.detail || 'Controller request failed');
    }

    return response.json();
}

// --- Status Endpoints ---

/**
 * Get all system stats from the Controller.
 * Returns CPU, memory, load, drives, network, power, iostat, processes,
 * disk_bandwidth along with system info (dockerized, is_rpi, hotspot, throttle).
 */
export async function getControllerStats() {
    return controllerFetch('/stats');
}

export async function getCpuStatus() {
    return controllerFetch('/status/cpu');
}

export async function getMemoryStatus() {
    return controllerFetch('/status/memory');
}

export async function getLoadStatus() {
    return controllerFetch('/status/load');
}

export async function getDrivesStatus() {
    return controllerFetch('/status/drives');
}

export async function getPrimaryDriveStatus() {
    return controllerFetch('/status/primary-drive');
}

export async function getNetworkStatus() {
    return controllerFetch('/status/network');
}

export async function getPowerStatus() {
    return controllerFetch('/status/power');
}

// --- Admin Endpoints ---

export async function getHotspotStatus() {
    return controllerFetch('/hotspot/status');
}

export async function enableHotspot() {
    return controllerFetch('/hotspot/enable', {method: 'POST'});
}

export async function disableHotspot() {
    return controllerFetch('/hotspot/disable', {method: 'POST'});
}

export async function getThrottleStatus() {
    return controllerFetch('/throttle/status');
}

export async function enableThrottle() {
    return controllerFetch('/throttle/enable', {method: 'POST'});
}

export async function disableThrottle() {
    return controllerFetch('/throttle/disable', {method: 'POST'});
}

export async function shutdownSystem() {
    return controllerFetch('/shutdown', {method: 'POST'});
}

export async function rebootSystem() {
    return controllerFetch('/reboot', {method: 'POST'});
}

export async function restartServices() {
    return controllerFetch('/restart', {method: 'POST'});
}

// --- Service Endpoints ---

export async function getServices() {
    return controllerFetch('/services');
}

export async function getServiceStatus(serviceName) {
    return controllerFetch(`/services/${serviceName}`);
}

export async function startService(serviceName) {
    return controllerFetch(`/services/${serviceName}/start`, {method: 'POST'});
}

export async function stopService(serviceName) {
    return controllerFetch(`/services/${serviceName}/stop`, {method: 'POST'});
}

export async function restartService(serviceName) {
    return controllerFetch(`/services/${serviceName}/restart`, {method: 'POST'});
}

export async function enableService(serviceName) {
    return controllerFetch(`/services/${serviceName}/enable`, {method: 'POST'});
}

export async function disableService(serviceName) {
    return controllerFetch(`/services/${serviceName}/disable`, {method: 'POST'});
}

export async function getServiceLogs(serviceName, lines = 100) {
    return controllerFetch(`/services/${serviceName}/logs?lines=${lines}`);
}

// --- Disk Endpoints ---

export async function getDisks() {
    return controllerFetch('/disks');
}

export async function getMounts() {
    return controllerFetch('/disks/mounts');
}

export async function mountDisk(device, mountPoint) {
    return controllerFetch('/disks/mount', {
        method: 'POST',
        body: JSON.stringify({device, mount_point: mountPoint}),
    });
}

export async function unmountDisk(mountPoint, lazy = false) {
    return controllerFetch('/disks/unmount', {
        method: 'POST',
        body: JSON.stringify({mount_point: mountPoint, lazy}),
    });
}

export async function detectWrolpiDrives() {
    return controllerFetch('/disks/detect-wrolpi');
}

export async function getSmartStatus() {
    return controllerFetch('/disks/smart');
}

// --- Health Check ---

export async function healthCheck() {
    return controllerFetch('/health');
}

// --- Controller Info ---

export async function getControllerInfo() {
    return controllerFetch('/info');
}
