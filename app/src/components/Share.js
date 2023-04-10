import React from "react";
import {Icon} from "./Theme";
import {Button as SButton, Header, IconGroup, Modal} from "semantic-ui-react";
import QRCode from "react-qr-code";
import {sendNotification} from "../api";

export const ShareEveryoneButton = ({url, size, onClick}) => {
    const handleShare = async () => {
        await sendNotification('Look at this page', url);
        if (onClick) {
            await onClick();
        }
    }

    return <SButton
        color='violet'
        size={size}
        onClick={handleShare}
    >
        Share with everyone
    </SButton>
}

export const ShareButton = () => {
    const [open, setOpen] = React.useState(false);

    const handleOpen = (e) => {
        if (e) {
            e.preventDefault();
        }
        setOpen(true);
    }

    const handleClose = (e) => {
        if (e) {
            e.preventDefault();
        }
        setOpen(false);
    }

    return <>
        <Modal closeIcon
               open={open}
               onClose={handleClose}
        >
            <Modal.Header>Share this page</Modal.Header>
            <Modal.Content>
                <Header as='h4'>Another user can scan this QR code to view this page</Header>
                <QRCode value={window.location.href}/>
            </Modal.Content>
            <Modal.Actions>
                <ShareEveryoneButton url={window.location.href} onClick={handleClose}/>
                <SButton onClick={handleClose}>Close</SButton>
            </Modal.Actions>
        </Modal>
        <a href='#' onClick={handleOpen}>
            <IconGroup size='large'>
                <Icon name='share'/>
            </IconGroup>
        </a>
    </>
}