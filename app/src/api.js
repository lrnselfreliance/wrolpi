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
        const response = await timeoutPromise(ms, promise);
        if (200 <= response.status && response.status < 300) {
            // Request was successful.
            return response;
        }
        // Request encountered an error.
        let copy = response.clone();
        const content = await copy.json();
        console.error('API error response json', content);
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

async function getErrorMessage(response, fallbackMessage) {
    try {
        const json = await response.clone().json();
        return json.error || json.message || fallbackMessage;
    } catch (error) {
        // Server did not response with JSON.  Return default message.
        return fallbackMessage;
    }
}

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
        const message = getErrorMessage(response, 'Failed to delete channel.');
        toast({
            type: 'error',
            title: 'Unexpected server response',
            description: message,
            time: 5000,
        });
    }
    return response;
}

export async function getChannels() {
    const response = await apiGet(`${VIDEOS_API}/channels`);
    if (response.status === 200) {
        return (await response.json())['channels'];
    } else {
        const message = getErrorMessage(response, 'Failed to get channels.');
        toast({
            type: 'error',
            title: 'Unexpected server response',
            description: message,
            time: 5000,
        });
    }
}

export async function getChannel(id) {
    const response = await apiGet(`${VIDEOS_API}/channels/${id}`);
    return (await response.json())['channel'];
}

export async function tagChannel(channelId, tagName, directory) {
    const body = {
        tag_name: tagName,
    }
    if (directory) {
        body['directory'] = directory;
    }
    const response = await apiPost(`${VIDEOS_API}/channels/${channelId}/tag`, body);
    if (!response.ok) {
        const message = await getErrorMessage(response, 'Failed to tag channel.  See server logs.');
        toast({
            type: 'error',
            title: 'Tagging Channel Failed',
            description: message,
            time: 5000,
        });
    }
}

export async function tagChannelInfo(channelId, tagName) {
    channelId = channelId ? parseInt(channelId) : null;
    const body = {channel_id: channelId, tag_name: tagName};
    const response = await apiPost(`${VIDEOS_API}/tag_info`, body);
    if (response.ok) {
        return (await response.json()).videos_destination;
    }
    const message = getErrorMessage(response, 'Failed to get channel tag info.');
    toast({
        type: 'error',
        title: 'Getting Channel Tag Info Failed',
        description: message,
        time: 5000,
    });
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

    const response = await apiPost(`${VIDEOS_API}/search`, body);
    if (response.status === 200) {
        let data = await response.json();
        return [data['file_groups'], data['totals']['file_groups']];
    } else {
        const message = getErrorMessage(response, 'Failed to search videos.');
        toast({
            type: 'error',
            title: 'Searching Videos failed',
            description: message,
            time: 5000,
        });
        return [[], 0];
    }
}

export async function getVideo(video_id) {
    const response = await apiGet(`${VIDEOS_API}/video/${video_id}`);
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
    const response = await apiDelete(`${VIDEOS_API}/video/${i}`);
    if (response.status !== 204) {
        const message = getErrorMessage(response, 'Failed to delete videos.');
        toast({
            type: 'error',
            title: 'Deleting Videos failed',
            description: message,
            time: 5000,
        });
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
    const response = await apiPost(`${API_URI}/files/directories`, form_data);
    if (response.ok) {
        return await response.json();
    }
    return [];
}

export async function getStatus() {
    const response = await apiGet(`${API_URI}/status`);
    if (response.status === 200) {
        return await response.json();
    } else {
        const message = getErrorMessage(response, 'Could not get server status.');
        toast({
            type: 'error',
            title: 'Fetching Status Failed',
            description: message,
            time: 5000,
        });
    }
}

export async function getSettings() {
    const response = await apiGet(`${API_URI}/settings`);
    if (response.ok) {
        return await response.json();
    } else {
        const message = getErrorMessage(response, 'Could not get settings.');
        toast({
            type: 'error',
            title: 'Fetching Settings Failed',
            description: message,
            time: 5000,
        });
    }
}

export async function saveSettings(settings) {
    const response = await apiPatch(`${API_URI}/settings`, settings);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Could not save settings.');
        toast({
            type: 'error',
            title: 'Saving Settings Failed',
            description: message,
            time: 5000,
        });
    }
    return response
}

