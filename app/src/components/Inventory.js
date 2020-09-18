import React from 'react';
import "../static/wrolpi.css";
import {deleteItems, getInventory, getItems, saveItem} from "../api";
import {Button, Checkbox, Form, Grid, Tab, Table} from "semantic-ui-react";
import {Route} from "react-router-dom";
import Container from "semantic-ui-react/dist/commonjs/elements/Container";

class InventorySummary extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            by_category: null,
            by_name: null,
        }
    }

    async componentDidMount() {
        let inventory = await this.getInventory();
        this.setState(inventory);
    }

    getInventory = async () => {
        let response = await getInventory();
        return response;
    }

    render() {
        let byCategory = <></>;
        let byName = <></>;

        if (this.state.by_category === null || this.state.by_category.length === 0) {
            byCategory = <p>No items have been added to the inventory.</p>
        }

        if (this.state.by_name === null || this.state.by_name.length === 0) {
            byName = <p>No items have been added to the inventory.</p>
        }

        return (
            <>
                <h3>Categorized</h3>
                {byCategory}
                <h3>By Name</h3>
                {byName}
            </>
        )
    }
}

class InventoryList extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            checkboxes: [],
        }
    }

    handleCheckbox = (checkbox) => {
        // Add or remove a checkbox ID from the checkboxes array.
        let checkboxes = this.state.checkboxes.concat();
        let id = checkbox.current.props.id;
        if (!checkbox.current.state.checked) {
            checkboxes = checkboxes.concat([id]);
        } else {
            const index = checkboxes.indexOf(id);
            if (index > -1) {
                checkboxes.splice(index, 1);
            }
        }
        this.setState({checkboxes: checkboxes}, () => console.log(this.state.checkboxes));
    }

    handleRemove = async (e) => {
        e.preventDefault();
        await deleteItems(this.state.checkboxes);
        await this.props.fetchItems();
    }

    row = (item) => {
        let ref = React.createRef();
        return (
            <Table.Row key={item.id}>
                <Table.Cell>
                    <Checkbox
                        id={item.id}
                        ref={ref}
                        onClick={() => this.handleCheckbox(ref)}
                    />
                </Table.Cell>
                <Table.Cell>{item.brand}</Table.Cell>
                <Table.Cell>{item.name}</Table.Cell>
                <Table.Cell>{item.item_size}</Table.Cell>
                <Table.Cell>{item.unit}</Table.Cell>
                <Table.Cell>{item.count}</Table.Cell>
                <Table.Cell>{item.subcategory}</Table.Cell>
                <Table.Cell>{item.category}</Table.Cell>
                <Table.Cell>{item.expiration_date}</Table.Cell>
            </Table.Row>
        )
    }

    render() {
        if (this.props.items.length === 0) {
            return <p>Add some items in the form above!</p>
        }

        return (
            <>
                <Table celled>
                    <Table.Header>
                        <Table.Row>
                            <Table.HeaderCell/>
                            <Table.HeaderCell>Brand</Table.HeaderCell>
                            <Table.HeaderCell>Name</Table.HeaderCell>
                            <Table.HeaderCell>Size</Table.HeaderCell>
                            <Table.HeaderCell>Unit</Table.HeaderCell>
                            <Table.HeaderCell>Count</Table.HeaderCell>
                            <Table.HeaderCell>Subcategory</Table.HeaderCell>
                            <Table.HeaderCell>Category</Table.HeaderCell>
                            <Table.HeaderCell>Expiration Date</Table.HeaderCell>
                        </Table.Row>
                    </Table.Header>
                    <Table.Body>
                        {this.props.items.map((i) => this.row(i))}
                    </Table.Body>
                </Table>
                <Button
                    color='red'
                    onClick={this.handleRemove}
                    disabled={this.state.checkboxes.length === 0}
                >
                    Remove
                </Button>
            </>
        )
    }
}

