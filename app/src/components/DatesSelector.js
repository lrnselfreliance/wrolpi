import React from "react";
import {Button, Form, FormField, Modal, ModalActions, ModalContent, ModalHeader, Segment} from "./Theme";
import {Checkbox, Dropdown} from "semantic-ui-react";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {monthNames} from "./Common";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";

export const dateRangeIsEmpty = (dateRange) => {
    return dateRange[0] === null && dateRange[1] === null;
}

function MonthsForm({monthsSelected, setMonthsSelected}) {
    monthsSelected = monthsSelected.map(i => parseInt(i));

    const handleWinter = (e) => {
        if (e) e.preventDefault();
        setMonthsSelected([12, 1, 2]);
    }

    const handleSpring = (e) => {
        if (e) e.preventDefault();
        setMonthsSelected([3, 4, 5]);
    }

    const handleSummer = (e) => {
        if (e) e.preventDefault();
        setMonthsSelected([6, 7, 8]);
    }

    const handleFall = (e) => {
        if (e) e.preventDefault();
        setMonthsSelected([9, 10, 11]);
    }

    const monthCheckbox = (label) => {
        // "January" == 1, etc.
        const idx = monthNames.indexOf(label) + 1;
        const isChecked = monthsSelected.indexOf(idx) >= 0;
        return <Checkbox
            label={label}
            checked={isChecked}
            size='large'
            onChange={(e, {checked}) => {
                // Add or remove month index if the respective checkbox is checked.
                if (checked) {
                    setMonthsSelected([...monthsSelected, idx]);
                } else {
                    setMonthsSelected(monthsSelected.filter(i => i !== idx));
                }
            }}
        />
    }

    return <Form>
        <Grid>
            <Grid.Row columns={3}>
                <Grid.Column>{monthCheckbox('January')}</Grid.Column>
                <Grid.Column>{monthCheckbox('February')}</Grid.Column>
                <Grid.Column>{monthCheckbox('March')}</Grid.Column>
            </Grid.Row>
            <Grid.Row columns={3}>
                <Grid.Column>{monthCheckbox('April')}</Grid.Column>
                <Grid.Column>{monthCheckbox('May')}</Grid.Column>
                <Grid.Column>{monthCheckbox('June')}</Grid.Column>
            </Grid.Row>
            <Grid.Row columns={3}>
                <Grid.Column>{monthCheckbox('July')}</Grid.Column>
                <Grid.Column>{monthCheckbox('August')}</Grid.Column>
                <Grid.Column>{monthCheckbox('September')}</Grid.Column>
            </Grid.Row>
            <Grid.Row columns={3}>
                <Grid.Column>{monthCheckbox('October')}</Grid.Column>
                <Grid.Column>{monthCheckbox('November')}</Grid.Column>
                <Grid.Column>{monthCheckbox('December')}</Grid.Column>
            </Grid.Row>
            <Grid.Row columns={4}>
                <Grid.Column><Button onClick={handleWinter} color='blue' size='small'>Winter</Button></Grid.Column>
                <Grid.Column><Button onClick={handleSpring} color='green' size='small'>Spring</Button></Grid.Column>
                <Grid.Column><Button onClick={handleSummer} color='yellow' size='small'>Summer</Button></Grid.Column>
                <Grid.Column><Button onClick={handleFall} color='red' size='small'>Fall</Button></Grid.Column>
            </Grid.Row>
        </Grid>
    </Form>
}

