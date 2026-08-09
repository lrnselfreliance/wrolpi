import React from "react";
import {useDropzone} from "react-dropzone";
import {Box, Group, Header, Icon, Panel, Progress, Stack} from "./ui";
import {DirectorySearch, mimetypeIconName, RequiredAsterisk, Toggle} from "./Common";
import {useUploadFile} from "../hooks/customHooks";
import _ from "lodash";

export function Upload({disabled}) {
    const {
        setFiles,
        progresses,
        destination,
        setDestination,
        doClear,
        tagsSelector,
        overwrite,
        setOverwrite,
        overallProgress,
        inProgress,
    } = useUploadFile();

    const onDrop = React.useCallback(async (acceptedFiles) => {
        if (acceptedFiles && acceptedFiles.length > 0) {
            setFiles(acceptedFiles);
        }
    }, [destination]);

    const {getRootProps, getInputProps} = useDropzone({onDrop, disabled: inProgress});

    React.useEffect(() => {
        if (!destination) {
            // Destination was cleared, clear progresses.
            doClear();
        }
    }, [destination]);

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

    return <>
        <Stack gap='sm'>
            <div>
                <label style={{display: 'block', marginBottom: 4}}>
                    <b>Destination</b> <RequiredAsterisk/>
                </label>
                <DirectorySearch
                    onSelect={i => setDestination(i)}
                    disabled={disabled || inProgress}
                    style={{marginBottom: '0.5em'}}
                />
                {tagsSelector}
            </div>

            <Toggle
                checked={overwrite}
                label='Overwrite'
                onChange={() => setOverwrite(!overwrite)}
                disabled={disabled || inProgress}
            />
        </Stack>

        {destination ?
            <Panel style={{marginTop: '1em'}}>
                <div {...getRootProps()} style={{padding: '1em', textAlign: 'center', cursor: 'pointer'}}>
                    <input {...getInputProps()}/>
                    <Header as='h3' icon='file text'>
                        Click here, or drop files here to upload
                    </Header>
                </div>
            </Panel>
            : <Header as='h3'>You must search for a directory to place your files</Header>
        }

        <br/>

        {progresses && Object.keys(progresses).length > 1 && <Progress
            percent={overallProgress}
            color='blue'
            label='Overall Progress'
        />}

        <Stack gap='sm' mt='sm'>
            {progressBars}
        </Stack>
    </>
}
