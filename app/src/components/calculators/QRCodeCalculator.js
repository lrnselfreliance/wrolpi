import React from "react";
import QRCode from "react-qr-code";
import {Header, Stack, TextInput} from "../ui";
import {Media} from "../../contexts/contexts";

export function QRCodeCalculator() {
    const [value, setValue] = React.useState('');

    return <Stack>
        <Header as='h1'>QR Code Calculator</Header>
        <TextInput value={value} onChange={e => setValue(e.target.value)} placeholder='Enter link, etc.'/>
        <Media at='mobile'>
            <div className='media' style={{
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
            <div className='media' style={{
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
    </Stack>
}
