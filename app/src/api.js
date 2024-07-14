import {API_URI, ARCHIVES_API, DEFAULT_LIMIT, emptyToNull, OTP_API, VIDEOS_API, ZIM_API} from "./components/Common";
import {toast} from "react-semantic-toasts-2";
import _ from "lodash";

function timeoutPromise(ms, promise) {
    // Create a timeout wrapper around a promise.  If the timeout is reached, throw an error.  Otherwise, return
    // the results of the promise.
    return new Promise((resolve, reject) => {
        const timeoutId = setTimeout(() => {
            reject(new Error("promise timeout"))
        }, ms);
        promise.then((res) => {
            clearTimeout(timeoutId);
            resolve(res);
        }, (err) => {
            clearTimeout(timeoutId);
            reject(err);
        });
    })
}

async function apiCall(url, method, body, ms = 60_000) {
    let init = {method};
    if (body !== undefined) {
        init.body = JSON.stringify(body);
    }

    // Create a fetch promise, this will be awaited by the timeout.
    let promise = fetch(url, init);

    try {
        // await the response or error.
        let response = await timeoutPromise(ms, promise);
        if (200 <= response.status && response.status < 300) {
            // Request was successful.
            return response;
        }
        // Request encountered an error.
        let copy = response.clone();
        const content = await copy.json();
        console.debug('API error response json', content);
        const code = content['code'];
        if (response.status === 403 && code === 'WROL_MODE_ENABLED') {
            toast({
                type: 'error',
                title: 'WROL Mode is enabled!',
                description: 'This functionality is disabled while WROL Mode is enabled!',
                time: 5000,
            });
        }
        return response;
    } catch (e) {
        // Timeout, or some other exception.
        console.error(e);
        throw e;
    }
}

// Convenience functions for API calls.
let apiGet = async (url) => {
    return await apiCall(url, 'GET')
};
let apiDelete = async (url) => {
    return await apiCall(url, 'DELETE')
};
let apiPost = async (url, body) => {
    return await apiCall(url, 'POST', body)
};
let apiPut = async (url, body) => {
    return await apiCall(url, 'PUT', body)
};
let apiPatch = async (url, body) => {
    return await apiCall(url, 'PATCH', body)
};

export async function updateChannel(id, channel) {
    channel = emptyToNull(channel);
    return await apiPut(`${VIDEOS_API}/channels/${id}`, channel);
}

export async function createChannel(channel) {
    channel = emptyToNull(channel);
    return await apiPost(`${VIDEOS_API}/channels`, channel);
}

export async function deleteChannel(channelId) {
    const response = await apiDelete(`${VIDEOS_API}/channels/${channelId}`);
    if (response.status !== 204) {
        const content = await response.json();
        console.error(content);
        throw Error(content);
    }
    return response;
}

export async function getChannels() {
    let response = await apiGet(`${VIDEOS_API}/channels`);
    if (response.status === 200) {
        return (await response.json())['channels'];
    } else {
        toast({
            type: 'error',
            title: 'Unexpected server response',
            description: 'Failed to get channels.  See server logs.',
            time: 5000,
        });
    }
}

export async function getChannel(id) {
    let response = await apiGet(`${VIDEOS_API}/channels/${id}`);
    return (await response.json())['channel'];
}

export async function searchVideos(offset, limit, channelId, searchStr, order_by, tagNames, headline) {
    // Build a search query to retrieve a list of videos from the API
    offset = parseInt(offset || 0);
    limit = parseInt(limit || DEFAULT_LIMIT);
    let body = {offset, limit, order_by: order_by || 'rank'};

    if (searchStr) {
        body['search_str'] = searchStr;
    }
    if (channelId) {
        body['channel_id'] = parseInt(channelId);
    }
    if (tagNames) {
        body['tag_names'] = tagNames;
    }
    if (headline) {
        body['headline'] = true;
    }

    console.debug('searching videos', body);

    let response = await apiPost(`${VIDEOS_API}/search`, body);
    if (response.status === 200) {
        let data = await response.json();
        return [data['file_groups'], data['totals']['file_groups']];
    } else {
        toast({
            type: 'error',
            title: 'Unexpected server response',
            description: 'Failed to search videos.  See server logs.',
            time: 5000,
        });
        return [[], 0];
    }
}

