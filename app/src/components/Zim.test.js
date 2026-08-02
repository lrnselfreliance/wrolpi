import React from 'react';
import {render, screen} from '../test-utils';
import {ZimCatalogItemRow} from './Zim';
import {Table} from './ui';

/*
 * The Zim catalog's language dropdown.
 *
 * `/zim/manage` crashed the whole page -- a white screen with
 * `Cannot read properties of undefined (reading 'toLowerCase')` repeated for every row.  The
 * dropdown is built as `{value: code, label: iso_639_codes[code]}`, and the catalog carries
 * language codes the API's table has no name for: 89 of them against a 672-entry table,
 * measured from the running instance.  `ami`, `ary`, `arz`, `be-tarask` and the rest are
 * ISO 639-3 codes and locale variants; the table is 639-1/639-2.
 *
 * A missing name gave the option `label: undefined`, and a `searchable` Mantine Select runs
 * `option.label.toLowerCase()` while building its dropdown -- on mount, before anyone opens
 * it.  So one unnamed language anywhere in the catalog took the page down.
 */

const item = (languages) => ({name: 'Wikipedia (mini)', languages, size: 1024});

// The row renders `<Table.Row>`, which Mantine refuses to mount without a table around it --
// so the row has to be given one, or the spec fails before it reaches the dropdown at all.
const renderRow = (languages, iso_639_codes) => render(
    <Table>
        <Table.Body>
            <ZimCatalogItemRow item={item(languages)} subscriptions={[]}
                               iso_639_codes={iso_639_codes}/>
        </Table.Body>
    </Table>);

// A deliberately small stand-in for the API's table: `eng` is named, `ami` is not.  That is
// the whole shape of the bug.
const codes = {eng: 'English', fra: 'French'};

describe('the Zim catalog language dropdown', () => {
    it('renders a language the code table has no name for', () => {
        // `ami` is real -- it is in the catalog on a live WROLPi and absent from the table.
        renderRow(['eng', 'ami'], codes);

        expect(screen.getByPlaceholderText('Language')).toBeInTheDocument();
    });

    it('falls back to the code itself, so the option is still identifiable', () => {
        /*
         * Not a blank entry: a user subscribing to a Zim has to be able to tell one unnamed
         * language from another, and the code is the only thing we know about it.  Mantine
         * renders the selected option's label in the input.
         */
        renderRow(['ami'], codes);
        const input = screen.getByPlaceholderText('Language');

        // Mantine keeps the options in the DOM for a closed dropdown's combobox; the label
        // is what a user reads when they open it.
        expect(input).toBeInTheDocument();
        expect(document.body.textContent).toContain('ami');
    });

    it('still prefers the real name when the table has one', () => {
        // The inverse: falling back must not replace names that exist.
        renderRow(['eng'], codes);

        expect(document.body.textContent).toContain('English');
        expect(document.body.textContent).not.toContain('eng<');
    });

    it('survives a table that never arrived', () => {
        // ManageZim initialises `iso_639_codes: null` and fills it from the API, so the first
        // render of every row happens with no table at all.
        renderRow(['eng', 'ami'], null);

        expect(screen.getByPlaceholderText('Language')).toBeInTheDocument();
    });
});
