import React from "react";
import {useDropzone} from "react-dropzone";
import {Box, Button, Group, Header, Icon, Modal, Panel, Progress, Stack} from "./ui";
import {DirectorySearch, mimetypeIconName, RequiredAsterisk, Toggle} from "./Common";
import {useMediaDirectory, useUploadFile} from "../hooks/customHooks";
import _ from "lodash";

/*
 * One upload form, two entry points.
 *
 * The dashboard asks the user where the files should go; the file browser already knows,
 * because the user selected the directory before pressing Upload.  That is the ONLY difference
 * between them, and it is `destination`:
 *
 *   undefined -- ask, with a DirectorySearch.  Until one is chosen there is nothing to drop
 *                files onto, so the target is replaced by the instruction to pick one.
 *   a string  -- fixed, and shown in the title.  '' is the media directory itself, which is a
 *                real destination; only `undefined` means "ask".
 *
 * Everything else -- the dropzone, the tag selector, the overwrite toggle, the per-file and
 * overall progress -- is the same work against the same `useUploadFile` state.
 */

export function UploadForm({
    askForDestination, destination, setDestination, disabled, inProgress, progresses, overallProgress,
    tagsSelector, overwrite, setOverwrite, getRootProps, getInputProps,
}) {
    let progressBars;
    if (!_.isEmpty(progresses)) {
        progressBars = Object.entries(progresses).map(([name, value]) => {
            const {percent, status, type} = value;
            let color = 'grey';
            let statusString;
            if (status === 'complete') {
                color = 'green';
                statusString = 'Complete:';
            } else if (status === 'pending') {
                statusString = 'Pending:';
            } else if (status === 'failed') {
                color = 'red';
                statusString = 'Failed:';
            } else if (status === 'conflicting') {
                color = 'orange';
                statusString = 'Already Exists:';
            }

            return <Group key={name} align='center' wrap='nowrap' gap='sm'>
                <Icon name={mimetypeIconName(type, name.toLowerCase())} size='large'/>
                <Box style={{flex: 1}}>
                    <Progress percent={percent} color={color} label={`${statusString} ${name}`}/>
                </Box>
            </Group>
        })
    }

    // A destination that was asked for and not yet given: there is nowhere to put a file.
    const canDrop = !askForDestination || !!destination;

    /*
     * A fragment, not a wrapper element.  The drop target below grows into whatever height the
     * dialog has left, which it can only do while its parent is the modal body's flex column --
     * a `<div>` or a `<form>` around all of this would absorb the growth and leave the target
     * its content height again.  The form is around the fields that have one.
     */
    return <>
        <form onSubmit={e => e.preventDefault()}>
        <Stack gap='sm'>
            {askForDestination && <div>
                <label style={{display: 'block', marginBottom: 4}}>
                    <b>Destination</b> <RequiredAsterisk/>
                </label>
                <DirectorySearch
                    onSelect={i => setDestination(i)}
                    disabled={disabled || inProgress}
                    style={{marginBottom: '0.5em'}}
                />
            </div>}
            {tagsSelector}

            <Toggle
                checked={overwrite}
                label='Overwrite existing files'
                onChange={() => setOverwrite(!overwrite)}
                disabled={disabled || inProgress}
            />
        </Stack>
        </form>

        {/* The target takes the room the dialog gives it rather than sitting as a strip at the
            top of it.  `min-height` as well as `flex`, so it stays a large target once the
            progress bars below it start claiming their own space. */}
        {canDrop ?
            <Panel style={{
                marginTop: '1em',
                padding: '1em',
                flex: '1 1 auto',
                display: 'flex',
                flexDirection: 'column',
            }}>
                <div {...getRootProps()}
                     style={{
                         cursor: 'pointer',
                         textAlign: 'center',
                         display: 'flex',
                         alignItems: 'center',
                         justifyContent: 'center',
                         flex: '1 1 auto',
                         minHeight: '30vh',
                     }}>
                    <input {...getInputProps()}/>
                    <Header as='h4' icon='file text'>Click here, or drop files here to upload</Header>
                </div>
            </Panel>
            // The instruction takes the same room the target would, so it sits where the user
            // is about to look rather than as a line above two thirds of an empty dialog.
            : <Header as='h4' style={{
                flex: '1 1 auto', display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
                You must search for a directory to place your files
            </Header>
        }

        {progresses && Object.keys(progresses).length > 1 &&
            <div style={{marginTop: '1em'}}>
                <Progress percent={overallProgress} color='blue' label='Overall Progress'/>
            </div>}

        <Stack gap={8} style={{marginTop: '1em'}}>
            {progressBars}
        </Stack>
    </>
}

/**
 * The upload dialog.  Pass a `destination` to upload into it, or leave it off to have the user
 * search for one.
 */
export function UploadModal({open, onClose, destination, onComplete, disabled}) {
    const mediaDirectory = useMediaDirectory();
    const asksForDestination = destination === undefined;

    const upload = useUploadFile();
    const {setFiles, setDestination, doClear, inProgress} = upload;

    const onDrop = React.useCallback(async (acceptedFiles) => {
        if (acceptedFiles && acceptedFiles.length > 0) {
            setFiles(acceptedFiles);
        }
    }, [setFiles]);

    const {getRootProps, getInputProps} = useDropzone({onDrop, disabled: inProgress});

    // A fixed destination is the caller's to declare; only the searching form sets its own.
    React.useEffect(() => {
        if (open && !asksForDestination) {
            setDestination(destination);
        }
    }, [open, destination, asksForDestination, setDestination]);

    // Destination was cleared, so the queued files have nowhere to go.
    React.useEffect(() => {
        if (!upload.destination && open) {
            doClear();
        }
    }, [upload.destination, open, doClear]);

    const handleClose = () => {
        if (inProgress) return;
        doClear();
        onClose();
        if (onComplete) onComplete();
    };

    const displayPath = asksForDestination ? null : `${mediaDirectory}/${destination}`;

    /*
     * Fullscreen, for the drop target.  At `large` the target was a strip about 90px tall in a
     * dialog covering a fifth of the screen -- a small thing to drag a file onto, and the page
     * behind it was the browser the file came from.  Given the room, the target takes it.
     */
    return <Modal open={open} onClose={handleClose} fullScreen>
        <Modal.Header>{displayPath ? `Upload to: ${displayPath}` : 'Upload from your device'}</Modal.Header>
        <Modal.Content>
            <UploadForm
                {...upload}
                askForDestination={asksForDestination}
                disabled={disabled}
                getRootProps={getRootProps}
                getInputProps={getInputProps}
            />
        </Modal.Content>
        <Modal.Actions>
            <Button role='cancel' onClick={handleClose} disabled={inProgress}>Close</Button>
        </Modal.Actions>
    </Modal>
}