export async function getVideo(video_id) {
    let response = await apiGet(`${VIDEOS_API}/video/${video_id}`);
    let data = await response.json();
    return [data['file_group'], data['prev'], data['next']];
}

export async function deleteVideos(videoIds) {
    if (!videoIds || videoIds.length === 0) {
        toast({
            type: 'error',
            title: 'Empty request',
            description: 'Unable to delete Videos because no IDs were passed.',
            time: 5000,
        });
    }
    console.info(`Deleting Videos: ${videoIds}`);
    const i = videoIds.join(',');
    let response = await apiDelete(`${VIDEOS_API}/video/${i}`);
    if (response.status !== 204) {
        const content = response.json();
        console.error(content);
        throw Error(content);
    }
}

export async function downloadVideoMetadata(videoUrl, destination) {
    return await postDownload(
        [videoUrl],
        'video',
        null,
        null,
        null,
        destination,
        null,
        null,
        null,
        null,
        true,
    );
}

export async function getDirectories(search_str) {
    let form_data = {'search_str': search_str || null};
    let response = await apiPost(`${API_URI}/files/directories`, form_data);
    if (response.status === 200) {
        return await response.json();
    }
    return [];
}

export async function getStatus() {
    let response = await apiGet(`${API_URI}/status`);
    if (response.status === 200) {
        return await response.json();
    } else {
        toast({
            type: 'error', title: 'Unexpected server response', description: 'Could not get server status', time: 5000,
        });
    }
}

export async function getSettings() {
    let response = await apiGet(`${API_URI}/settings`);
    if (response.status === 200) {
        return await response.json();
    } else {
        toast({
            type: 'error', title: 'Unexpected server response', description: 'Could not get settings', time: 5000,
        });
    }
}

export async function saveSettings(settings) {
    return await apiPatch(`${API_URI}/settings`, settings);
}

export async function getDownloads() {
    let response = await apiGet(`${API_URI}/download`);
    if (response.status === 200) {
        return await response.json();
    } else {
        toast({
            type: 'error', title: 'Unexpected server response', description: 'Could not get downloads', time: 5000,
        });
    }
}

export async function validateRegex(regex) {
    let response = await apiPost(`${API_URI}/valid_regex`, {regex});
    return (await response.json())['valid'];
}

export async function getVideosStatistics() {
    let response = await apiGet(`${VIDEOS_API}/statistics`);
    if (response.status === 200) {
        return (await response.json())['statistics'];
    } else {
        toast({
            type: 'error', title: 'Unexpected server response', description: 'Could not get statistics', time: 5000,
        });
    }
}

export async function createChannelDownload(channelId, url, frequency, title_include, title_exclude, tag_names) {
    const body = {
        url: url,
        frequency: frequency,
        settings: {
            title_include: title_include,
            title_exclude: title_exclude,
            tag_names: tag_names,
        },
    }
    url = `${VIDEOS_API}/channels/${channelId}/download`;
    let response = await apiPost(url, body);
    if (!response.ok) {
        const json = await response.json();
        if (json['code'] === 'INVALID_DOWNLOAD') {
            toast({
                type: 'error',
                title: 'Cannot Download!',
                description: 'This channel does not have a download record.  Modify the frequency.',
                time: 5000,
            });
        } else {
            toast({
                type: 'error',
                title: 'Failed to Download!',
                description: 'Failed to create download.  See server logs.',
                time: 5000,
            });
        }
    }
    return response;
}

export async function updateChannelDownload(channelId, downloadId, url, frequency, title_include, title_exclude, tag_names) {
    const body = {
        url: url,
        frequency: frequency,
        settings: {
            title_include: title_include,
            title_exclude: title_exclude,
            tag_names: tag_names,
        },
    }
    url = `${VIDEOS_API}/channels/${channelId}/download/${downloadId}`;
    let response = await apiPut(url, body);
    if (!response.ok) {
        const json = await response.json();
        if (json['code'] === 'INVALID_DOWNLOAD') {
            toast({
                type: 'error',
                title: 'Cannot Download!',
                description: 'This channel does not have a download record.  Modify the frequency.',
                time: 5000,
            });
        } else {
            toast({
                type: 'error',
                title: 'Failed to Download!',
                description: 'Failed to update download.  See server logs.',
                time: 5000,
            });
        }
    }
    return response;
}

