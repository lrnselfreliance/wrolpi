import {API_URI, DEFAULT_LIMIT, VIDEOS_API} from "./components/Common";

export async function updateChannel(link, channel) {
    let response = await fetch(`${VIDEOS_API}/channels/${link}`,
        {method: 'PUT', body: JSON.stringify(channel)});

    if (response.status !== 204) {
        throw Error('Failed to update channel.  See browser logs.');
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

export async function getVideos(offset, limit, channel_link, search_str, favorites) {
    // Build a search query to retrieve a list of videos from the API
    offset = offset || 0;
    limit = limit || DEFAULT_LIMIT;
    let body = {offset, limit, favorites: !!favorites};

    if (search_str) {
        body.search_str = search_str;
    }
    if (channel_link) {
        body.channel_link = channel_link;
    }

    let response = await fetch(`${VIDEOS_API}/search`, {method: 'POST', body: JSON.stringify(body)});
    if (response.status === 200) {
        let data = await response.json();
        return [data['videos'], data['totals']['videos']];
    } else {
        throw Error(`Unable to search videos`);
    }
}

export async function getVideo(video_id) {
    let response = await fetch(`${VIDEOS_API}/video/${video_id}`);
    let data = await response.json();
    return data['video'];
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

export async function favoriteVideo(event, video_id, favorite) {
    event.preventDefault();
    let url = `${VIDEOS_API}:favorite`;
    let body = {favorite: favorite, video_id};
    await fetch(url, {method: 'POST', body: JSON.stringify(body)});
}
