import {Card, PlaceholderImage, PlaceholderLine} from "semantic-ui-react";
import React, {useContext} from "react";
import {ThemeContext} from "../contexts/contexts";
import {Placeholder} from "./Theme";

export function CardPlacholder() {
    const {s} = useContext(ThemeContext);

    return <Card>
        <Placeholder>
            <PlaceholderImage rectangular/>
        </Placeholder>
        <Card.Content {...s}>
            <Placeholder>
                <PlaceholderLine/>
                <PlaceholderLine/>
                <PlaceholderLine/>
            </Placeholder>
        </Card.Content>
    </Card>
}

export function VideoPlaceholder() {
    return (
        <Card.Group doubling stackable>
            <CardPlacholder/>
        </Card.Group>
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
