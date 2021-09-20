import React from "react";
import {Container, Form, Header} from "semantic-ui-react";
import {Route} from "react-router-dom";
import {APIForm} from "./Common";
import {postArchive} from "../api";

class ArchiveAddForm extends APIForm {
    constructor(props) {
        super(props);
        this.state = {
            ...this.state,
            inputs: {
                url: '',
            },
            errors: {},
        };
    }

    handleSubmit = async (e) => {
        e.preventDefault();
        await postArchive(this.state.inputs.url);
    }

    render() {
        return (
            <>
                <Header as='h2'>Archive</Header>
                <Form onSubmit={this.handleSubmit}>
                    <label htmlFor='url'>Archive URL</label>
                    <Form.Group>
                        <Form.Input
                            name='url'
                            placeholder='https://wrolpi.org'
                            onChange={this.handleInputChange}
                        />
                        <Form.Button primary>Archive</Form.Button>
                    </Form.Group>
                </Form>
            </>
        )
    }
}

class Archive extends React.Component {
    render() {
        return (
            <Container fluid style={{marginTop: '2em'}}>
                <ArchiveAddForm/>
            </Container>
        )
    }
}

export class ArchiveRoute extends React.Component {
    render() {
        return (
            <>
                <Container style={{marginTop: '2em', marginBottom: '2em'}}>
                    <Route path='/archive' exact component={Archive}/>
                </Container>
            </>
        )
    }
}
