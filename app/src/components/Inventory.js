import React from 'react';
import "../static/wrolpi.css";
import {
    deleteInventory,
    deleteItems,
    getInventories,
    getInventory,
    getItems,
    saveInventory,
    saveItem,
    updateInventory
} from "../api";
import {Button, Checkbox, Dropdown, Form, Grid, Header, Portal, Segment, Tab, Table} from "semantic-ui-react";
import {Route} from "react-router-dom";
import Container from "semantic-ui-react/dist/commonjs/elements/Container";
import {toast} from 'react-semantic-toasts';

class InventorySummary extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            by_category: null,
            by_name: null,
            inventory: null,
        }
    }

    async componentDidMount() {
        await this.fetchInventory();
    }

    fetchInventory = async () => {
        let inventorySummary = await getInventory(this.state.inventory.id);
        this.setState(inventorySummary);
    }

    setInventory = async (inventory) => {
        this.setState({inventory}, this.fetchInventory);
    }

    categoryTable = () => {
        if (this.state.by_category === null || this.state.by_category.length === 0) {
            return <p>No items have been added to this inventory.</p>;
        }

        function row(i) {
            return <Table.Row>
                <Table.Cell>{i.category}</Table.Cell>
                <Table.Cell>{i.subcategory}</Table.Cell>
                <Table.Cell>{i.total_size}</Table.Cell>
                <Table.Cell>{i.unit}</Table.Cell>
            </Table.Row>
        }

        return <Table>
            <Table.Header>
                <Table.Row>
                    <Table.Cell>Category</Table.Cell>
                    <Table.Cell>Subcategory</Table.Cell>
                    <Table.Cell>Total Size</Table.Cell>
                    <Table.Cell>Unit</Table.Cell>
                </Table.Row>
            </Table.Header>
            <Table.Body>
                {this.state.by_category.map((i) => row(i))}
            </Table.Body>
        </Table>;
    }

    nameTable = () => {
        if (this.state.by_name === null || this.state.by_name.length === 0) {
            return <p>No items have been added to this inventory.</p>;
        }

        function row(i) {
            return <Table.Row>
                <Table.Cell>{i.brand}</Table.Cell>
                <Table.Cell>{i.name}</Table.Cell>
                <Table.Cell>{i.total_size}</Table.Cell>
                <Table.Cell>{i.unit}</Table.Cell>
            </Table.Row>
        }

        return <Table>
            <Table.Header>
                <Table.Row>
                    <Table.Cell>Brand</Table.Cell>
                    <Table.Cell>Product Name</Table.Cell>
                    <Table.Cell>Total Size</Table.Cell>
                    <Table.Cell>Unit</Table.Cell>
                </Table.Row>
            </Table.Header>
            <Table.Body>
                {this.state.by_name.map((i) => row(i))}
            </Table.Body>
        </Table>;
    }

    render() {
        return (
            <>
                <InventorySelector setInventory={this.setInventory}/>
                <h3>Categorized</h3>
                {this.categoryTable()}
                <h3>By Name</h3>
                {this.nameTable()}
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
        this.setState({checkboxes: checkboxes});
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
            return <p>Add some items using the form above!</p>
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

class InventoryPortal extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            open: false,
            inventory: null,
            name: '',
        };
    }

    componentDidUpdate(prevProps, prevState, snapshot) {
        if (this.props !== prevProps) {
            this.setState({
                inventory: this.props.inventory,
                name: this.props.inventory ? this.props.inventory.name : '',
            });
        }
    }

    handleClose = () => this.setState({open: false});
    handleOpen = () => this.setState({open: true});

    handleInputChange = (e, {name, value}) => {
        this.setState({[name]: value});
    }

    handleSubmit = async (e) => {
        e.preventDefault();
        let inventory = {
            id: this.state.inventory ? this.state.inventory.id : null,
            name: this.state.name || (this.state.inventory ? this.state.inventory.name : ''),
        };
        await this.props.handleSubmit(inventory, this.handleClose);
    }

    handleDelete = async (e) => {
        e.preventDefault();
        this.props.handleDelete(this.state.inventory, this.handleClose);
    }

    render() {
        return (
            <>
                <Button
                    disabled={this.props.open}
                    onClick={this.handleOpen}
                    {...this.props.buttonProps}
                />
                <Portal onClose={this.handleClose} open={this.state.open}>
                    <Segment
                        style={{
                            left: '40%',
                            position: 'fixed',
                            top: '50%',
                            zIndex: 1000,
                        }}
                    >
                        <Header>{this.props.header}</Header>
                        <Form onSubmit={this.handleSubmit}>
                            <label>Name</label>
                            <Form.Input
                                name='name'
                                value={this.state.name}
                                onChange={this.handleInputChange}
                            />
                            <Button primary type='submit'>Save</Button>
                            {
                                this.props.deleteButton &&
                                <Button color='red'
                                        onClick={this.handleDelete}
                                >
                                    Delete
                                </Button>
                            }
                            <Button secondary floated='right' onClick={this.handleClose}>Cancel</Button>
                        </Form>
                    </Segment>
                </Portal>
            </>
        )
    }
}

