import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import React from "react";
import {Header} from "../Theme";
import QRCode from "react-qr-code";
import {Input} from "semantic-ui-react";
import {Media} from "../../contexts/contexts";

export function QRCodeCalculator() {
    const [value, setValue] = React.useState('');

    return <Grid>
        <Grid.Row>
            <Grid.Column>
                <Header as='h1'>QR Code Calculator</Header>
            </Grid.Column>
        </Grid.Row>
        <Grid.Row>
            <Grid.Column>
                <Input fluid value={value} onChange={e => setValue(e.target.value)} placeholder='Enter link, etc.'/>
            </Grid.Column>
        </Grid.Row>
        <Grid.Row>
            <Grid.Column>
                <Media at='mobile'>
                    <div style={{
                        height: "auto",
                        margin: "0 auto",
                        width: '332px',
                        background: 'white',
                        padding: '16px'
                    }}>
                        <QRCode value={value} size={300}/>
                    </div>
                </Media>
                <Media greaterThanOrEqual='tablet'>
                    <div style={{
                        height: "auto",
                        margin: "0 auto",
                        maxWidth: '632px',
                        width: "100%",
                        background: 'white',
                        padding: '16px'
                    }}>
                        <QRCode value={value} size={600}/>
                    </div>
                </Media>
            </Grid.Column>
        </Grid.Row>
    </Grid>
}