export async function refreshChannel(channelId) {
    let url = `${VIDEOS_API}/channels/refresh/${channelId}`;
    return await fetch(url, {method: 'POST'});
}

export async function encryptOTP(otp, plaintext) {
    let body = {otp, plaintext};
    let response = await apiPost(`${OTP_API}/encrypt_otp`, body);
    if (response.status === 200) {
        return await response.json();
    } else {
        toast({
            type: 'error', title: 'Error!', description: 'Failed to encrypt OTP', time: 5000,
        });
    }
}

export async function decryptOTP(otp, ciphertext) {
    let body = {otp, ciphertext};
    let response = await apiPost(`${OTP_API}/decrypt_otp`, body);
    if (response.status === 200) {
        return await response.json();
    } else {
        toast({
            type: 'error', title: 'Error!', description: 'Failed to decrypt OTP', time: 5000,
        });
    }
}

export async function getCategories() {
    let response = await apiGet(`${API_URI}/inventory/categories`);
    if (response.status === 200) {
        return (await response.json())['categories'];
    } else {
        toast({
            type: 'error', title: 'Unexpected server response', description: 'Could not get categories', time: 5000,
        });
    }
}

export async function getBrands() {
    let response = await apiGet(`${API_URI}/inventory/brands`);
    if (response.status === 200) {
        return (await response.json())['brands'];
    } else {
        toast({
            type: 'error', title: 'Unexpected server response', description: 'Could not get brands', time: 5000,
        });
    }
}

export async function getInventories() {
    let response = await apiGet(`${API_URI}/inventory`);
    if (response.status === 200) {
        return (await response.json())['inventories'];
    } else {
        toast({
            type: 'error', title: 'Unexpected server response', description: 'Could not get inventories', time: 5000,
        });
    }
}

export async function getInventory(inventoryId) {
    let response = await apiGet(`${API_URI}/inventory/${inventoryId}`);
    if (response.status === 200) {
        return await response.json();
    } else {
        toast({
            type: 'error', title: 'Unexpected server response', description: 'Could not get inventory', time: 5000,
        });
    }
}

export async function saveInventory(inventory) {
    return await apiPost(`${API_URI}/inventory`, inventory);
}

export async function updateInventory(inventoryId, inventory) {
    delete inventory['id'];
    return await apiPut(`${API_URI}/inventory/${inventoryId}`, inventory);
}

export async function deleteInventory(inventoryId) {
    return await apiDelete(`${API_URI}/inventory/${inventoryId}`);
}

export async function getItems(inventoryId) {
    let response = await apiGet(`${API_URI}/inventory/${inventoryId}/item`);
    return await response.json();
}

export async function saveItem(inventoryId, item) {
    return await apiPost(`${API_URI}/inventory/${inventoryId}/item`, item);
}

export async function updateItem(itemId, item) {
    item = emptyToNull(item);
    return await apiPut(`${API_URI}/inventory/item/${itemId}`, item);
}

export async function deleteItems(itemIds) {
    let i = itemIds.join(',');
    await apiDelete(`${API_URI}/inventory/item/${i}`);
}

export async function deleteArchives(archiveIds) {
    if (!archiveIds || archiveIds.length === 0) {
        toast({
            type: 'error',
            title: 'Empty request',
            description: 'Unable to delete Archives because no IDs were passed.',
            time: 5000,
        });
    }
    console.log(`Deleting Archives: ${archiveIds}`);
    let i = archiveIds.join(',');
    const response = await apiDelete(`${API_URI}/archive/${i}`);
    if (response.status !== 204) {
        const content = await response.json();
        console.debug(content);
        throw Error(content['error']);
    }
}

export async function searchArchives(offset, limit, domain, searchStr, order, tagNames, headline) {
    // Build a search query to retrieve a list of videos from the API
    offset = parseInt(offset || 0);
    limit = parseInt(limit || DEFAULT_LIMIT);
    let body = {offset, limit};
    if (domain) {
        body['domain'] = domain;
    }
    if (searchStr) {
        body['search_str'] = searchStr;
    }
    if (order) {
        body['order_by'] = order;
    }
    if (tagNames) {
        body['tag_names'] = tagNames;
    }
    if (headline) {
        body['headline'] = true;
    }

    console.debug('searching archives', body);
    let response = await apiPost(`${ARCHIVES_API}/search`, body);
    if (response.status === 200) {
        let data = await response.json();
        return [data['file_groups'], data['totals']['file_groups']];
    } else {
        toast({
            type: 'error',
            title: 'Unable to search archives',
            description: 'Cannot search archives.  See server logs.',
            time: 5000,
        });
        return [[], 0];
    }
}

