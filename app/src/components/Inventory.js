import React from 'react';
import "../static/wrolpi.css";
import {
    deleteInventory,
    deleteItems,
    getBrands,
    getCategories,
    getInventories,
    getInventory,
    getItems,
    saveInventory,
    saveItem,
    updateInventory,
    updateItem
} from "../api";
import {Button, Checkbox, Dropdown, Form, Grid, Header, Portal, Segment, Table} from "semantic-ui-react";
import {Route} from "react-router-dom";
import {toast} from 'react-semantic-toasts';
import {arraysEqual, enumerate, PageContainer, replaceNullValues, TabLinks} from './Common';
import _ from 'lodash';

class InventorySummary extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            by_category: null,
            by_subcategory: null,
            by_name: null,
            inventory: null,
        }
    }

    async componentDidMount() {
        await this.fetchInventory();
    }

    fetchInventory = async () => {
        if (this.state.inventory) {
            let {by_category, by_subcategory, by_name} = await getInventory(this.state.inventory.id);
            by_category = enumerate(by_category);
            by_subcategory = enumerate(by_subcategory);
            by_name = enumerate(by_name);
            this.setState({by_category, by_subcategory, by_name});
        }
    }

    setInventory = async (inventory) => {
        this.setState({inventory}, this.fetchInventory);
    }

    categoryTable = () => {
        if (this.state.by_category === null || this.state.by_category.length === 0) {
            return <p>No items have been added to this inventory.</p>;
        }

        function row([key, i]) {
            return <Table.Row key={key}>
                <Table.Cell>{i.category}</Table.Cell>
                <Table.Cell>{i.total_size}</Table.Cell>
                <Table.Cell>{i.unit}</Table.Cell>
            </Table.Row>
        }

        return <Table>
            <Table.Header>
                <Table.Row>
                    <Table.HeaderCell>Category</Table.HeaderCell>
                    <Table.HeaderCell>Total Size</Table.HeaderCell>
                    <Table.HeaderCell>Unit</Table.HeaderCell>
                </Table.Row>
            </Table.Header>
            <Table.Body>
                {this.state.by_category.map(row)}
            </Table.Body>
        </Table>;
    }

    subcategoryTable = () => {
        if (this.state.by_subcategory === null || this.state.by_subcategory.length === 0) {
            return <p>No items have been added to this inventory.</p>;
        }

        function row([key, i]) {
            return <Table.Row key={key}>
                <Table.Cell>{i.category}</Table.Cell>
                <Table.Cell>{i.subcategory}</Table.Cell>
                <Table.Cell>{i.total_size}</Table.Cell>
                <Table.Cell>{i.unit}</Table.Cell>
            </Table.Row>
        }

        return <Table>
            <Table.Header>
                <Table.Row>
                    <Table.HeaderCell>Category</Table.HeaderCell>
                    <Table.HeaderCell>Subcategory</Table.HeaderCell>
                    <Table.HeaderCell>Total Size</Table.HeaderCell>
                    <Table.HeaderCell>Unit</Table.HeaderCell>
                </Table.Row>
            </Table.Header>
            <Table.Body>
                {this.state.by_subcategory.map(row)}
            </Table.Body>
        </Table>;
    }

    nameTable = () => {
        if (this.state.by_name === null || this.state.by_name.length === 0) {
            return <p>No items have been added to this inventory.</p>;
        }

        function row([key, i]) {
            return <Table.Row key={key}>
                <Table.Cell>{i.brand}</Table.Cell>
                <Table.Cell>{i.name}</Table.Cell>
                <Table.Cell>{i.total_size}</Table.Cell>
                <Table.Cell>{i.unit}</Table.Cell>
            </Table.Row>
        }

        return <Table>
            <Table.Header>
                <Table.Row>
                    <Table.HeaderCell>Brand</Table.HeaderCell>
                    <Table.HeaderCell>Product Name</Table.HeaderCell>
                    <Table.HeaderCell>Total Size</Table.HeaderCell>
                    <Table.HeaderCell>Unit</Table.HeaderCell>
                </Table.Row>
            </Table.Header>
            <Table.Body>
                {this.state.by_name.map(row)}
            </Table.Body>
        </Table>;
    }

    render() {
        return (
            <>
                <InventorySelector setInventory={this.setInventory}/>
                <h3>Categorized</h3>
                {this.categoryTable()}

                <h3>Categorized by Subcategory</h3>
                {this.subcategoryTable()}

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
            editItems: {},
        }
    }

    handleCheckbox = (checkbox, item) => {
        // Add or remove a checkbox ID from the checkboxes array.
        let checkboxes = this.state.checkboxes;
        let checked = checkbox.current.state.checked;

        // Add the item id to the list of checked checkboxes.
        let value = checkbox.current.props.value;
        if (!checked) {
            checkboxes = checkboxes.concat([value]);
        } else {
            const index = checkboxes.indexOf(value);
            if (index > -1) {
                checkboxes.splice(index, 1);
            }
        }

        // Create or remove the editItem.  This is a copy of the item which can then be modified and saved.
        let editItems = this.state.editItems;
        if (!checked) {
            let editItem = {}
            Object.assign(editItem, item);
            replaceNullValues(editItem);
            editItems[item.id] = editItem;
        } else {
            delete editItems[item.id];
        }

        this.setState({checkboxes: checkboxes, editItems: editItems});
    }

    handleRemove = async (e) => {
        e.preventDefault();
        await deleteItems(this.state.checkboxes);
        await this.props.fetchItems();
    }

    handleInputChange = (e, {name, value}, itemId) => {
        let editItems = this.state.editItems;
        editItems[itemId][name] = value;
        this.setState({editItems});
    }

    handleSave = async (e) => {
        e.preventDefault();
        let keys = Object.keys(this.state.editItems);
        for (let i = 0; i < keys.length; i++) {
            let itemId = keys[i];
            let item = this.state.editItems[itemId];
            await updateItem(itemId, item);
        }
        this.setState({editItems: {}, checkboxes: []}, this.props.fetchItems);
    }

    row = (item) => {
        let ref = React.createRef();
        let editable = this.state.checkboxes.indexOf(item.id) >= 0;

        let checkboxCell = <Table.Cell>
            <Checkbox
                value={item.id}
                ref={ref}
                onClick={() => this.handleCheckbox(ref, item)}
            />
        </Table.Cell>;

        if (!editable) {
            // Show the user the non-editable version, until they check the checkbox.
            return (
                <Table.Row key={item.id}>
                    {checkboxCell}
                    <Table.Cell style={{paddingTop: '1.5em', paddingBottom: '1.5em'}}>
                        {item.brand}
                    </Table.Cell>
                    <Table.Cell style={{paddingTop: '1.5em', paddingBottom: '1.5em'}}>
                        {item.name}
                    </Table.Cell>
                    <Table.Cell style={{paddingTop: '1.5em', paddingBottom: '1.5em'}}>
                        {item.item_size}
                    </Table.Cell>
                    <Table.Cell style={{paddingTop: '1.5em', paddingBottom: '1.5em'}}>
                        {item.unit}
                    </Table.Cell>
                    <Table.Cell style={{paddingTop: '1.5em', paddingBottom: '1.5em'}}>
                        {item.count}
                    </Table.Cell>
                    <Table.Cell style={{paddingTop: '1.5em', paddingBottom: '1.5em'}}>{
                        item.subcategory}
                    </Table.Cell>
                    <Table.Cell style={{paddingTop: '1.5em', paddingBottom: '1.5em'}}>
                        {item.category}
                    </Table.Cell>
                    <Table.Cell style={{paddingTop: '1.5em', paddingBottom: '1.5em'}}>
                        {item.expiration_date}
                    </Table.Cell>
                </Table.Row>
            )
        } else {
            // Insert the modified table row so the user can edit this item.
            let editItem = this.state.editItems[item.id];
            return <Table.Row key={item.id}>
                {checkboxCell}
                <Table.Cell>
                    <BrandInput
                        value={editItem.brand}
                        handleInputChange={(i, j) => this.handleInputChange(i, j, item.id)}
                    />
                </Table.Cell>
                <Table.Cell>
                    <Form.Input
                        fluid
                        name="name"
                        value={editItem.name}
                        onChange={(i, j) => this.handleInputChange(i, j, item.id)}
                    />
                </Table.Cell>
                <Table.Cell>
                    <Form.Input
                        fluid
                        name="item_size"
                        value={editItem.item_size}
                        onChange={(i, j) => this.handleInputChange(i, j, item.id)}
                    />
                </Table.Cell>
                <Table.Cell>
                    <Form.Input
                        fluid
                        name="unit"
                        value={editItem.unit}
                        onChange={(i, j) => this.handleInputChange(i, j, item.id)}
                    />
                </Table.Cell>
                <Table.Cell>
                    <Form.Input
                        fluid
                        name="count"
                        value={editItem.count}
                        onChange={(i, j) => this.handleInputChange(i, j, item.id)}
                    />
                </Table.Cell>
                <TableCategoryInputs
                    handleInputChange={(i, j) => this.handleInputChange(i, j, item.id)}
                    subcategory={editItem.subcategory}
                    category={editItem.category}
                />
                <Table.Cell>
                    <Form.Input
                        fluid
                        name="expiration_date"
                        value={editItem.expiration_date}
                        onChange={(i, j) => this.handleInputChange(i, j, item.id)}
                    />
                </Table.Cell>
            </Table.Row>
        }
    }

    handleSort = (columns) => {
        this.props.handleSort(columns);
    }

    render() {
        if (this.props.items.length === 0) {
            return <p>Add some items using the form above!</p>
        }

        const {sortColumns, sortDirection} = this.props;

        return (
            <>
                <Table celled sortable>
                    <Table.Header>
                        <Table.Row>
                            <Table.HeaderCell
                                sorted={arraysEqual(sortColumns, ['id']) ? sortDirection : null}
                                onClick={() => this.handleSort(['id'])}
                            >
                                Edit
                            </Table.HeaderCell>
                            <Table.HeaderCell
                                sorted={arraysEqual(sortColumns, ['brand', 'name']) ? sortDirection : null}
                                onClick={() => this.handleSort(['brand', 'name'])}
                            >
                                Brand
                            </Table.HeaderCell>
                            <Table.HeaderCell
                                sorted={arraysEqual(sortColumns, ['name', 'brand']) ? sortDirection : null}
                                onClick={() => this.handleSort(['name', 'brand'])}
                            >
                                Name
                            </Table.HeaderCell>
                            <Table.HeaderCell
                                sorted={arraysEqual(sortColumns, ['size']) ? sortDirection : null}
                                onClick={() => this.handleSort(['size'])}
                            >
                                Size
                            </Table.HeaderCell>
                            <Table.HeaderCell
                                sorted={arraysEqual(sortColumns, ['unit']) ? sortDirection : null}
                                onClick={() => this.handleSort(['unit'])}
                            >
                                Unit
                            </Table.HeaderCell>
                            <Table.HeaderCell
                                sorted={arraysEqual(sortColumns, ['count']) ? sortDirection : null}
                                onClick={() => this.handleSort(['count'])}
                            >
                                Count
                            </Table.HeaderCell>
                            <Table.HeaderCell
                                sorted={arraysEqual(sortColumns, ['subcategory', 'category']) ? sortDirection : null}
                                onClick={() => this.handleSort(['subcategory', 'category'])}
                            >
                                Subcategory
                            </Table.HeaderCell>
                            <Table.HeaderCell
                                sorted={arraysEqual(sortColumns, ['category', 'subcategory']) ? sortDirection : null}
                                onClick={() => this.handleSort(['category', 'subcategory'])}
                            >
                                Category
                            </Table.HeaderCell>
                            <Table.HeaderCell
                                sorted={arraysEqual(sortColumns, ['expiration_date']) ? sortDirection : null}
                                onClick={() => this.handleSort(['expiration_date'])}
                            >
                                Expiration Date
                            </Table.HeaderCell>
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
                    floated='right'
                >
                    Remove
                </Button>
                <Button
                    secondary
                    onClick={this.handleSave}
                    disabled={this.state.checkboxes.length === 0}
                >
                    Save
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
                header: 'Failed to save inventory!',
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
                header: 'Failed to delete inventory!',
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
                buttonProps={{icon: 'edit', color: 'yellow'}}
                deleteButton={true}
            />
        )
    }
}

