import React from "react";
import {useDropzone} from "react-dropzone";
import {Box, Button, Group, Header, Icon, Modal, Panel, Progress, Stack} from "./ui";
import {DirectorySearch, mimetypeIconName, RequiredAsterisk, Toggle} from "./Common";
import {useMediaDirectory, useUploadFile} from "../hooks/customHooks";
import _ from "lodash";

/*
 * `destination` says where the files go:
 *
 *   undefined -- ask, with a DirectorySearch.
 *   a string  -- upload there.  '' is the media directory, a real destination; a falsy check
 *                against it reads the media root as "nowhere".
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
     * A fragment, and the `<form>` around only the fields.  The drop target below grows into
     * the dialog's leftover height, which requires its parent to be the modal body's flex
     * column: any element wrapping all of this absorbs the growth instead.
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

        {/* The target grows into the dialog's leftover height.  `min-height` as well as
            `flex`, so it stays a large target once progress bars claim their own space. */}
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
            // The instruction takes the room the target would, rather than sitting as a line
            // above an empty dialog.
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

    /*
     * The user cleared their search, so the queued files have nowhere to go.
     *
     * Only while asking.  `''` is a fixed destination -- the media directory -- and clearing on
     * it fired this effect on every render, because `doClear` is a new function each time and
     * its own setState scheduled the next render.  React caps that at "Maximum update depth
     * exceeded"; the file browser reached it whenever Upload was pressed with nothing selected.
     */
    React.useEffect(() => {
        if (asksForDestination && !upload.destination && open) {
            doClear();
        }
    }, [asksForDestination, upload.destination, open, doClear]);

    const handleClose = () => {
        if (inProgress) return;
        doClear();
        onClose();
        if (onComplete) onComplete();
    };

    // No trailing slash for the media directory itself.
    const displayPath = asksForDestination ? null
        : (destination ? `${mediaDirectory}/${destination}` : mediaDirectory);

    // Fullscreen, so the drop target is something you can drag a file onto without aiming.
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