export async function getDownloads() {
    const response = await apiGet(`${API_URI}/download`);
    if (response.ok) {
        return await response.json();
    } else {
        const message = getErrorMessage(response, 'Could not get downloads.');
        toast({
            type: 'error',
            title: 'Getting Downloads Failed',
            description: message,
            time: 5000,
        });
    }
    return response
}

export async function validateRegex(regex) {
    const response = await apiPost(`${API_URI}/valid_regex`, {regex});
    try {
        return (await response.json())['valid'];
    } catch (e) {
        return false;
    }
}

export async function getVideosStatistics() {
    const response = await apiGet(`${VIDEOS_API}/statistics`);
    if (response.status === 200) {
        return (await response.json())['statistics'];
    } else {
        const message = getErrorMessage(response, 'Could not get statistics.');
        toast({
            type: 'error',
            title: 'Getting Statistics Failed',
            description: message,
            time: 5000,
        });
    }
    return response
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
    const response = await apiPost(url, body);
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
            const message = getErrorMessage(response, 'Could not create Channel download.');
            toast({
                type: 'error',
                title: 'Creating Channel Download Failed',
                description: message,
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
    const response = await apiPut(url, body);
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
            const message = getErrorMessage(response, 'Could not update Channel download.');
            toast({
                type: 'error',
                title: 'Updating Channel Download Failed',
                description: message,
                time: 5000,
            });
        }
    }
    return response;
}

export async function refreshChannel(channelId) {
    let url = `${VIDEOS_API}/channels/refresh/${channelId}`;
    const response = await apiPost(url);
    if (!response.ok) {
        const message = getErrorMessage(response, "Failed to refresh this channel's directory");
        toast({
            type: 'error',
            title: 'Failed to refresh',
            description: message,
            time: 5000,
        })
    }
    return response;
}

export async function encryptOTP(otp, plaintext) {
    let body = {otp, plaintext};
    const response = await apiPost(`${OTP_API}/encrypt_otp`, body);
    if (response.ok) {
        return await response.json();
    } else {
        const message = getErrorMessage(response, 'Failed to encrypt OTP.  See server logs.');
        toast({
            type: 'error',
            title: 'Failed to encrypt OTP',
            description: message,
            time: 5000,
        })
    }
}

export async function decryptOTP(otp, ciphertext) {
    let body = {otp, ciphertext};
    const response = await apiPost(`${OTP_API}/decrypt_otp`, body);
    if (response.ok) {
        return await response.json();
    } else {
        const message = getErrorMessage(response, 'Failed to decrypt OTP.  See server logs.');
        toast({
            type: 'error',
            title: 'Failed to decrypt OTP',
            description: message,
            time: 5000,
        })
    }
}

export async function getCategories() {
    const response = await apiGet(`${API_URI}/inventory/categories`);
    if (response.ok) {
        return (await response.json())['categories'];
    } else {
        const message = getErrorMessage(response, 'Could not get categories');
        toast({
            type: 'error', title: 'Unexpected server response', description: message, time: 5000,
        });
    }
}

export async function getBrands() {
    const response = await apiGet(`${API_URI}/inventory/brands`);
    if (response.ok) {
        return (await response.json())['brands'];
    } else {
        const message = getErrorMessage(response, 'Could not get brands');
        toast({
            type: 'error', title: 'Unexpected server response', description: message, time: 5000,
        });
    }
}