export async function fetchDomains() {
    let response = await apiGet(`${ARCHIVES_API}/domains`);
    if (response.status === 200) {
        let data = await response.json();
        return [data['domains'], data['totals']['domains']];
    } else {
        toast({
            type: 'error',
            title: 'Domains Error',
            description: 'Unable to fetch Domains.  See server logs.',
            time: 5000,
        });
    }
}

export async function getArchive(archiveId) {
    const response = await apiGet(`${ARCHIVES_API}/${archiveId}`);
    if (response.status === 200) {
        const data = await response.json();
        return [data['file_group'], data['history']];
    } else {
        toast({
            type: 'error', title: 'Archive Error', description: 'Unable to get Archive.  See server logs.', time: 5000,
        });
    }
}

function getDownloadSettings(excludedURLs, depth, suffix, tagNames, downloadMetadataOnly, destination, max_pages) {
    let settings = {};
    if (excludedURLs) settings['excluded_urls'] = excludedURLs;
    if (depth) settings['depth'] = depth;
    if (suffix) settings['suffix'] = suffix;
    if (tagNames) settings['tag_names'] = tagNames;
    if (downloadMetadataOnly) settings['download_metadata_only'] = downloadMetadataOnly;
    if (destination) settings['destination'] = destination;
    if (max_pages) settings['max_pages'] = max_pages;
    return settings;
}

export async function postDownload(
    urls,
    downloader,
    frequency,
    sub_downloader,
    excludedURLs,
    destination,
    tagNames,
    depth,
    suffix,
    max_pages,
    downloadMetadataOnly,
) {
    if (!downloader) {
        toast({
            type: 'error',
            title: 'Failed to submit download',
            description: 'downloader is required, but was not provided',
            time: 5000,
        })
        throw new Error('downloader is required, but was not provided');
    }

    let settings = getDownloadSettings(excludedURLs, depth, suffix, tagNames, downloadMetadataOnly, destination,
        max_pages);
    let body = {
        urls: urls,
        downloader: downloader,
        sub_downloader: sub_downloader,
        frequency: frequency || null,
        settings: settings,
    };
    const response = await apiPost(`${API_URI}/download`, body);
    return response;
}

export async function putDownload(
    urls,
    download_id,
    downloader,
    sub_downloader,
    frequency,
    excludedURLs,
) {
    if (!downloader) {
        toast({
            type: 'error',
            title: 'Failed to submit download',
            description: 'downloader is required, but was not provided',
            time: 5000,
        })
        throw new Error('downloader is required, but was not provided');
    }

    let settings = getDownloadSettings(excludedURLs)
    let body = {
        urls: urls,
        downloader: downloader,
        sub_downloader: sub_downloader,
        frequency: frequency || null,
        settings: settings,
    };
    const response = await apiPut(`${API_URI}/download/${download_id}`, body);
    return response;
}

export async function killDownload(download_id) {
    let response = await apiPost(`${API_URI}/download/${download_id}/kill`);
    return response;
}

export async function restartDownload(download_id) {
    return await apiPost(`${API_URI}/download/${download_id}/restart`);
}

export async function killDownloads() {
    let response = await apiPost(`${API_URI}/download/kill`);
    return response;
}

export async function startDownloads() {
    let response = await apiPost(`${API_URI}/download/enable`);
    return response;
}

export async function getDownloaders() {
    try {
        let response = await apiGet(`${API_URI}/downloaders`);
        return await response.json();
    } catch (e) {
        return {downloaders: []};
    }
}

export async function deleteDownload(downloadId) {
    try {
        let response = await apiDelete(`${API_URI}/download/${downloadId}`);
        if (response.status !== 204) {
            toast({
                type: 'error',
                title: 'Unable to delete',
                description: 'Unable to delete the download.  See server logs.',
                time: 5000,
            });
        }
    } catch (e) {
        return null;
    }
}

