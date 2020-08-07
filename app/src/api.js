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
    let form_data = {search_str};
    let response = await apiGet(`${VIDEOS_API}/directories`, {
        method: 'post',
        body: JSON.stringify(form_data),
    });
    if (response.status === 200) {
        return (await response.json())['directories'];
    }
    return [];
}

export async function getConfig() {
    let response = await apiGet(`http://${API_URI}/api/settings`);
    let data = await response.json();
    return data['config'];
}

export async function saveConfig(config) {
    return await apiPatch(`http://${API_URI}/api/settings`, config);
}

export async function validateRegex(regex) {
    let response = await apiPost(`http://${API_URI}/api/valid_regex`, {regex});
    return (await response.json())['valid'];
}

export async function favoriteVideo(video_id, favorite) {
    let body = {favorite: favorite, video_id};
    let response = await apiPost(`${VIDEOS_API}:favorite`, body);
    return (await response.json())['favorite'];
}
