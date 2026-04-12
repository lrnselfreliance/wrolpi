import React, {useEffect, useState} from "react";
import {Link, useNavigate} from "react-router";
import {CardContent, CardDescription, CardGroup, CardHeader, CardMeta} from "semantic-ui-react";
import {getMapSearchStatus, searchMap} from "../api";
import {Card, Header, Loader, Segment} from "./Theme";
import {Paginator} from "./Common";
import {useLatestRequest, usePages} from "../hooks/customHooks";
import {QueryContext, ThemeContext} from "../contexts/contexts";
import {MAP_VIEWER_URI} from "./Vars";

function formatPopulation(pop) {
    if (!pop) return null;
    if (pop >= 1_000_000) return `${(pop / 1_000_000).toFixed(1)}M`;
    if (pop >= 1_000) return `${Math.round(pop / 1_000)}K`;
    return `${pop}`;
}

function MapPlaceCard({place, index}) {
    const navigate = useNavigate();
    const {s} = React.useContext(ThemeContext);
    const [iframeSrc, setIframeSrc] = useState(null);

    const zoom = place.min_zoom ? Math.max(8, Math.round(13 - place.min_zoom / 3)) : 11;
    const embedSrc = `${MAP_VIEWER_URI}/embed.html#${place.lat},${place.lon},${zoom}`;

    // Stagger iframe loading to avoid overwhelming the map viewer with simultaneous requests.
    useEffect(() => {
        const timer = setTimeout(() => setIframeSrc(embedSrc), 100 + index * 200);
        return () => clearTimeout(timer);
    }, [embedSrc, index]);

    const handleClick = () => {
        navigate(`/map?lat=${place.lat}&lon=${place.lon}&z=${zoom}`);
    };

    const subtitle = [];
    if (place.region) subtitle.push(place.region);
    const detail = place.kind_detail || place.kind || "";
    if (detail && !place.region) subtitle.push(detail.replace(/_/g, " "));
    const pop = formatPopulation(place.population);
    if (pop) subtitle.push(`pop. ${pop}`);

    return <Card onClick={handleClick} style={{cursor: "pointer"}}>
        <div style={{height: 150, overflow: "hidden", position: "relative", background: "#1a1a2e"}}>
            {iframeSrc && <iframe
                src={iframeSrc}
                title={place.name}
                loading="lazy"
                style={{
                    width: "100%",
                    height: "100%",
                    border: "none",
                    pointerEvents: "none",
                }}
            />}
        </div>
        <CardContent {...s}>
            <CardHeader {...s}>{place.name}</CardHeader>
            {subtitle.length > 0 && <CardMeta {...s}>{subtitle.join(" \u00b7 ")}</CardMeta>}
            <CardDescription {...s}>
                {place.lat.toFixed(4)}, {place.lon.toFixed(4)}
            </CardDescription>
        </CardContent>
    </Card>;
}

export function MapSearchView() {
    const {searchParams} = React.useContext(QueryContext);
    const searchStr = searchParams.get("q") || "";
    const {offset, limit, activePage, setPage, totalPages, setTotal} = usePages(12);
    // useLatestRequest discards stale responses and catches errors, so rapid pagination
    // can't show out-of-order results and a network failure can't leave the spinner stuck.
    const {data, sendRequest, loading} = useLatestRequest(300);
    const [hasMaps, setHasMaps] = useState(null);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            const status = await getMapSearchStatus();
            if (!cancelled) {
                const installed = (status.indexed || []).length + (status.missing || []).length;
                setHasMaps(installed > 0);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        if (!searchStr || searchStr.length < 2) {
            setTotal(0);
            return;
        }
        sendRequest(async () => await searchMap(searchStr, limit, offset));
    }, [searchStr, offset, limit, sendRequest]);

    const results = (data && data.results) || [];
    useEffect(() => {
        setTotal((data && data.total) || 0);
    }, [data, setTotal]);

    if (hasMaps === false) {
        return <Segment>
            <Header as="h4">No maps are installed.</Header>
            <p>Subscribe to a map region to search for places.</p>
            <Link to="/map/manage">Go to Map Manager</Link>
        </Segment>;
    }

    if (loading) {
        return <Segment><Loader active inline="centered"/></Segment>;
    }

    if (!searchStr) {
        return <Segment><Header as="h4">Enter a search query to find map locations.</Header></Segment>;
    }

    if (results.length === 0) {
        return <Segment><Header as="h4">No map locations found for "{searchStr}".</Header></Segment>;
    }

    return <React.Fragment>
        <CardGroup itemsPerRow={3} stackable style={{marginTop: "1em"}}>
            {results.map((place, i) =>
                <MapPlaceCard key={`${place.name}-${place.lat}-${place.lon}-${i}`} place={place} index={i}/>
            )}
        </CardGroup>
        <center style={{marginTop: '2em'}}>
            <Paginator activePage={activePage} totalPages={totalPages} onPageChange={setPage}/>
        </center>
    </React.Fragment>;
}