export async function filesSearch(offset, limit, searchStr, mimetypes, model, tagNames, headline, months, fromYear, toYear) {
    const body = {search_str: searchStr, offset: parseInt(offset), limit: parseInt(limit)};
    if (mimetypes) {
        body['mimetypes'] = mimetypes;
    }
    if (model) {
        body['model'] = model;
    }
    if (tagNames) {
        body['tag_names'] = tagNames;
    }
    if (headline) {
        body['headline'] = true;
    }
    if (!_.isEmpty(months)) {
        body['months'] = months.map(i => parseInt(i));
    }
    if (fromYear) {
        body['from_year'] = fromYear;
    }
    if (toYear) {
        body['to_year'] = toYear;
    }
    console.info('searching files', body);
    const response = await apiPost(`${API_URI}/files/search`, body);

    if (response.status === 200) {
        let data = await response.json();
        let [file_groups, total] = [data['file_groups'], data['totals']['file_groups']];
        return [file_groups, total];
    } else {
        toast({
            type: 'error',
            title: 'Unable to search files',
            description: 'Cannot search files.  See server logs.',
            time: 5000,
        });
        return [null, null];
    }
}

export async function refreshFiles(paths) {
    let response;
    if (Array.isArray(paths) && paths.length > 0) {
        // Refresh user-selected files/directories only.
        const body = {paths};
        console.info(`Refreshing: ${paths}`);
        response = await apiPost(`${API_URI}/files/refresh`, body);
    } else {
        console.info(`Refreshing all files`);
        response = await apiPost(`${API_URI}/files/refresh`);
    }
    return response;
}

export async function makeDirectory(path) {
    const body = {path: path};
    try {
        await apiPost(`${API_URI}/files/directory`, body);
    } catch (e) {
        console.error(e);
        toast({
            type: 'error',
            title: 'Unable to create directory',
            description: 'Failed to create directory.  See server logs.',
            time: 5000,
        });
    }
}

export async function getFiles(directories) {
    console.debug(`getFiles ${directories}`);
    let body = {directories: directories || []};
    let response = await apiPost(`${API_URI}/files`, body);
    let {files} = await response.json();
    return files;
}

export async function getFile(path) {
    let body = {file: path};
    let response = await apiPost(`${API_URI}/files/file`, body);
    if (response.ok) {
        const {file} = await response.json();
        return file;
    } else {
        throw new Error('Failed to get file data');
    }
}

export async function deleteFile(paths) {
    let body = {paths: paths};
    const response = await apiPost(`${API_URI}/files/delete`, body);
    if (response.status === 409) {
        const content = await response.json();
        toast({
            type: 'error',
            title: 'Delete error',
            description: content['message'],
            time: 5000,
        });
    }
}

export async function fetchFilesProgress() {
    const response = await apiGet(`${API_URI}/files/refresh_progress`);
    if (response.status === 200) {
        const json = await response.json();
        return json['progress'];
    }
}

export async function getHotspotStatus() {
    let response = await getSettings();
    return response['hotspot_status'];
}

export async function setHotspot(on) {
    let response;
    if (on) {
        response = await apiPost(`${API_URI}/hotspot/on`);
    } else {
        response = await apiPost(`${API_URI}/hotspot/off`);
    }
    if (response.status === 204) {
        return null;
    } else {
        const content = await response.json();
        const code = content['code'];
        if (code === 'NATIVE_ONLY') {
            toast({
                type: 'error',
                title: 'Unsupported!',
                description: 'Hotspot is only supported outside Docker!',
                time: 5000,
            });
        } else {
            toast({
                type: 'error', title: 'Error!', description: 'Could not modify hotspot.  See server logs.', time: 5000,
            });
        }
    }
}

export async function getThrottleStatus() {
    let response = await getSettings();
    return response['throttle_status'];
}

export async function setThrottle(on) {
    let response;
    if (on) {
        response = await apiPost(`${API_URI}/throttle/on`);
    } else {
        response = await apiPost(`${API_URI}/throttle/off`);
    }
    if (response.status === 204) {
        return null;
    } else {
        const content = await response.json();
        const code = content['code'];
        if (code === 'NATIVE_ONLY') {
            toast({
                type: 'error',
                title: 'Unsupported!',
                description: 'Throttle is only supported on a Raspberry Pi!',
                time: 5000,
            });
        } else {
            toast({
                type: 'error', title: 'Error!', description: 'Could not modify throttle.  See server logs.', time: 5000,
            });
        }
    }
}