export async function getInventories() {
    const response = await apiGet(`${API_URI}/inventory`);
    if (response.ok) {
        return (await response.json())['inventories'];
    } else {
        const message = getErrorMessage(response, 'Could not get inventories');
        toast({
            type: 'error', title: 'Unexpected server response', description: message, time: 5000,
        });
    }
}

export async function getInventory(inventoryId) {
    const response = await apiGet(`${API_URI}/inventory/${inventoryId}`);
    if (response.ok) {
        return await response.json();
    } else {
        const message = getErrorMessage(response, 'Could not get inventory');
        toast({
            type: 'error', title: 'Unexpected server response', description: message, time: 5000,
        });
    }
}

export async function saveInventory(inventory) {
    const response = await apiPost(`${API_URI}/inventory`, inventory);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Failed to save inventory');
        toast({
            type: 'error', title: 'Unexpected server response', description: message, time: 5000,
        });
    }
    return response
}

export async function updateInventory(inventoryId, inventory) {
    delete inventory['id'];
    const response = await apiPut(`${API_URI}/inventory/${inventoryId}`, inventory);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Failed to update inventory');
        toast({
            type: 'error', title: 'Unexpected server response', description: message, time: 5000,
        });
    }
    return response
}

export async function deleteInventory(inventoryId) {
    const response = await apiDelete(`${API_URI}/inventory/${inventoryId}`);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Failed to delete inventory');
        toast({
            type: 'error', title: 'Unexpected server response', description: message, time: 5000,
        });
    }
    return response
}

export async function getItems(inventoryId) {
    const response = await apiGet(`${API_URI}/inventory/${inventoryId}/item`);
    if (response.ok) {
        return await response.json();
    } else {
        const message = getErrorMessage(response, 'Failed to get items');
        toast({
            type: 'error', title: 'Unexpected server response', description: message, time: 5000,
        });
    }
    return response
}

export async function saveItem(inventoryId, item) {
    const response = await apiPost(`${API_URI}/inventory/${inventoryId}/item`, item);
    if (response.ok) {
        return await response.json();
    } else {
        const message = getErrorMessage(response, 'Failed to save item');
        toast({
            type: 'error', title: 'Unexpected server response', description: message, time: 5000,
        });
    }
    return response
}

export async function updateItem(itemId, item) {
    item = emptyToNull(item);
    const response = await apiPut(`${API_URI}/inventory/item/${itemId}`, item);
    if (response.ok) {
        return await response.json();
    } else {
        const message = getErrorMessage(response, 'Failed to update item');
        toast({
            type: 'error', title: 'Unexpected server response', description: message, time: 5000,
        });
    }
    return response
}

export async function deleteItems(itemIds) {
    let i = itemIds.join(',');
    const response = await apiDelete(`${API_URI}/inventory/item/${i}`);
    if (response.ok) {
        return await response.json();
    } else {
        const message = getErrorMessage(response, 'Failed to delete items');
        toast({
            type: 'error', title: 'Unexpected server response', description: message, time: 5000,
        });
    }
    return response
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
    if (!response.ok) {
        const message = getErrorMessage(response, 'Failed to delete archives');
        toast({
            type: 'error', title: 'Unexpected server response', description: message, time: 5000,
        });
        throw Error('Failed to delete archives');
    }
    return response
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
    const response = await apiPost(`${ARCHIVES_API}/search`, body);
    if (response.ok) {
        let data = await response.json();
        return [data['file_groups'], data['totals']['file_groups']];
    } else {
        const message = getErrorMessage(response, 'Cannot search archives.  See server logs.');
        toast({
            type: 'error',
            title: 'Unable to search archives',
            description: message,
            time: 5000,
        });
        return [[], 0];
    }
}

export async function fetchDomains() {
    const response = await apiGet(`${ARCHIVES_API}/domains`);
    if (response.ok) {
        let data = await response.json();
        return [data['domains'], data['totals']['domains']];
    } else {
        const message = getErrorMessage(response, 'Unable to fetch Domains.  See server logs.');
        toast({
            type: 'error',
            title: 'Domains Error',
            description: message,
            time: 5000,
        });
    }
}

