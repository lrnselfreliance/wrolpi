import Container from "semantic-ui-react/dist/commonjs/elements/Container";
import {Route} from "react-router-dom";
import React from 'react';
import "../static/wrolpi.css";
import {getInventory} from "../api";

class InventorySummary extends React.Component {

    async componentDidMount() {
        await this.getInventory();
    }

    getInventory = async () => {
        let response = await getInventory();
    }

    render() {
        return (
            <>Inventory</>
        )
    }
}

export class InventoryRoute extends React.Component {
    render() {
        return (
            <>
                <Container style={{marginTop: '2em', marginBottom: '2em'}}>
                    <Route path='/inventory' exact component={InventorySummary}/>
                </Container>
            </>
        )
    }
}