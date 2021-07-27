import {API_URI, DEFAULT_LIMIT, VIDEOS_API} from "./components/Common";
import {toast} from 'react-semantic-toasts';

function timeoutPromise(ms, promise) {
    // Create a timeout wrapper around a promise.  If the timeout is reached, throw an error.  Otherwise, return
    // the results of the promise.
    return new Promise((resolve, reject) => {
        const timeoutId = setTimeout(() => {
            reject(new Error("promise timeout"))
        }, ms);
        promise.then(
            (res) => {
                clearTimeout(timeoutId);
                resolve(res);
            },
            (err) => {
                clearTimeout(timeoutId);
                reject(err);
            }
        );
    })
}

async function apiCall(url, method, body, ms = 3000) {
    let init = {method};
    if (body !== undefined) {
        init.body = JSON.stringify(body);
    }

    // Create a fetch promise, this will be awaited by the timeout.
    let promise = fetch(url, init);

    try {
        // await the response or error.
        return await timeoutPromise(ms, promise);
    } catch (e) {
        // Timeout, or some other exception.
        if (e.message === 'promise timeout') {
            toast({
                type: 'error',
                title: 'Server failed to respond!',
                description: 'Timeout while waiting for server response.  See server logs.',
                time: 5000,
            });
        } else {
            toast({
                type: 'error',
                title: 'Error!',
                description: 'See client logs',
                time: 5000,
            });
        }
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


export async function updateChannel(link, channel) {
    return await apiPut(`${VIDEOS_API}/channels/${link}`, channel);
}

export async function createChannel(channel) {
    return await apiPost(`${VIDEOS_API}/channels`, channel);
}

export async function deleteChannel(channel_link) {
    return apiDelete(`${VIDEOS_API}/channels/${channel_link}`);
}

export async function getChannels() {
    let response = await apiGet(`${VIDEOS_API}/channels`);
    return (await response.json())['channels'];
}

export async function getChannel(link) {
    let response = await apiGet(`${VIDEOS_API}/channels/${link}`);
    return (await response.json())['channel'];
}

export async function searchVideos(offset, limit, channel_link, searchStr, favorites, order_by) {
    // Build a search query to retrieve a list of videos from the API
    offset = offset || 0;
    limit = limit || DEFAULT_LIMIT;
    let body = {offset, limit, favorites: favorites};

    if (searchStr) {
        body.search_str = searchStr;
    }
    if (channel_link) {
        body.channel_link = channel_link;
    }
    body.order_by = order_by ? order_by : 'rank'

    let response = await apiPost(`${VIDEOS_API}/search`, body);
    if (response.status === 200) {
        let data = await response.json();
        return [data['videos'], data['totals']['videos']];
    } else {
        throw Error(`Unable to search videos`);
    }
}

export async function getVideo(video_id) {
    let response = await apiGet(`${VIDEOS_API}/video/${video_id}`);
    let data = await response.json();
    return [data['video'], data['prev'], data['next']];
}

export async function deleteVideo(video_id) {
    let response = await apiDelete(`${VIDEOS_API}/video/${video_id}`);
    let data = await response.json();
    if (data.code === 17) {
        toast({
            type: 'warning',
            title: 'WROL Mode Enabled',
            description: 'This cannot be done while WROL Mode is enabled.',
            time: 5000,
        });
        throw Error('WROL Mode enabled');
    }
    if (response.status !== 204) {
        toast({
            type: 'error',
            title: 'Unexpected server response',
            description: 'Failed to delete video.  See server logs.',
            time: 5000,
        });
        throw Error('Failed to delete video');
    }
}

export async function getDirectories(search_str) {
    let form_data = {'search_str': search_str || null};
    let response = await apiPost(`${VIDEOS_API}/directories`, form_data);
    if (response.status === 200) {
        return (await response.json())['directories'];
    }
    return [];
}

export async function getConfig() {
    let response = await apiGet(`${API_URI}/settings`);
    let data = await response.json();
    return data['config'];
}

export async function saveConfig(config) {
    return await apiPatch(`${API_URI}/settings`, config);
}

export async function validateRegex(regex) {
    let response = await apiPost(`${API_URI}/valid_regex`, {regex});
    return (await response.json())['valid'];
}

export async function favoriteVideo(video_id, favorite) {
    let body = {favorite: favorite, video_id};
    let response = await apiPost(`${VIDEOS_API}:favorite`, body);
    return (await response.json())['favorite'];
}

export async function getStatistics() {
    let response = await apiGet(`${VIDEOS_API}/statistics`);
    return (await response.json())['statistics'];
}

export async function refresh() {
    let response = await apiPost(`${VIDEOS_API}:refresh`);
    return await response.json();
}

export async function download() {
    let response = await apiPost(`${VIDEOS_API}:download`);
    return await response.json();
}

export async function downloadChannel(link) {
    let url = `${VIDEOS_API}:download/${link}`;
    await fetch(url, {method: 'POST'});
}

export async function refreshChannel(link) {
    let url = `${VIDEOS_API}:refresh/${link}`;
    await fetch(url, {method: 'POST'});
}

export async function encryptOTP(otp, plaintext) {
    let body = {otp, plaintext};
    let response = await apiPost(`${API_URI}:encrypt_otp`, body);
    if (response.status !== 200) {
        toast({
            type: 'error',
            title: 'Error!',
            description: 'Failed to encrypt OTP',
            time: 5000,
        });
        return;
    }
    return await response.json();
}

export async function decryptOTP(otp, ciphertext) {
    let body = {otp, ciphertext};
    let response = await apiPost(`${API_URI}:decrypt_otp`, body);
    if (response.status !== 200) {
        toast({
            type: 'error',
            title: 'Error!',
            description: 'Failed to decrypt OTP',
            time: 5000,
        });
        return;
    }
    return await response.json();
}

export async function getCategories() {
    let response = await apiGet(`${API_URI}/inventory/categories`);
    return (await response.json())['categories'];
}

export async function getBrands() {
    let response = await apiGet(`${API_URI}/inventory/brands`);
    return (await response.json())['brands'];
}

export async function getInventories() {
    let response = await apiGet(`${API_URI}/inventory`);
    return (await response.json())['inventories'];
}

export async function getInventory(inventoryId) {
    let response = await apiGet(`${API_URI}/inventory/${inventoryId}`);
    return await response.json();
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
    return await apiPut(`${API_URI}/inventory/item/${itemId}`, item);
}

export async function deleteItems(itemIds) {
    let i = itemIds.join(',');
    await apiDelete(`${API_URI}/inventory/item/${i}`);
}