export async function getArchive(archiveId) {
    const response = await apiGet(`${ARCHIVES_API}/${archiveId}`);
    if (response.ok) {
        const data = await response.json();
        return [data['file_group'], data['history']];
    } else {
        const message = getErrorMessage(response, 'Unable to get Archive.  See server logs.');
        toast({
            type: 'error', title: 'Archive Error', description: message, time: 5000,
        });
    }
}

function calculateDownloadSettings(excludedURLs, depth, suffix, tagNames, downloadMetadataOnly, destination, max_pages) {
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

    let settings = calculateDownloadSettings(excludedURLs, depth, suffix, tagNames, downloadMetadataOnly, destination,
        max_pages);
    let body = {
        urls: urls,
        downloader: downloader,
        sub_downloader: sub_downloader,
        frequency: frequency || null,
        settings: settings,
    };
    const response = await apiPost(`${API_URI}/download`, body);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Unable to create Download.  See server logs.');
        toast({
            type: 'error', title: 'Download Error', description: message, time: 5000,
        });
    }
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

    let settings = calculateDownloadSettings(excludedURLs)
    let body = {
        urls: urls,
        downloader: downloader,
        sub_downloader: sub_downloader,
        frequency: frequency || null,
        settings: settings,
    };
    const response = await apiPut(`${API_URI}/download/${download_id}`, body);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Unable to update Download.  See server logs.');
        toast({
            type: 'error', title: 'Download Error', description: message, time: 5000,
        });
    }
    return response;
}

export async function killDownload(download_id) {
    const response = await apiPost(`${API_URI}/download/${download_id}/kill`);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Unable to stop Download.  See server logs.');
        toast({
            type: 'error', title: 'Download Error', description: message, time: 5000,
        });
    }
    return response;
}

export async function restartDownload(download_id) {
    const response = await apiPost(`${API_URI}/download/${download_id}/restart`);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Unable to restart Download.  See server logs.');
        toast({
            type: 'error', title: 'Download Error', description: message, time: 5000,
        });
    }
    return response
}

export async function killDownloads() {
    const response = await apiPost(`${API_URI}/download/kill`);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Unable to stop downloading.  See server logs.');
        toast({
            type: 'error', title: 'Download Error', description: message, time: 5000,
        });
    }
    return response;
}

export async function startDownloads() {
    const response = await apiPost(`${API_URI}/download/enable`);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Unable to start downloading.  See server logs.');
        toast({
            type: 'error', title: 'Download Error', description: message, time: 5000,
        });
    }
    return response;
}

export async function getDownloaders() {
    try {
        const response = await apiGet(`${API_URI}/downloaders`);
        // Not toasting because this will happen often.
        return await response.json();
    } catch (e) {
        return {downloaders: []};
    }
}

export async function deleteDownload(downloadId) {
    try {
        const response = await apiDelete(`${API_URI}/download/${downloadId}`);
        if (!response.ok) {
            const message = getErrorMessage(response, 'Unable to delete the download.  See server logs.');
            toast({
                type: 'error',
                title: 'Download Error',
                description: message,
                time: 5000,
            });
        }
    } catch (e) {
        return null;
    }
}

