import {API_URI, VIDEOS_API} from "./components/Common";

export async function updateChannel(link, channel) {
    let response = await fetch(`${VIDEOS_API}/channels/${link}`,
        {method: 'PUT', body: JSON.stringify(channel)});

    if (response.status !== 204) {
        throw Error('Failed to update channel.  See browser logs.');
    }
}

export async function deleteChannel(channel) {
    let response = await fetch(`${VIDEOS_API}/channels/${channel['link']}`, {method: 'DELETE'});

    if (response.status !== 204) {
        throw Error('Failed to delete channel.  See browser logs.');
    }
}

export async function getChannels() {
    let url = `${VIDEOS_API}/channels`;
    let response = await fetch(url);
    let data = await response.json();
    return data['channels'];
}

export async function getChannel(link) {
    let response = await fetch(`${VIDEOS_API}/channels/${link}`);
    let data = await response.json();
    return data['channel'];
}

export async function getChannelVideos(link, offset, limit) {
    offset = offset || 0;
    limit = limit || 20;
    let response = await fetch(`${VIDEOS_API}/channels/${link}/videos?offset=${offset}&limit=${limit}`);
    if (response.status === 200) {
        let data = await response.json();
        return [data['videos'], data['total']];
    } else {
        throw Error('Unable to fetch videos for channel');
    }
}

export async function getVideo(video_id) {
    let response = await fetch(`${VIDEOS_API}/video/${video_id}`);
    let data = await response.json();
    return data['video'];
}

export async function getNewestVideos(offset) {
    offset = offset || 0;
    let response = await fetch(`${VIDEOS_API}/recent?offset=${offset}`);
    if (response.status === 200) {
        let data = await response.json();
        return [data['videos'], data['total']];
    } else {
        throw Error('Unable to fetch recent videos');
    }
}

export async function getSearchVideos(search_str, offset) {
    let form_data = {search_str: search_str, offset: offset};
    let response = await fetch(`${VIDEOS_API}/search`, {
        method: 'POST',
        body: JSON.stringify(form_data),
    });
    let data = await response.json();

    let videos = [];
    let total = null;
    if (data['videos']) {
        videos = data['videos'];
        total = data['totals']['videos'];
    }
    return [videos, total];
}

export async function getDirectories(search_str) {
    let form_data = {search_str};
    let response = await fetch(`${VIDEOS_API}/directories`, {
        method: 'post',
        body: JSON.stringify(form_data),
    });
    if (response.status === 200) {
        let data = await response.json();
        let directories = data['directories'];
        return directories;
    }
    return [];
}

export async function getConfig() {
    let url = `http://${API_URI}/api/settings`;
    let response = await fetch(url);
    let data = await response.json();
    return data['config'];
}

export async function saveConfig(config) {
    let url = `http://${API_URI}/api/settings`;
    await fetch(url, {method: 'PUT', body: JSON.stringify(config)});
}

export async function validateRegex(regex) {
    let url = `http://${API_URI}/api/valid_regex`;
    let body = {regex: regex};
    let response = await fetch(url, {method: 'POST', body: JSON.stringify(body)});
    return (await response.json())['valid'];
}
