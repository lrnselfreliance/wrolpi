import React from "react";
import {Button, Header, Icon, IconButton, Modal} from "./ui";
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

/*
 * `asIcon` is for the navbar corner, where the trigger sits beside other bare glyphs and a
 * boxed button would not match; everywhere else it is a real button, matching its siblings.
 */
export const ShareButton = ({asIcon = false}) => {
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
        <Modal size='small' closeIcon
               open={open}
               onClose={handleClose}
        >
            <Modal.Header>Share this page</Modal.Header>
            <Modal.Content>
                <Header as='h4'>Another user can scan this QR code to view this page</Header>
                {/* `media`: filtered as a unit by night mode; see DonatePage. */}
                <div className='media'
                     style={{padding: '1em', backgroundColor: '#ffffff', display: "inline-block"}}>
                    <QRCode value={window.location.href}/>
                </div>
            </Modal.Content>
            <Modal.Actions>
                <ShareEveryoneButton url={window.location.href} onClick={handleClose}/>
                <Button role='cancel' onClick={handleClose}>Close</Button>
            </Modal.Actions>
        </Modal>
        {asIcon
            ? <a href='#' onClick={handleOpen}>
                <Icon name='share' size='large'/>
            </a>
            : <IconButton icon='share' label='Share' size='small' onClick={handleOpen}/>}
    </>
}
