import {Card, Placeholder} from "semantic-ui-react";
import React from "react";

export function VideoPlaceholder() {
    return (
        <Card.Group doubling stackable>
            <Card>
                <Placeholder>
                    <Placeholder.Image rectangular/>
                </Placeholder>
                <Card.Content>
                    <Placeholder>
                        <Placeholder.Line/>
                        <Placeholder.Line/>
                        <Placeholder.Line/>
                    </Placeholder>
                </Card.Content>
            </Card>
        </Card.Group>
    )
}

export function ChannelPlaceholder() {
    return (
        <Placeholder>
            <Placeholder.Line length='long'/>
            <Placeholder.Line length='short'/>
        </Placeholder>
    )
}

export function ArchivePlaceholder() {
    return (
        <Card.Group doubling stackable>
            <Card>
                <Placeholder>
                    <Placeholder.Image rectangular/>
                </Placeholder>
                <Card.Content>
                    <Placeholder>
                        <Placeholder.Line/>
                        <Placeholder.Line/>
                    </Placeholder>
                    <Placeholder style={{height: 40, width: 40}}>
                        <Placeholder.Image rectangular/>
                    </Placeholder>
                </Card.Content>
            </Card>
        </Card.Group>
    )
}