class InventoryAddList extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            items: [],
            brand: '',
            name: '',
            item_size: '',
            unit: '',
            count: '',
            category: '',
            subcategory: '',
            expiration_date: '',
        }
    }

    componentDidMount = async () => {
        this.clearValues();
        await this.fetchItems();
    }

    fetchItems = async () => {
        let response = await getItems();
        this.setState({items: response.items});
    }

    handleInputChange = (e, {name, value}) => {
        this.setState({[name]: value});
    }

    clearValues = () => {
        this.setState({
            brand: '',
            name: '',
            item_size: '',
            unit: '',
            count: '',
            category: '',
            subcategory: '',
            expiration_date: '',
        });
    }

    handleSubmit = async (e) => {
        e.preventDefault();
        let item = {
            brand: this.state.brand,
            name: this.state.name,
            item_size: this.state.item_size,
            unit: this.state.unit,
            count: this.state.count,
            category: this.state.category,
            subcategory: this.state.subcategory,
            expiration_date: this.state.expiration_date,
        };
        await saveItem(item);
        await this.clearValues();
        await this.fetchItems();
    }

    render() {
        return (
            <>
                <Form onSubmit={this.handleSubmit}>
                    <Form.Group widths='equal'>
                        <Grid>
                            <Grid.Column computer={2} mobile={16}>
                                <label>Brand</label>
                                <Form.Input
                                    name="brand"
                                    placeholder="Brand"
                                    onChange={this.handleInputChange}
                                    value={this.state.brand}
                                />
                            </Grid.Column>
                            <Grid.Column computer={3} mobile={16}>
                                <label>Product Name</label>
                                <Form.Input
                                    required
                                    name="name"
                                    placeholder="Product Name"
                                    onChange={this.handleInputChange}
                                    value={this.state.name}
                                />
                            </Grid.Column>
                            <Grid.Column computer={1} mobile={4}>
                                <label>Size</label>
                                <Form.Input
                                    required
                                    name="item_size"
                                    placeholder="Size"
                                    onChange={this.handleInputChange}
                                    value={this.state.item_size}
                                />
                            </Grid.Column>
                            <Grid.Column computer={1} mobile={4}>
                                <label>Unit</label>
                                <Form.Input
                                    required
                                    name="unit"
                                    placeholder="Unit"
                                    onChange={this.handleInputChange}
                                    value={this.state.unit}
                                />
                            </Grid.Column>
                            <Grid.Column computer={1} mobile={4}>
                                <label>Count</label>
                                <Form.Input
                                    required
                                    name="count"
                                    placeholder="Count"
                                    onChange={this.handleInputChange}
                                    value={this.state.count}
                                />
                            </Grid.Column>
                            <Grid.Column computer={2} mobile={16}>
                                <label>Subcategory</label>
                                <Form.Input
                                    name="subcategory"
                                    placeholder="Subcategory"
                                    onChange={this.handleInputChange}
                                    value={this.state.subcategory}
                                />
                            </Grid.Column>
                            <Grid.Column computer={2} mobile={16}>
                                <label>Category</label>
                                <Form.Input
                                    name="category"
                                    placeholder="Category"
                                    onChange={this.handleInputChange}
                                    value={this.state.category}
                                />
                            </Grid.Column>
                            <Grid.Column computer={2} mobile={16}>
                                <label>Expiration Date</label>
                                <Form.Input
                                    name="expiration_date"
                                    placeholder="Expiration Date"
                                    onChange={this.handleInputChange}
                                    value={this.state.expiration_date}
                                />
                            </Grid.Column>
                            <Grid.Column computer={1} mobile={16}>
                                <Button icon='plus' type='submit' style={{marginTop: '1.4em'}}/>
                            </Grid.Column>
                        </Grid>
                    </Form.Group>
                </Form>
                <h4>Items in Inventory</h4>
                <InventoryList items={this.state.items} fetchItems={this.fetchItems}/>
            </>
        )
    }
}

class InventoryTab extends React.Component {

    render() {
        let panes = [
            {menuItem: 'List', render: () => <Tab.Pane><InventoryAddList/></Tab.Pane>},
            {menuItem: 'Summary', render: () => <Tab.Pane><InventorySummary/></Tab.Pane>},
        ];
        return (
            <Tab panes={panes}/>
        )
    }
}

export class InventoryRoute extends React.Component {
    render() {
        return (
            <>
                <Container fluid style={{marginTop: '2em', marginBottom: '2em'}}>
                    <Route path='/inventory' exact component={InventoryTab}/>
                </Container>
            </>
        )
    }
}