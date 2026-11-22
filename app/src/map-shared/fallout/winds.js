// The forecast winds aloft (as the API gives them: modules/map/winds.py), as the fallout model reads
// them.  Shared by the app's map viewer and the standalone viewer: no imports from the app, no
// dependencies.
//
// A forecast is {lat, lon, elevation (m, of the forecast's ground), fetched_at, hours: [{time,
// precipitation (mm in the hour), winds: [[height (m above sea level), speed (m/s), direction the
// wind blows FROM (degrees)]]}]}.

// The hour of `forecast` nearest `when` (a Date): its index.
export function nearestHour(forecast, when = new Date()) {
    let best = 0, gap = Infinity;
    forecast.hours.forEach((hour, i) => {
        const g = Math.abs(Date.parse(hour.time) - when.getTime());
        if (g < gap) {
            best = i;
            gap = g;
        }
    });
    return best;
}

// The winds of `hour` as a profile the model takes: [[height above ground zero (m), east (m/s),
// north (m/s)]], for ground zero `groundElevation` m above sea level.  A wind below ground zero is
// kept: a valley's ground may be lower.
export function forecastProfile(hour, groundElevation) {
    return hour.winds.map(([height, speed, from]) => {
        const toward = (from + 180) * Math.PI / 180;
        return [height - groundElevation, speed * Math.sin(toward), speed * Math.cos(toward)];
    });
}

// How much rain (mm) the forecast has from hour `index` for `hours` hours: rain washes fallout down in
// places the model does not show.
export function rainAhead(forecast, index, hours = 6) {
    return forecast.hours.slice(index, index + hours).reduce((a, h) => a + (h.precipitation || 0), 0);
}

// How old (hours) `forecast` was at `when`.
export function forecastAge(forecast, when = new Date()) {
    return (when.getTime() - Date.parse(forecast.fetched_at)) / 3600000;
}

// Whether `forecast` runs out before `when`: the last hour it has is before it.
export function forecastExpired(forecast, when = new Date()) {
    return Date.parse(forecast.hours[forecast.hours.length - 1].time) < when.getTime();
}