class NewInventory extends React.Component {

    handleSubmit = async (inventory, closeCallback) => {
        delete inventory.id;
        let response = await saveInventory(inventory);

        if (response.status === 201) {
            await this.props.success();
            closeCallback();
        } else {
            toast({
                type: 'error',
                header: 'Failed to save inventory!',
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
                        <NewInventory success={() => this.fetchInventories()}/>
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

class SuggestionInput extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            value: '',
        }
    }

    componentDidMount() {
        this.setState({value: this.props.value !== undefined ? this.props.value : ''})
    }

    componentDidUpdate(prevProps, prevState, snapshot) {
        if (prevProps !== this.props && this.props.value !== undefined) {
            this.setState({value: this.props.value});
        }
    }

    buildOptions() {
        return this.props.options.map((i) => <option key={i[0]} value={i}>{i[2]}</option>)
    }

    handleInputChange = (e, option) => {
        e.preventDefault();
        let [key, value,] = option.value.split(',');
        if (!isNaN(key)) {
            // User chose from the suggestions.
            this.setState({value: value});
            this.props.handleInputChange(e, {name: option.name, key: key, value: value})
        } else {
            // User typed in something new.
            value = key === undefined ? '' : key;
            this.setState({value: value});
            this.props.handleInputChange(e, {name: option.name, value: value});
        }
    }

    clearInput() {
        this.setState({value: ''});
    }

    render() {
        return (
            <>
                <label>{this.props.label}</label>
                <Form.Input
                    fluid={this.props.fluid !== undefined ? this.props.fluid : false}
                    list={this.props.list}
                    name={this.props.name}
                    placeholder={this.props.placeholder}
                    onChange={this.handleInputChange}
                    value={this.state.value}
                />
                <datalist id={this.props.list}>
                    {this.buildOptions()}
                </datalist>
            </>
        )
    }
}

class CategoryInputs extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            categories: [],
            subcategory: '',
            category: '',
        }
    }

    componentDidMount = async () => {
        await this.fetchCategories();
        this.setState({
            subcategory: this.props.subcategory !== undefined ? this.props.subcategory : '',
            category: this.props.category !== undefined ? this.props.category : '',
        });
    }

    fetchCategories = async () => {
        let categories = await getCategories();
        categories = enumerate(categories);
        let newCategories = [];
        for (let i = 0; i < categories.length; i++) {
            let [key, sc] = categories[i];
            let [subcategory, category] = sc;
            newCategories = newCategories.concat([[key, subcategory, `${subcategory}/${category}`]]);
        }
        this.setState({categories: newCategories});
    }

    clearInputs = () => {
        this.subcategoryRef.current.clearInput();

        this.setState({
            subcategory: '',
            category: '',
        });
    }

    handleInputChange = (e, {name, value, key}) => {
        this.setState({[name]: value});
        if (key) {
            // User chose from suggestions.  Set the associated category.
            let [subcategory, category] = this.state.categories[key][2].split('/');
            this.setState({subcategory: subcategory, category: category});
            this.props.handleInputChange(e, {'name': 'subcategory', 'value': subcategory});
            this.props.handleInputChange(e, {'name': 'category', 'value': category});
        } else {
            this.props.handleInputChange(e, {name, value});
        }
    }

    render() {
        this.subcategoryRef = React.createRef();

        return (
            <Grid>
                <Grid.Column computer={8} mobile={16}>
                    <SuggestionInput
                        ref={this.subcategoryRef}
                        name='subcategory'
                        fluid={true}
                        list='subcategory'
                        label='Subcategory'
                        placeholder='Subcategory'
                        value={this.state.subcategory}
                        options={this.state.categories}
                        handleInputChange={this.handleInputChange}
                    />
                </Grid.Column>
                <Grid.Column computer={8} mobile={16}>
                    <label>Category</label>
                    <Form.Input
                        name="category"
                        placeholder="Category"
                        onChange={this.handleInputChange}
                        value={this.state.category}
                    />
                </Grid.Column>
            </Grid>
        )
    }
}