export async function filesSearch(offset, limit, searchStr, mimetypes, model, tagNames, headline, months, fromYear, toYear, anyTag) {
    const body = {search_str: searchStr, offset: parseInt(offset), limit: parseInt(limit), any_tag: anyTag};
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

    if (response.ok) {
        let data = await response.json();
        let [file_groups, total] = [data['file_groups'], data['totals']['file_groups']];
        return [file_groups, total];
    } else {
        const message = getErrorMessage(response, 'Cannot search files.  See server logs.');
        toast({
            type: 'error',
            title: 'Unable to search files',
            description: message,
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
    if (!response.ok) {
        const message = getErrorMessage(response, 'Cannot refresh files.  See server logs.');
        toast({
            type: 'error',
            title: 'Files Error',
            description: message,
            time: 5000,
        });
    }
    return response;
}

export async function makeDirectory(path) {
    const body = {path: path};
    const response = await apiPost(`${API_URI}/files/directory`, body);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Failed to create directory.  See server logs.');
        toast({
            type: 'error',
            title: 'Unable to create directory',
            description: message,
            time: 5000,
        });
    }
}

export async function getFiles(directories) {
    console.debug(`getFiles ${directories}`);
    let body = {directories: directories || []};
    const response = await apiPost(`${API_URI}/files`, body);
    // Not toasting because this will happen often.
    let {files} = await response.json();
    return files;
}

export async function getFile(path) {
    let body = {file: path};
    const response = await apiPost(`${API_URI}/files/file`, body);
    if (response.ok) {
        const {file} = await response.json();
        return file;
    } else {
        const message = getErrorMessage(response, 'Failed to get file data.  See server logs.');
        toast({
            type: 'error',
            title: 'Files Error',
            description: message,
            time: 5000,
        });
    }
}

export async function deleteFile(paths) {
    let body = {paths: paths};
    const response = await apiPost(`${API_URI}/files/delete`, body);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Failed to delete file.  See server logs.');
        toast({
            type: 'error',
            title: 'Files Error',
            description: message,
            time: 5000,
        });
    }
    return response
}

export async function fetchFilesProgress() {
    const response = await apiGet(`${API_URI}/files/refresh_progress`);
    if (response.ok) {
        const json = await response.json();
        return json['progress'];
    }
}

export async function setHotspot(on) {
    let response;
    if (on) {
        response = await apiPost(`${API_URI}/hotspot/on`);
    } else {
        response = await apiPost(`${API_URI}/hotspot/off`);
    }
    if (response.ok) {
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
            const message = getErrorMessage(response, 'Could not modify hotspot.  See server logs.');
            toast({
                type: 'error',
                title: 'Hotspot Error',
                description: message,
                time: 5000,
            });
        }
    }
}

export async function setThrottle(on) {
    let response;
    if (on) {
        response = await apiPost(`${API_URI}/throttle/on`);
    } else {
        response = await apiPost(`${API_URI}/throttle/off`);
    }
    if (response.ok) {
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
            const message = getErrorMessage(response, 'Could not modify throttle.  See server logs.');
            toast({type: 'error', title: 'Throttle Error', description: message, time: 5000});
        }
    }
}

export async function getMapImportStatus() {
    const response = await apiGet(`${API_URI}/map/files`);
    if (response.ok) {
        return await response.json();
    } else {
        const message = getErrorMessage(response, 'Could not get import status');
        toast({type: 'error', title: 'Map Error', description: message, time: 5000});
    }
}

export async function importMapFiles(paths) {
    let body = {'files': paths};
    const response = await apiPost(`${API_URI}/map/import`, body);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Could not start import!  See server logs.');
        toast({type: 'error', title: 'Map Error', description: message, time: 5000});
    }
}

export async function clearCompletedDownloads() {
    const response = await apiPost(`${API_URI}/download/clear_completed`);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Could not clear completed downloads!  See server logs.');
        toast({type: 'error', title: 'Downloads Error', description: message, time: 5000});
    }
    return response
}

export async function deleteOnceDownloads() {
    const response = await apiPost(`${API_URI}/download/delete_once`);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Could not delete once downloads!  See server logs.');
        toast({type: 'error', title: 'Downloads Error', description: message, time: 5000});
    }
    return response
}

export async function retryOnceDownloads() {
    const response = await apiPost(`${API_URI}/download/retry_once`);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Could not retry once downloads!  See server logs.');
        toast({type: 'error', title: 'Downloads Error', description: message, time: 5000});
    }
    return response
}

