import {CardContent, CardGroup, PlaceholderImage, PlaceholderLine} from "semantic-ui-react";
import React, {useContext} from "react";
import {ThemeContext} from "../contexts/contexts";
import {Card, Placeholder} from "./Theme";

export function CardPlaceholder() {
    const {s} = useContext(ThemeContext);

    return <Card>
        <Placeholder>
            <PlaceholderImage rectangular/>
        </Placeholder>
        <CardContent {...s}>
            <Placeholder>
                <PlaceholderLine/>
                <PlaceholderLine/>
                <PlaceholderLine/>
            </Placeholder>
        </CardContent>
    </Card>
}

export function VideoPlaceholder() {
    return <CardGroup doubling stackable>
        <CardPlaceholder/>
    </CardGroup>
}

export function ChannelPlaceholder() {
    return <Placeholder>
        <PlaceholderLine length='long'/>
        <PlaceholderLine length='short'/>
    </Placeholder>
}

export function ProgressPlaceholder() {
    return <Placeholder style={{marginBottom: '1em'}}>
        <PlaceholderLine/>
        <PlaceholderLine/>
    </Placeholder>
}

export function TextPlaceholder() {
    return <Placeholder style={{marginBottom: '1em'}}>
        <PlaceholderLine/>
        <PlaceholderLine/>
        <PlaceholderLine/>
    </Placeholder>
}

export function TagPlaceholder() {
    return <Placeholder style={{height: 30, width: 80}}>
        <PlaceholderImage/>
    </Placeholder>
}

export function TableRowPlaceholder() {
    return <Placeholder>
        <PlaceholderLine/>
    </Placeholder>
}