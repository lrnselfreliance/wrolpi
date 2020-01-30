import {VIDEOS_API} from "./components/Common";

export async function updateChannel(channel, name_ref, url_ref, directory_ref, mkdir_ref, matchRegex_ref) {
    let name = name_ref.current.value;
    let url = url_ref.current.value;
    let directory = directory_ref.current.value;
    let mkdir = mkdir_ref.current.value;
    let matchRegex = matchRegex_ref.current.value;
    let body = {name, url, directory, mkdir, match_regex: matchRegex};

    let response = await fetch(`${VIDEOS_API}/channels/${channel['link']}`,
        {method: 'PUT', body: JSON.stringify(body)});

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
    let response = await fetch(`${VIDEOS_API}/channels/${link}/videos?offset=${offset}&limit=${limit}`);
    if (response.status === 200) {
        let data = await response.json();
        return [data['videos'], data['total']];
    } else {
        throw Error('Unable to fetch videos for channel');
    }
}

export async function getVideo(video_hash) {
    let response = await fetch(`${VIDEOS_API}/video/${video_hash}`);
    let data = await response.json();
    return data['video'];
}

export async function getRecentVideos(offset) {
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