export async function getStatistics() {
    const response = await apiGet(`${API_URI}/statistics`);
    if (response.ok) {
        return await response.json();
    } else {
        const message = getErrorMessage(response, 'Unable to get file statistics');
        toast({type: 'error', title: 'Error', description: message, time: 5000});
    }
}

export async function getEvents(after) {
    let uri = `${API_URI}/events/feed`;
    if (after) {
        uri = `${uri}?after=${encodeURIComponent(after)}`
    }
    const response = await apiGet(uri);
    if (response.ok) {
        return await response.json();
    }
    // Not toasting because this happens often.
    return response
}

export async function getTags() {
    const uri = `${API_URI}/tag`;
    const response = await apiGet(uri);
    if (response.ok) {
        const body = await response.json();
        return body['tags'];
    }
    // Not toasting because this happens often.
    return response
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
    const response = await apiPost(uri, body);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Unable to add tag');
        toast({type: 'error', title: 'Tag Error', description: message, time: 5000});
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
    const response = await apiPost(uri, body)
    if (!response.ok) {
        const message = getErrorMessage(response, 'Unable to untag');
        toast({type: 'error', title: 'Tag Error', description: message, time: 5000});
    }
}

export async function saveTag(name, color, id) {
    const body = {name: name, color: color};
    let uri = `${API_URI}/tag`;
    if (id) {
        uri = `${uri}/${id}`;
    }
    const response = await apiPost(uri, body);
    if (id && response.status === 200) {
        toast({
            type: 'info', title: 'Saved tag', description: `Saved tag: ${name}`, time: 2000,
        });
    } else if (response.status === 201) {
        toast({
            type: 'info', title: 'Created new tag', description: `Created new tag: ${name}`, time: 2000,
        });
    } else {
        const message = getErrorMessage(response, 'Unable to save tag');
        toast({type: 'error', title: 'Tag Error', description: message, time: 5000});
    }
}

export async function deleteTag(id, name) {
    const uri = `${API_URI}/tag/${id}`;
    const response = await apiDelete(uri);
    if (response.status === 400) {
        const content = await response.json();
        const message = getErrorMessage(response, 'Cannot delete, Tag is used');
        if (content['code'] === 'USED_TAG') {
            toast({
                type: 'error', title: 'Error!', description: message, time: 5000,
            })
        }
    } else if (!response.ok) {
        console.error('Failed to delete tag');
        const message = getErrorMessage(response, `Unable to delete tag: ${name}`);
        toast({type: 'error', title: 'Tag Error', description: message, time: 5000});
    }
}

export async function fetchFile(path) {
    const uri = `${API_URI}/files/file`;
    const body = {file: path};
    const response = await apiPost(uri, body);
    if (response.ok) {
        const content = await response.json();
        return content['file'];
    } else {
        console.error('Unable to fetch file dict!  See client logs.');
        const message = getErrorMessage(response, 'Unable to get File');
        toast({type: 'error', title: 'File Error', description: message, time: 5000});
    }
}

export async function sendNotification(message, url) {
    const body = {message, url};
    const response = await apiPost(`${API_URI}/notify`, body);
    if (response.status === 201) {
        toast({type: 'success', title: 'Shared', description: 'Your share was sent', time: 2000});
    } else {
        const message = getErrorMessage(response, 'Your share failed to send!');
        toast({type: 'error', title: 'Error', description: message, time: 5000});
    }
}

export async function searchDirectories(name) {
    const body = {name: name || ''};
    const response = await apiPost(`${API_URI}/files/search_directories`, body);
    if (response.status === 204) {
        return [];
    } else if (response.status === 200) {
        return await response.json();
    } else {
        const message = getErrorMessage(response, 'Failed to search directories!');
        toast({type: 'error', title: 'Error', description: message, time: 5000});
    }
}