class TableCategoryInputs extends CategoryInputs {
    render() {
        return (
            <>
                <Table.Cell style={{paddingTop: '1.5em', paddingBottom: '1.5em'}}>
                    <SuggestionInput
                        ref={this.subcategoryRef}
                        name='subcategory'
                        fluid={true}
                        list='subcategory'
                        placeholder='Subcategory'
                        value={this.state.subcategory}
                        options={this.state.categories}
                        handleInputChange={this.handleInputChange}
                    />
                </Table.Cell>
                <Table.Cell style={{paddingTop: '1.5em', paddingBottom: '1.5em'}}>
                    <Form.Input
                        fluid
                        name="category"
                        placeholder="Category"
                        onChange={this.handleInputChange}
                        value={this.state.category}
                    />
                </Table.Cell>
            </>
        )
    }
}

class BrandInput extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            brand: '',
            options: [],
        }
    }

    async componentDidMount() {
        await this.fetchBrands();
        this.setState({brand: this.props.value !== undefined ? this.props.value : ''});
    }

    fetchBrands = async () => {
        let brands = await getBrands();
        brands = enumerate(brands);
        let newBrands = [];
        for (let i = 0; i < brands.length; i++) {
            let [key, brand] = brands[i];
            newBrands = newBrands.concat([[key, brand, brand]]);
        }
        this.setState({options: newBrands});
    }

    handleInputChange = (e, {name, value}) => {
        this.setState({[name]: value});
        this.props.handleInputChange(e, {name, value});
    }

    clearInput() {
        this.setState({brand: ''});
    }

    render() {
        return (
            <SuggestionInput
                name='brand'
                fluid={true}
                list='brand'
                label={this.props.label}
                placeholder='Brand'
                value={this.state.brand}
                options={this.state.options}
                handleInputChange={this.handleInputChange}
            />
        )
    }
}