export async function getMapImportStatus() {
    let response = await apiGet(`${API_URI}/map/files`);
    if (response.status === 200) {
        return await response.json();
    } else {
        toast({
            type: 'error', title: 'Unexpected server response', description: 'Could not get import status', time: 5000,
        });
    }
}

export async function importMapFiles(paths) {
    let body = {'files': paths};
    let response = await apiPost(`${API_URI}/map/import`, body);
    if (response.status === 204) {
        return null;
    } else {
        toast({
            type: 'error', title: 'Error!', description: 'Could not start import!  See server logs.', time: 5000,
        });
    }
}

export async function clearCompletedDownloads() {
    let response = await apiPost(`${API_URI}/download/clear_completed`);
    if (response.status === 204) {
        return null
    } else {
        toast({
            type: 'error',
            title: 'Error!',
            description: 'Could not clear completed downloads!  See server logs.',
            time: 5000,
        });
    }
}

export async function clearFailedDownloads() {
    let response = await apiPost(`${API_URI}/download/clear_failed`);
    if (response.status === 204) {
        return null
    } else {
        toast({
            type: 'error',
            title: 'Error!',
            description: 'Could not clear failed downloads!  See server logs.',
            time: 5000,
        });
    }
}

export async function deleteOnceDownloads() {
    let response = await apiPost(`${API_URI}/download/delete_once`);
    if (response.status === 204) {
        return null
    } else {
        toast({
            type: 'error',
            title: 'Error!',
            description: 'Could not delete once downloads!  See server logs.',
            time: 5000,
        });
    }
}

export async function retryOnceDownloads() {
    let response = await apiPost(`${API_URI}/download/retry_once`);
    if (response.status === 204) {
        return null
    } else {
        toast({
            type: 'error',
            title: 'Error!',
            description: 'Could not retry once downloads!  See server logs.',
            time: 5000,
        });
    }
}

export async function getStatistics() {
    let response = await apiGet(`${API_URI}/statistics`);
    if (response.status === 200) {
        const contents = await response.json();
        return contents;
    } else {
        toast({
            type: 'error', title: 'Error!', description: 'Unable to get file statistics', time: 5000,
        })
    }
}

export async function getEvents(after) {
    let uri = `${API_URI}/events/feed`;
    if (after) {
        uri = `${uri}?after=${encodeURIComponent(after)}`
    }
    let response = await apiGet(uri);
    if (response.status === 200) {
        return await response.json();
    }
}

export async function getTags() {
    let uri = `${API_URI}/tag`;
    let response = await apiGet(uri);
    if (response.status === 200) {
        const body = await response.json();
        return body['tags'];
    }
}

export async function tagFileGroup(fileGroup, name) {
    const body = {tag_name: name};

    const {id, primary_path, path} = fileGroup;
    if (id) {
        body['file_group_id'] = id;
    } else if (primary_path) {
        body['file_group_primary_path'] = primary_path;
    } else if (path) {
        body['file_group_primary_path'] = path;
    }

    const uri = `${API_URI}/files/tag`;
    let response = await apiPost(uri, body);
    if (response.status !== 201) {
        console.error('Failed to add tag');
    }
}

export async function untagFileGroup(fileGroup, name) {
    const body = {tag_name: name};

    const {id, primary_path, path} = fileGroup;
    if (id) {
        body['file_group_id'] = id;
    } else if (primary_path) {
        body['file_group_primary_path'] = primary_path;
    } else if (path) {
        body['file_group_primary_path'] = path;
    }

    const uri = `${API_URI}/files/untag`;
    let response = await apiPost(uri, body)
    if (response.status !== 204) {
        console.error('Failed to remove tag');
    }
}

export async function saveTag(name, color, id) {
    const body = {name: name, color: color};
    let uri = `${API_URI}/tag`;
    if (id) {
        uri = `${uri}/${id}`;
    }
    let response = await apiPost(uri, body);
    if (id && response.status === 200) {
        toast({
            type: 'info', title: 'Saved tag', description: `Saved tag: ${name}`, time: 2000,
        });
    } else if (response.status === 201) {
        toast({
            type: 'info', title: 'Created new tag', description: `Created new tag: ${name}`, time: 2000,
        });
    } else {
        console.error('Failed to create new tag');
        toast({
            type: 'error', title: 'Error!', description: 'Unable to save tag', time: 5000,
        })
    }
}

