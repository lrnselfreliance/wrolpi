import React, {useState} from "react";
import {PageContainer, useTitle} from "./Common";
import {Button, Header, Segment, Table} from "./Theme";
import {Icon, Modal, TableBody, TableCell, TableRow} from "semantic-ui-react";
import QRCode from "react-qr-code";

const bitcoinAddress = '1mi1ddLSd6LmkuwJd1ttZsKuED724vYjS';
const bitcoinContent = `bitcoin:${bitcoinAddress}`;
const ethereumAddress = '0xC27C39b31A3a9D12C345A58aFe8a42a2e1eb0448';
const ethereumContent = `ethereum:${ethereumAddress}`;
const litecoinAddress = `LKngzDZUZcggxk2fTAZYmBcksLBMrnhioA`;
const litecoinContent = `litecoin:${litecoinAddress}`;
const moneroAddress = '87jv2NpGb5sbUwk7zYYwEY5RAoh1jRfTo4d1BAewVdJJFKg2bDF2UXtLfTc8LZkkSagDsnJyevLpZaZ846QHcLDjUenBrcY';
const moneroContent = `monero:${moneroAddress};`

function CoinQRButton({qrCodeValue, header, buttonColor}) {
    const [open, setOpen] = useState(false);

    return <>
        <Button icon color={buttonColor}
                onClick={() => setOpen(true)}>
            <Icon name='qrcode' size='big'/>
        </Button>
        <Modal closeIcon
               open={open}
               onClose={() => setOpen(false)}
               onOpen={() => setOpen(true)}
        >
            <Modal.Header>{header}</Modal.Header>
            <Modal.Content>
                <QRCode value={qrCodeValue} size={300}/>
            </Modal.Content>
        </Modal>
    </>
}

function CoinRow({header, qrCodeValue, address, buttonColor}) {
    return <>
        <Header as='h3'>{header}</Header>
        <Table stackable>
            <TableBody>
                <TableRow>
                    <TableCell width={1}>
                        <CoinQRButton qrCodeValue={qrCodeValue} header={header} buttonColor={buttonColor}/>
                    </TableCell>
                    <TableCell width={15} textAlign='left'>
                        <pre>{address}</pre>
                    </TableCell>
                </TableRow>
            </TableBody>
        </Table>
    </>
}

export function Donate() {
    useTitle('Donate');

    return <PageContainer>
        <Segment>
            <Header as='h1'>Donate</Header>
            <Header as='h3'>We appreciate any support you can provide to WROLPi!</Header>
            <CoinRow header='Monero' qrCodeValue={moneroContent} address={moneroAddress} buttonColor='orange'/>
            <CoinRow header='Litecoin' qrCodeValue={litecoinContent} address={litecoinAddress} buttonColor='grey'/>
            <CoinRow header='Ethereum' qrCodeValue={ethereumContent} address={ethereumAddress} buttonColor='blue'/>
            <CoinRow header='Bitcoin' qrCodeValue={bitcoinContent} address={bitcoinAddress} buttonColor='yellow'/>
        </Segment>
    </PageContainer>;
}