class InventoryAddList extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            inventory: null,
            categories: [],
            sort: {columns: null, direction: 'ascending'},
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
        await this.fetchItems();
    }

    fetchItems = async () => {
        if (this.state.inventory) {
            this.setState({items: []});
            let response = await getItems(this.state.inventory.id);
            let items = response.items;

            this.setState({items: items});
        }
    }

    handleInputChange = (e, {name, value}) => {
        this.setState({[name]: value});
    }

    clearInputs = () => {
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
        this.categoriesRef.current.clearInputs();
        this.brandRef.current.clearInput();
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
            await this.clearInputs();
            await this.fetchItems();
            await this.fetchCategories();
            await this.fetchBrands();
        } else {
            toast({
                type: 'error',
                header: 'Failed to save item!',
                description: 'Server responded with an error.',
                time: 5000,
            })
        }
    }

    setInventory = async (inventory) => {
        this.setState({inventory}, this.fetchItems);
    }

    fetchCategories = async () => {
        await this.categoriesRef.current.fetchCategories();
    }

    fetchBrands = async () => {
        await this.brandRef.current.fetchBrands();
    }

    handleSort = (newColumns) => {
        let sorted = _.sortBy(this.state.items, newColumns);
        let {columns, direction} = this.state.sort;
        if (arraysEqual(columns, newColumns)) {
            direction = direction === 'ascending' ? 'descending' : 'ascending';
        }
        if (direction === 'descending') {
            sorted = sorted.reverse();
        }
        this.setState({items: sorted, sort: {columns: newColumns, direction: direction}});
    }

    render() {
        this.categoriesRef = React.createRef();
        this.brandRef = React.createRef();
        return (
            <>
                <InventorySelector setInventory={this.setInventory}/>
                <Form onSubmit={this.handleSubmit} style={{marginLeft: '0.5em', marginTop: '1em'}}>
                    <Form.Group widths='equal'>
                        <Grid>
                            <Grid.Column computer={2} mobile={16}>
                                <BrandInput
                                    label='Brand'
                                    ref={this.brandRef}
                                    handleInputChange={this.handleInputChange}
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
                            <Grid.Column computer={4} mobile={16}>
                                <CategoryInputs
                                    ref={this.categoriesRef}
                                    handleInputChange={this.handleInputChange}
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
                                <Button primary icon='plus' type='submit' style={{marginTop: '1.4em'}}/>
                            </Grid.Column>
                        </Grid>
                    </Form.Group>
                </Form>
                <h4>Items in: {this.state.inventory ? this.state.inventory.name : ''}</h4>
                <InventoryList
                    items={this.state.items}
                    fetchItems={this.fetchItems}
                    handleSort={this.handleSort}
                    sortColumns={this.state.sort.columns}
                    sortDirection={this.state.sort.direction}
                />
            </>
        )
    }
}

export function InventoryRoute(props) {
    const links = [
        {text: 'List', to: '/inventory', exact: true},
        {text: 'Summary', to: '/inventory/summary'},
    ];
    return (
        <PageContainer>
            <TabLinks links={links}/>
            <Route path='/inventory' exact component={InventoryAddList}/>
            <Route path='/inventory/summary' exact component={InventorySummary}/>
        </PageContainer>
    )
}
