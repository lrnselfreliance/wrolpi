import React from "react";
import {Button, Header, Icon, Modal, ModalActions, ModalContent, ModalHeader} from "./Theme";
import {IconGroup} from "semantic-ui-react";
import QRCode from "react-qr-code";
import {sendNotification} from "../api";

export const ShareEveryoneButton = ({url, size, onClick}) => {
    const handleShare = async () => {
        await sendNotification('A user shared this', url);
        if (onClick) {
            await onClick();
        }
    }

    return <Button
        color='violet'
        size={size}
        onClick={handleShare}
    >
        Share with everyone
    </Button>
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
            <ModalHeader>Share this page</ModalHeader>
            <ModalContent>
                <Header as='h4'>Another user can scan this QR code to view this page</Header>
                <div style={{padding: '1em', backgroundColor: '#ffffff', display: "inline-block"}}>
                    <QRCode value={window.location.href}/>
                </div>
            </ModalContent>
            <ModalActions>
                <ShareEveryoneButton url={window.location.href} onClick={handleClose}/>
                <Button onClick={handleClose}>Close</Button>
            </ModalActions>
        </Modal>
        <a href='#' onClick={handleOpen}>
            <IconGroup size='large'>
                <Icon name='share'/>
            </IconGroup>
        </a>
    </>
}