function DateRangeForm({dateRange, setDateRange}) {
    const currentYear = (new Date()).getFullYear();
    const [error, setError] = React.useState('');

    let yearRange = [];
    for (let i = 1970; i <= currentYear; i++) {
        yearRange = [...yearRange, {
            key: i,
            text: i,
            value: i,
        }];
    }

    const handleFromYear = (e, {value}) => {
        const toYear = dateRange[1] || currentYear;
        setDateRange([value, toYear]);
    }

    const handleToYear = (e, {value}) => {
        setDateRange([dateRange[0], value]);
    }

    React.useEffect(() => {
        if (dateRange[0] > dateRange[1]) {
            setError('From Year must be greater than To Year');
        } else {
            setError('');
        }
    }, [dateRange])

    const errorMessage = error && <Message error content={error}/>;

    return <React.Fragment>
        <Form>
            <Grid>
                <Grid.Row columns={2}>
                    <Grid.Column>
                        <FormField>
                            <label>From Year</label>
                            <Dropdown search scrolling fluid
                                      options={yearRange}
                                      value={dateRange[0]}
                                      onChange={handleFromYear}
                                      error={!!error}
                            />
                        </FormField>
                    </Grid.Column>
                    <Grid.Column>
                        <FormField>
                            <label>To Year</label>
                            <Dropdown search scrolling fluid
                                      options={yearRange.reverse()}
                                      value={dateRange[1]}
                                      onChange={handleToYear}
                                      error={!!error}
                            />
                        </FormField>
                    </Grid.Column>
                </Grid.Row>
            </Grid>
        </Form>
        {errorMessage}
    </React.Fragment>
}

export function DateSelectorButton({
                                       onDatesChange,
                                       defaultMonthsSelected,
                                       defaultDateRange,
                                       onClear,
                                       buttonProps
                                   }) {
    const emptyDateRange = [null, null];

    const [open, setOpen] = React.useState(false);
    const [monthsSelected, setMonthsSelected] = React.useState(defaultMonthsSelected || []);
    const [dateRange, setDateRange] = React.useState(defaultDateRange || emptyDateRange);
    const [color, setColor] = React.useState('grey');

    React.useEffect(() => {
        if (monthsSelected.length > 0 || (!dateRangeIsEmpty(dateRange))) {
            setColor('violet');
        } else {
            setColor('grey');
        }
    }, [JSON.stringify(dateRange), JSON.stringify(monthsSelected)]);

    React.useEffect(() => {
        if (!defaultMonthsSelected || (defaultMonthsSelected && defaultMonthsSelected.length === 0)) {
            setMonthsSelected([]);
        }
        console.log(defaultDateRange);
        if (!defaultDateRange || (defaultDateRange && defaultDateRange.length === 2
            && defaultDateRange[0] == null && defaultDateRange[1] === null)) {
            setDateRange(emptyDateRange);
        }
    }, [JSON.stringify(defaultMonthsSelected), JSON.stringify(defaultDateRange)]);

    const handleOpen = (e) => {
        if (e) e.preventDefault();
        setOpen(true);
    }

    const handleClose = (e) => {
        if (e) e.preventDefault();
        setOpen(false);
        // Only submit selection when user has closed selector.
        let newFromDate;
        let newToDate;
        let newMonths;
        if (dateRange && dateRange[0] <= dateRange[1]) {
            newFromDate = dateRange[0];
            newToDate = dateRange[1];
        }
        if (monthsSelected) {
            newMonths = monthsSelected;
        }
        if (onDatesChange) {
            onDatesChange(newFromDate, newToDate, newMonths);
        }
    }

    const localOnSetDateRange = (newDateRange) => {
        setDateRange(newDateRange);
    }

    const handleClear = (e) => {
        if (e) e.preventDefault();
        setDateRange(emptyDateRange);
        setMonthsSelected([]);
        if (onClear) {
            onClear();
        }
        setOpen(false);
    }

    return <React.Fragment>
        <Button
            icon='calendar alternate'
            onClick={handleOpen}
            color={color}
            {...buttonProps}
        />
        <Modal closeIcon
               open={open}
               onClose={handleClose}
               size='tiny'
        >
            <ModalHeader>Filter by Published Date</ModalHeader>
            <ModalContent>
                <Segment>
                    <DateRangeForm dateRange={dateRange} setDateRange={localOnSetDateRange}/>
                </Segment>
                <Segment>
                    <MonthsForm monthsSelected={monthsSelected} setMonthsSelected={setMonthsSelected}/>
                </Segment>
            </ModalContent>
            <ModalActions>
                <Button onClick={handleClear} secondary>Clear</Button>
                <Button onClick={handleClose}>Close</Button>
            </ModalActions>
        </Modal>
    </React.Fragment>
}
