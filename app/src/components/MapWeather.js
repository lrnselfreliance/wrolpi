import React, {useCallback, useEffect, useState} from "react";
import {downloadWeatherNow, getWeather, setWeatherSubscription} from "../api";
import {ErrorMessage, humanFileSize} from "./Common";
import {Button, Header, Toggle} from "./ui";
import {LANDING_HOURS} from "../map-shared/fallout/winds.js";

// The weather subscription: a forecast of the winds aloft around the saved nuclear targets,
// downloaded every day (a recurring Download), for the fallout simulator.

// How often (ms) the subscription is asked again while it downloads.
const REFRESH_MS = 10000;

// Whether a download of the weather is waiting or running.
export const weatherDownloading = (weather) => ['new', 'pending'].includes(weather?.download?.status);

// The weather subscription, asked again while it downloads: {weather (null while pending, undefined
// when it could not be fetched), downloading, setEnabled(enabled), downloadNow()}.
export function useWeather() {
    const [weather, setWeather] = useState(null);
    const refresh = useCallback(async () => setWeather(await getWeather()), []);
    useEffect(() => {
        refresh();
    }, [refresh]);
    const downloading = weatherDownloading(weather);
    useEffect(() => {
        if (!downloading) return;
        const timer = setInterval(refresh, REFRESH_MS);
        return () => clearInterval(timer);
    }, [downloading, refresh]);
    const setEnabled = async (enabled) => {
        const changed = await setWeatherSubscription(enabled);
        if (changed) setWeather(changed);
    };
    const downloadNow = async () => {
        const changed = await downloadWeatherNow();
        if (changed) setWeather(changed);
    };
    return {weather, downloading, setEnabled, downloadNow};
}

// Whether the forecast kept (`field`, as the subscription tells it) has the winds for bursts now,
// until all their fallout is down.
export function fieldCoversNow(field, when = new Date()) {
    if (!field) return false;
    const first = Date.parse(field.first_hour), last = Date.parse(field.last_hour);
    return first <= when.getTime() + 3600000 && last >= when.getTime() + LANDING_HOURS * 3600000;
}

// About how long a download takes, as the user reads it.
export const downloadTime = (seconds) => !seconds || seconds < 60 ? "about a minute"
    : `about ${Math.round(seconds / 60) + 1} minutes`;

const when = (time) => time ? new Date(time).toLocaleString(undefined, {
    weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
}) : null;

// The Manage tab's section for the weather subscription: turning it on or off, what it downloads,
// how its downloads have gone, and the forecast kept.
export function WeatherSection() {
    const {weather, downloading, setEnabled, downloadNow} = useWeather();
    const muted = {color: "var(--muted)", fontSize: "0.875rem"};
    const warning = {color: "var(--warning)", fontSize: "0.875rem"};
    const header = <Header as='h3'>Weather</Header>;
    if (weather === undefined) return <>{header}<ErrorMessage>Could not fetch the weather subscription</ErrorMessage></>;
    if (!weather) return header;
    const {download, field} = weather;
    const failed = download && ['failed', 'deferred'].includes(download.status) && download.error;
    return <>
        {header}
        <Toggle label="Download the weather forecast from Open-Meteo every day" checked={weather.enabled}
                onChange={(e) => setEnabled(e.currentTarget.checked)}/>
        <div style={muted}>
            The winds aloft, hour by hour for four days, around the saved nuclear targets: the fallout simulator
            carries fallout by them.  Open-Meteo is told only places on whole degrees, never a target.
        </div>
        {weather.targets === 0
            ? <div style={warning}>
                No nuclear targets are saved, so there is nowhere to download the forecast around. Save some in
                nuclear mode (☢) on the map.
            </div>
            : <div style={muted}>
                Around {weather.targets === 1 ? "1 target" : `${weather.targets} targets`}: {weather.points} places
                every {weather.spacing}°, which takes {downloadTime(weather.seconds)} to download.
            </div>}
        {weather.enabled && <div style={{marginTop: "0.5rem"}}>
            {downloading && <div>Downloading the forecast…</div>}
            {download?.last_successful_download && <div style={muted}>
                Last downloaded {when(download.last_successful_download)}.
                {download.next_download && !downloading && ` Next ${when(download.next_download)}.`}
            </div>}
            {failed && <div style={warning}>The last download failed: {download.error}</div>}
            <Button size='xs' style={{marginTop: "0.25rem"}} disabled={downloading || weather.targets === 0}
                    onClick={downloadNow}>Download now</Button>
        </div>}
        <div style={{marginTop: "0.5rem"}}>
            {field
                ? <>
                    <div>
                        Forecast kept: {when(field.first_hour)} to {when(field.last_hour)}, {field.points} places
                        every {field.spacing}°, {humanFileSize(field.size)}.
                    </div>
                    {fieldCoversNow(field)
                        ? <div style={muted}>It has the winds for bursts now, until their fallout is down.</div>
                        : <div style={warning}>
                            It is too old for bursts now: their fallout comes down over {LANDING_HOURS} hours, past
                            its end. {weather.enabled ? "Download it again." : "Turn on the download to get a new one."}
                        </div>}
                </>
                : <div style={muted}>No forecast has been downloaded.</div>}
        </div>
    </>;
}
