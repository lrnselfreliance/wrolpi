import {CardContent, CardGroup, PlaceholderImage, PlaceholderLine} from "semantic-ui-react";
import React, {useContext} from "react";
import {ThemeContext} from "../contexts/contexts";
import {Card, Placeholder} from "./Theme";

export function CardPlacholder() {
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
    return (
        <CardGroup doubling stackable>
            <CardPlacholder/>
        </CardGroup>
    )
}

export function ChannelPlaceholder() {
    return (
        <Placeholder>
            <PlaceholderLine length='long'/>
            <PlaceholderLine length='short'/>
        </Placeholder>
    )
}

export function ProgressPlaceholder() {
    return <Placeholder style={{marginBottom: '1em'}}>
        <PlaceholderLine/>
        <PlaceholderLine/>
    </Placeholder>
}