export async function deleteTag(id, name) {
    const uri = `${API_URI}/tag/${id}`;
    let response = await apiDelete(uri);
    if (response.status === 400) {
        const content = await response.json();
        if (content['code'] === 'USED_TAG') {
            toast({
                type: 'error', title: 'Error!', description: content['message'], time: 5000,
            })
        }
    } else if (response.status !== 204) {
        console.error('Failed to delete tag');
        toast({
            type: 'error', title: 'Error!', description: `Unable to delete tag: ${name}`, time: 5000,
        })
    }
}

export async function fetchFile(path) {
    const uri = `${API_URI}/files/file`;
    const body = {file: path};
    const response = await apiPost(uri, body);
    if (response.status === 200) {
        const content = await response.json();
        return content['file'];
    } else {
        console.error('Unable to fetch file dict!  See client logs.');
    }
}

export async function sendNotification(message, url) {
    const body = {message, url};
    const response = await apiPost(`${API_URI}/notify`, body);
    if (response.status === 201) {
        toast({type: 'success', title: 'Shared', description: 'Your share was sent', time: 2000});
    } else {
        toast({type: 'error', title: 'Error', description: 'Your share failed to send!', time: 5000});
        console.error('Failed to share');
    }
}

export async function searchDirectories(name) {
    const body = {name: name || ''};
    const response = await apiPost(`${API_URI}/files/search_directories`, body);
    if (response.status === 204) {
        return [];
    } else if (response.status === 200) {
        const content = await response.json();
        return content;
    } else {
        toast({type: 'error', title: 'Error', description: 'Failed to search directories!', time: 5000});
    }
}

export async function renamePath(path, newName) {
    const body = {path, new_name: newName};
    const response = await apiPost(`${API_URI}/files/rename`, body);
    if (response.status !== 204) {
        toast({type: 'error', title: 'Error', description: 'Failed to rename!', time: 5000});
    }
}

export async function movePaths(destination, paths) {
    const body = {destination, paths};
    const response = await apiPost(`${API_URI}/files/move`, body);
    if (response.status !== 204) {
        const content = await response.json();
        toast({type: 'error', title: 'Error', description: content['api_error'], time: 5000});
    }
}

export async function ignoreDirectory(directory) {
    const body = {path: directory};
    const response = await apiPost(`${API_URI}/files/ignore_directory`, body);
    if (response.status !== 200) {
        toast({type: 'error', title: 'Error', description: 'Failed to ignore directory!', time: 5000});
    }
}

export async function unignoreDirectory(directory) {
    const body = {path: directory};
    const response = await apiPost(`${API_URI}/files/unignore_directory`, body);
    if (response.status !== 200) {
        toast({type: 'error', title: 'Error', description: 'Failed to unignore directory!', time: 5000});
    }
}

export async function fetchZims() {
    const response = await apiGet(`${API_URI}/zim`);
    if (response.status === 200) {
        const content = await response.json();
        return {
            zims: content['zims'],
        }
    } else {
        toast({type: 'error', title: 'Error', description: 'Cannot fetch Zims', time: 5000});
    }
}

export async function fetchZimSubscriptions() {
    const response = await apiGet(`${API_URI}/zim/subscribe`);
    if (response.status === 200) {
        const content = await response.json();
        return {
            subscriptions: content['subscriptions'],
            catalog: content['catalog'],
            iso_639_codes: content['iso_639_codes'],
        }
    } else {
        toast({type: 'error', title: 'Error', description: 'Cannot fetch Zim Subscriptions', time: 5000});
    }
}

export async function searchZims(offset, limit, searchStr) {
    offset = parseInt(offset || 0);
    limit = parseInt(limit || DEFAULT_LIMIT);
    let body = {offset, limit};
    if (searchStr) {
        body['search_str'] = searchStr;
    }

    console.debug('searching zims', body);
    let response = await apiPost(`${ZIM_API}/search`, body);
    if (response.status === 200) {
        let data = await response.json();
        return [data['zims'],];
    } else {
        toast({
            type: 'error',
            title: 'Unable to search zims',
            description: 'Cannot search zims.  See server logs.',
            time: 5000,
        });
        return [[], 0];
    }
}

