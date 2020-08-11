import {Card, Form, Placeholder} from "semantic-ui-react";
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

export function FieldPlaceholder() {
    return (
        <Form.Field>
            <Placeholder style={{'marginBottom': '0.5em'}}>
                <Placeholder.Line length="short"/>
            </Placeholder>
            <input disabled/>
        </Form.Field>
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
