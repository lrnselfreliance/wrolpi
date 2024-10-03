import React from "react";
import {useDropzone} from "react-dropzone";
import {Form, Header, Icon, Progress, Segment} from "./Theme";
import {DirectorySearch, mimetypeIconName} from "./Common";
import {useUploadFile} from "../hooks/customHooks";
import _ from "lodash";
import {ThemeContext} from "../contexts/contexts";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {Form as SForm} from "semantic-ui-react";

export function Upload({disabled}) {
    const {t} = React.useContext(ThemeContext);

    const {setFiles, progresses, destination, setDestination, doClear, tagsSelector} = useUploadFile();

    const onDrop = React.useCallback(async (acceptedFiles) => {
        if (acceptedFiles && acceptedFiles.length > 0) {
            setFiles(acceptedFiles);
        }
    }, [destination]);

    const {getRootProps, getInputProps} = useDropzone({onDrop});

    React.useEffect(() => {
        if (!destination) {
            // Destination was cleared, clear progresses.
            doClear();
        }
    }, [destination]);

    const handleDestination = (value) => {
        setDestination(value);
    }

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
            // Only indicating when upload is pending.
            let indicating = status === 'pending';

            return <Grid.Row key={name}>
                <Grid.Column mobile={3} tablet={2} computer={1}>
                    <Icon name={mimetypeIconName(type, name.toLowerCase())} size='big'/>
                </Grid.Column>
                <Grid.Column mobile={13} tablet={14} computer={15}>
                    <Progress progress indicating={indicating} percent={percent} color={color}>
                        <p {...t}>{statusString} {name}</p>
                    </Progress>
                </Grid.Column>
            </Grid.Row>
        })
    }

    return <>
        <Form>
            <SForm.Field required>
                <label>Destination</label>
                <DirectorySearch
                    onSelect={handleDestination}
                    disabled={disabled}
                    style={{marginBottom: '0.5em'}}
                />
                {tagsSelector}
            </SForm.Field>
        </Form>

        {destination ?
            <Segment>
                <Grid columns={1}>
                    <Grid.Row>
                        <Grid.Column style={{padding: '1em'}}>
                            <Form onSubmit={() => {
                            }}>
                                <div {...getRootProps()}>
                                    <input {...getInputProps()}/>
                                    <Grid textAlign='center'>
                                        <Grid.Row>
                                            <Grid.Column>
                                                <Header icon>
                                                    <Icon name='file text'/>
                                                    Click here, or drop files here to upload
                                                </Header>
                                            </Grid.Column>
                                        </Grid.Row>
                                    </Grid>
                                </div>
                            </Form>
                        </Grid.Column>
                    </Grid.Row>
                </Grid>
            </Segment>
            : <Header as='h3'>You must search for a directory to place your files</Header>
        }

        <br/>

        <Grid columns={2}>
            {progressBars}
        </Grid>
    </>
}