export async function searchZim(offset, limit, searchStr, zimId, activeTags) {
    offset = parseInt(offset || 0);
    limit = parseInt(limit || DEFAULT_LIMIT);
    let body = {offset, limit, search_str: searchStr, tag_names: activeTags || []};

    console.debug(`Searching Zim ${zimId} for: ${searchStr} tags: ${activeTags}`);
    let response = await apiPost(`${ZIM_API}/search/${zimId}`, body);
    if (response.status === 200) {
        const content = await response.json();
        const zim = content['zim'];
        const searchLength = zim['search'].length;
        console.debug(`Got ${searchLength} results for Zim ${zimId}`);
        return content['zim'];
    }
}

export async function tagZimEntry(zim_id, zim_entry, name) {
    const body = {tag_name: name, zim_id: zim_id, zim_entry: zim_entry};

    const uri = `${API_URI}/zim/tag`;
    let response = await apiPost(uri, body);
    if (response.status !== 201) {
        console.error('Failed to add tag');
    }
}

export async function untagZimEntry(zim_id, zim_entry, name) {
    const body = {tag_name: name, zim_id: zim_id, zim_entry: zim_entry};

    const uri = `${API_URI}/zim/untag`;
    let response = await apiPost(uri, body);
    if (response.status !== 201) {
        console.error('Failed to add tag');
    }
}

export async function zimSubscribe(name, language) {
    const body = {name, language};
    const response = await apiPost(`${API_URI}/zim/subscribe`, body);
    return response.status === 201;
}

export async function zimUnsubscribe(id) {
    const response = await apiDelete(`${API_URI}/zim/subscribe/${id}`);
    return response.status === 204;
}

export async function fetchDecoded(vinNumber) {
    const body = {vin_number: vinNumber};
    const response = await apiPost(`${API_URI}/vin_number_decoder`, body);
    if (response.status === 200) {
        const content = await response.json();
        return content['vin'];
    } else if (response.status === 400) {
        console.error('Invalid VIN Number');
        return null;
    }
}

export async function searchSuggestions(search_str) {
    const body = {search_str};
    const response = await apiPost(`${API_URI}/search_suggestions`, body);
    if (response.ok) {
        const content = await response.json();

        return {
            channels: content.channels,
            domains: content.domains,
        }
    }
}

export async function searchEstimateFiles(search_str, tagNames, mimetypes, months, dateRange) {
    months = months ? months.map(i => parseInt(i)) : [];

    const body = {search_str, tag_names: tagNames, mimetypes, months};
    if (dateRange) {
        body['from_year'] = dateRange[0];
        body['to_year'] = dateRange[1];
    }
    const response = await apiPost(`${API_URI}/search_file_estimates`, body);
    if (response.ok) {
        const content = await response.json();

        return {
            fileGroups: content.file_groups,
        }
    }
}

export async function searchEstimateZims(search_str, tagNames) {
    const body = {search_str: search_str, tag_names: tagNames};
    const response = await apiPost(`${API_URI}/zim/search_estimates`, body);
    if (response.ok) {
        const content = await response.json();
        return {
            zimsEstimates: content.zims_estimates,
        }
    }
}

export async function getOutdatedZims() {
    const response = await apiGet(`${API_URI}/zim/outdated`);
    if (response.status === 200) {
        const content = await response.json();
        return {
            outdated: content['outdated'],
            current: content['current'],
        }
    } else {
        toast({
            type: 'error',
            title: 'Unable to fetch',
            description: 'Cannot fetch outdated Zims.  See server logs.',
            time: 5000,
        });
    }
}

export async function deleteOutdatedZims() {
    const response = await apiDelete(`${API_URI}/zim/outdated`);
    return response.status === 204;
}

export async function postShutdown() {
    const response = await apiPost(`${API_URI}/shutdown`);
    if (response.status !== 204) {
        // Return the error.
        return await response.json();
    }
    return null
}

export async function postRestart() {
    const response = await apiPost(`${API_URI}/restart`);
    if (response.status !== 204) {
        // Return the error.
        return await response.json();
    }
    return null
}
