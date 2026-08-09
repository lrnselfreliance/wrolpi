import React from "react";
import {Card, CardGroup, Placeholder, Skeleton} from "./ui";

export function CardPlaceholder() {
    return <Card media={<Skeleton height={140} radius={0} animate/>}>
        <Placeholder lines={3}/>
    </Card>
}

export function VideoPlaceholder() {
    return <CardGroup>
        <CardPlaceholder/>
    </CardGroup>
}

export function ChannelPlaceholder() {
    return <Placeholder lines={2}/>
}

export function ProgressPlaceholder() {
    return <div style={{marginBottom: '1em'}}>
        <Placeholder lines={2}/>
    </div>
}

export function TextPlaceholder() {
    return <div style={{marginBottom: '1em'}}>
        <Placeholder lines={3}/>
    </div>
}

export function TagPlaceholder() {
    return <Skeleton height={30} width={80} radius={0} animate/>
}

export function TableRowPlaceholder() {
    return <Placeholder lines={1}/>
}