class EditInventory extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            open: false,
            inventory: props.inventory,
        }
    }

    componentDidUpdate(prevProps, prevState, snapshot) {
        if (prevProps !== this.props) {
            this.setState({inventory: this.props.inventory});
        }
    }

    handleSubmit = async (inventory, closeCallback) => {
        let inventoryId = inventory.id;
        delete inventory['id'];
        let response = await updateInventory(inventoryId, inventory);

        if (response.status === 204) {
            await this.props.success();
            closeCallback();
        } else {
            toast({
                type: 'error',
                title: 'Failed to save inventory!',
                description: 'Server responded with an error.',
                time: 5000,
            })
        }
    }

    handleDelete = async (inventory, closeCallback) => {
        let response = await deleteInventory(inventory.id);

        if (response.status === 204) {
            await this.props.success();
            closeCallback();
        } else {
            toast({
                type: 'error',
                title: 'Failed to delete inventory!',
                description: 'Server responded with an error.',
                time: 5000,
            })
        }
    }

    render() {
        return (
            <InventoryPortal
                inventory={this.props.inventory}
                header='Edit Inventory'
                handleSubmit={this.handleSubmit}
                handleDelete={this.handleDelete}
                buttonProps={{icon: 'edit', color: 'red'}}
                deleteButton={true}
            />
        )
    }
}

class NewInventory extends React.Component {

    handleSubmit = async (inventory, closeCallback) => {
        let response = await saveInventory(inventory);

        if (response.status === 201) {
            await this.props.success();
            closeCallback();
        } else {
            toast({
                type: 'error',
                title: 'Failed to save inventory!',
                description: 'Server responded with an error.',
                time: 5000,
            })
        }
    }

    render() {
        return (
            <InventoryPortal
                header='Create a new Inventory list'
                handleSubmit={this.handleSubmit}
                buttonProps={{icon: 'plus'}}
            />
        )
    }

}

class InventorySelector extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            options: [],
            inventories: [],
            selected: null,
            newInventoryPortal: false,
            editInventoryPortal: false,
            name: '',
        }
    }

    async componentDidMount() {
        await this.fetchInventories();
    }

    async fetchInventories() {
        let inventories = await getInventories();
        let options = [];
        for (let i = 0; i < inventories.length; i++) {
            let inventory = inventories[i];
            options = options.concat([{
                key: inventory.id,
                text: inventory.name,
                value: inventory.id,
                id: inventory.id,
            }])
        }
        let selected = this.state.selected || inventories[0];
        this.setState({inventories, options, selected},
            () => this.props.setInventory(selected));
    }

    setInventory = (e, {value}) => {
        let selected = null;
        for (let i = 0; i < this.state.inventories.length; i++) {
            if (value === this.state.inventories[i].id) {
                selected = this.state.inventories[i];
            }
        }
        this.setState({selected: selected},
            () => this.props.setInventory(this.state.selected));
    }

    render() {
        return (
            <>
                <h3>Inventory</h3>
                <Grid>
                    <Grid.Column width={14}>
                        <Dropdown
                            placeholder='Select an Inventory'
                            fluid
                            selection
                            value={this.state.selected ? this.state.selected.id : null}
                            options={this.state.options}
                            onChange={this.setInventory}
                        />
                    </Grid.Column>
                    <Grid.Column width={2}>
                        <NewInventory success={() => this.fetchInventories}/>
                        <EditInventory
                            inventory={this.state.selected}
                            success={() => this.fetchInventories()}
                        />
                    </Grid.Column>
                </Grid>
            </>
        )
    }
}

class InventoryAddList extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            inventory: null,
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
        if (this.state.inventory) {
            let response = await getItems(this.state.inventory.id);
            let items = response.items;

            this.setState({items: items});
        }
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
        let response = await saveItem(this.state.inventory.id, item);
        if (response.status === 204) {
            await this.clearValues();
            await this.fetchItems();
        } else {
            toast({
                type: 'error',
                title: 'Failed to save item!',
                description: 'Server responded with an error.',
                time: 5000,
            })
        }
    }

    setInventory = async (inventory) => {
        this.setState({inventory}, this.fetchItems);
    }

    render() {
        return (
            <>
                <InventorySelector setInventory={this.setInventory}/>
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
                <h4>Items in: {this.state.inventory ? this.state.inventory.name : ''}</h4>
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