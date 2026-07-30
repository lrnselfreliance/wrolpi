import React from "react";
import {Button, Checkbox, Grid, Message, Modal, Panel, Select} from "./ui";
import {monthNames} from "./Common";

export const dateRangeIsEmpty = (dateRange) => {
    return dateRange[0] === null && dateRange[1] === null;
}

export function MonthsForm({monthsSelected, setMonthsSelected}) {
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
            size='lg'
            onChange={(e) => {
                // Add or remove month index if the respective checkbox is checked.
                const checked = e.currentTarget.checked;
                if (checked) {
                    setMonthsSelected([...monthsSelected, idx]);
                } else {
                    setMonthsSelected(monthsSelected.filter(i => i !== idx));
                }
            }}
        />
    }

    const monthRowStyle = {display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.7em', marginBottom: '0.7em'};
    const seasonRowStyle = {display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.7em'};

    return <div>
        <div style={monthRowStyle}>
            <div>{monthCheckbox('January')}</div>
            <div>{monthCheckbox('February')}</div>
            <div>{monthCheckbox('March')}</div>
        </div>
        <div style={monthRowStyle}>
            <div>{monthCheckbox('April')}</div>
            <div>{monthCheckbox('May')}</div>
            <div>{monthCheckbox('June')}</div>
        </div>
        <div style={monthRowStyle}>
            <div>{monthCheckbox('July')}</div>
            <div>{monthCheckbox('August')}</div>
            <div>{monthCheckbox('September')}</div>
        </div>
        <div style={monthRowStyle}>
            <div>{monthCheckbox('October')}</div>
            <div>{monthCheckbox('November')}</div>
            <div>{monthCheckbox('December')}</div>
        </div>
        <div style={seasonRowStyle}>
            <Button onClick={handleWinter} color='blue' size='small'>Winter</Button>
            <Button onClick={handleSpring} color='green' size='small'>Spring</Button>
            <Button onClick={handleSummer} color='yellow' size='small'>Summer</Button>
            <Button onClick={handleFall} color='red' size='small'>Fall</Button>
        </div>
    </div>
}

export function DateRangeForm({dateRange, setDateRange}) {
    const currentYear = (new Date()).getFullYear();
    const [error, setError] = React.useState('');

    let yearRange = [];
    for (let i = 1970; i <= currentYear; i++) {
        yearRange = [...yearRange, {value: i.toString(), label: i.toString()}];
    }

    const handleFromYear = (value) => {
        const toYear = dateRange[1] || currentYear;
        setDateRange([value ? parseInt(value) : null, toYear]);
    }

    const handleToYear = (value) => {
        setDateRange([dateRange[0], value ? parseInt(value) : null]);
    }

    React.useEffect(() => {
        if (dateRange[0] > dateRange[1]) {
            setError('From Year must be greater than To Year');
        } else {
            setError('');
        }
    }, [dateRange])

    const errorMessage = error && <Message kind='error'>{error}</Message>;

    return <React.Fragment>
        <Grid>
            <Grid.Col span={{base: 12, sm: 6}}>
                <label>From Year</label>
                <Select
                    searchable
                    data={yearRange}
                    value={dateRange[0] != null ? dateRange[0].toString() : null}
                    onChange={handleFromYear}
                    error={!!error}
                    maxDropdownHeight={280}
                />
            </Grid.Col>
            <Grid.Col span={{base: 12, sm: 6}}>
                <label>To Year</label>
                <Select
                    searchable
                    data={[...yearRange].reverse()}
                    value={dateRange[1] != null ? dateRange[1].toString() : null}
                    onChange={handleToYear}
                    error={!!error}
                    maxDropdownHeight={280}
                />
            </Grid.Col>
        </Grid>
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
            icon='calendar'
            onClick={handleOpen}
            color={color}
            {...buttonProps}
        />
        <Modal closeIcon
               open={open}
               onClose={handleClose}
               size='tiny'
        >
            <Modal.Header>Filter by Published Date</Modal.Header>
            <Modal.Content>
                <Panel>
                    <DateRangeForm dateRange={dateRange} setDateRange={localOnSetDateRange}/>
                </Panel>
                <Panel>
                    <MonthsForm monthsSelected={monthsSelected} setMonthsSelected={setMonthsSelected}/>
                </Panel>
            </Modal.Content>
            <Modal.Actions>
                <Button onClick={handleClear} role='cancel'>Clear</Button>
                <Button onClick={handleClose} role='primary'>Close</Button>
            </Modal.Actions>
        </Modal>
    </React.Fragment>
}