export async function renamePath(path, newName) {
    const body = {path, new_name: newName};
    const response = await apiPost(`${API_URI}/files/rename`, body);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Failed to rename!');
        toast({type: 'error', title: 'Error', description: message, time: 5000});
    }
}

export async function movePaths(destination, paths) {
    const body = {destination, paths};
    const response = await apiPost(`${API_URI}/files/move`, body);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Failed to move!');
        toast({type: 'error', title: 'Error', description: message, time: 5000});
    }
}

export async function ignoreDirectory(directory) {
    const body = {path: directory};
    const response = await apiPost(`${API_URI}/files/ignore_directory`, body);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Failed to ignore directory!');
        toast({type: 'error', title: 'Error', description: message, time: 5000});
    }
}

export async function unignoreDirectory(directory) {
    const body = {path: directory};
    const response = await apiPost(`${API_URI}/files/unignore_directory`, body);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Failed to unignore directory!');
        toast({type: 'error', title: 'Error', description: message, time: 5000});
    }
}

export async function fetchZims() {
    const response = await apiGet(`${API_URI}/zim`);
    if (response.ok) {
        const content = await response.json();
        return {
            zims: content['zims'],
        }
    } else {
        const message = getErrorMessage(response, 'Cannot fetch Zims');
        toast({type: 'error', title: 'Error', description: message, time: 5000});
    }
}

export async function fetchZimSubscriptions() {
    const response = await apiGet(`${API_URI}/zim/subscribe`);
    if (response.ok) {
        const content = await response.json();
        return {
            subscriptions: content['subscriptions'],
            catalog: content['catalog'],
            iso_639_codes: content['iso_639_codes'],
        }
    } else {
        const message = getErrorMessage(response, 'Cannot fetch Zim Subscriptions');
        toast({type: 'error', title: 'Error', description: message, time: 5000});
    }
}

export async function searchZim(offset, limit, searchStr, zimId, activeTags) {
    offset = parseInt(offset || 0);
    limit = parseInt(limit || DEFAULT_LIMIT);
    let body = {offset, limit, search_str: searchStr, tag_names: activeTags || []};

    console.debug(`Searching Zim ${zimId} for: ${searchStr} tags: ${activeTags}`);
    const response = await apiPost(`${ZIM_API}/search/${zimId}`, body);
    if (response.ok) {
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
    const response = await apiPost(uri, body);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Failed to add zim tag');
        toast({type: 'error', title: 'Error', description: message, time: 5000});
    }
}

export async function untagZimEntry(zim_id, zim_entry, name) {
    const body = {tag_name: name, zim_id: zim_id, zim_entry: zim_entry};

    const uri = `${API_URI}/zim/untag`;
    const response = await apiPost(uri, body);
    if (!response.ok) {
        const message = getErrorMessage(response, 'Failed to untag zim');
        toast({type: 'error', title: 'Error', description: message, time: 5000});
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
    } else {
        console.error('Failed to get file search suggestions!');
    }
}

export async function searchEstimateFiles(search_str, tagNames, mimetypes, months, dateRange, anyTag) {
    months = months ? months.map(i => parseInt(i)) : [];

    const body = {search_str, tag_names: tagNames, mimetypes, months, any_tag: anyTag};
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
    } else {
        console.error('Failed to get file search estimates!');
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

export async function searchEstimateOthers(tagNames) {
    const body = {tag_names: tagNames};
    const response = await apiPost(`${API_URI}/search_other_estimates`, body);
    if (response.ok) {
        const content = await response.json();
        return {
            others: content.others,
        }
    }
}

export async function searchChannels(tagNames) {
    const body = {tag_names: tagNames};
    const response = await apiPost(`${API_URI}/videos/channels/search`, body);
    if (response.ok) {
        const content = await response.json();
        return {
            channels: content.channels,
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
        const message = getErrorMessage(response, 'Cannot fetch outdated Zims.  See server logs.');
        toast({
            type: 'error',
            title: 'Error',
            description: message,
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
