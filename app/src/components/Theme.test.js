import React from 'react';
import {Button, Modal, Progress} from './Theme';
import {renderInDarkMode, renderInLightMode} from '../test-utils';

// All semantic-ui colors.
const allColors = ['red', 'orange', 'yellow', 'olive', 'green', 'teal', 'blue', 'violet', 'purple', 'pink', 'brown', 'grey'];

// Light bar colors that always need dark percent text (light bars in any theme).
const lightBarColors = ['yellow', 'olive', 'teal'];
// Bar colors that need dark percent text only in dark mode (inverted makes bar lighter).
const darkModeLightBarColors = ['grey', 'blue'];

describe('Button ref forwarding', () => {
    // Regression: SButton is a class component, so forwarding a ref straight to it resolves to the class instance
    // (no `.contains`). Semantic UI's Modal/Popup Portal calls `node.contains(...)` on the trigger's ref during
    // handleDocumentClick, throwing "node.contains is not a function". The forwarded ref must be the DOM <button>.
    it('resolves a forwarded ref to the underlying DOM element', () => {
        const ref = React.createRef();
        renderInLightMode(<Button ref={ref} content='Click'/>);

        expect(ref.current).toBeInstanceOf(HTMLElement);
        expect(typeof ref.current.contains).toBe('function');
        expect(ref.current.tagName).toBe('BUTTON');
    });

    it('does not throw when a Button is used as a controlled Modal trigger and the document is clicked', () => {
        // Reproduces the Control page crash: an open Modal whose trigger is a themed Button. A document click
        // invokes the Portal's handleDocumentClick -> doesNodeContainClick(triggerRef.current, e).
        renderInLightMode(
            <Modal open trigger={<Button content='Open'/>}>
                <Modal.Content>content</Modal.Content>
            </Modal>
        );

        expect(() => {
            document.body.dispatchEvent(new MouseEvent('click', {bubbles: true}));
        }).not.toThrow();
    });
});

describe('Progress component theme support', () => {
    describe('dark mode', () => {
        it('adds inverted-progress-text class for label readability', () => {
            const {container} = renderInDarkMode(
                <Progress percent={39} progress indicating color='violet'>
                    2.1 GB / 5.3 GB
                </Progress>
            );

            const progressEl = container.querySelector('.ui.progress');
            expect(progressEl).toHaveClass('inverted-progress-text');

            const progressLabel = container.querySelector('.bar > .progress');
            expect(progressLabel).toHaveTextContent('39%');

            const label = container.querySelector('.ui.progress > .label');
            expect(label).toHaveTextContent('2.1 GB / 5.3 GB');
        });

        it('does NOT add inverted-progress-text in light mode', () => {
            const {container} = renderInLightMode(
                <Progress percent={39} progress indicating color='violet'>
                    2.1 GB / 5.3 GB
                </Progress>
            );

            const progressEl = container.querySelector('.ui.progress');
            expect(progressEl).not.toHaveClass('inverted-progress-text');
        });
    });

    describe('percent text contrast per color', () => {
        allColors.forEach(color => {
            it(`${color} bar has readable percent text in light mode`, () => {
                const {container} = renderInLightMode(
                    <Progress percent={50} progress color={color}/>
                );

                const progressLabel = container.querySelector('.bar > .progress');
                expect(progressLabel).toBeInTheDocument();
                expect(progressLabel).toHaveTextContent('50%');

                const progressEl = container.querySelector('.ui.progress');
                if (lightBarColors.includes(color)) {
                    expect(progressEl).toHaveClass('light-bar-progress-text');
                } else {
                    expect(progressEl).not.toHaveClass('light-bar-progress-text');
                }
            });

            it(`${color} bar has readable percent text in dark mode`, () => {
                const {container} = renderInDarkMode(
                    <Progress percent={50} progress color={color}/>
                );

                const progressLabel = container.querySelector('.bar > .progress');
                expect(progressLabel).toBeInTheDocument();
                expect(progressLabel).toHaveTextContent('50%');

                const progressEl = container.querySelector('.ui.progress');
                if (lightBarColors.includes(color) || darkModeLightBarColors.includes(color)) {
                    expect(progressEl).toHaveClass('light-bar-progress-text');
                } else {
                    expect(progressEl).not.toHaveClass('light-bar-progress-text');
                }
            });
        });
    });
});
