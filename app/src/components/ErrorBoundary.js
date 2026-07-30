import React from 'react';
import {Box, Button, ButtonGroup, Message, Panel} from './ui';

/**
 * Error Boundary component that catches JavaScript errors in child components
 * and displays a fallback UI instead of crashing the entire app.
 *
 * Usage:
 *   <ErrorBoundary>
 *     <ComponentThatMightThrow />
 *   </ErrorBoundary>
 *
 * With custom fallback:
 *   <ErrorBoundary fallback={<div>Something went wrong</div>}>
 *     <ComponentThatMightThrow />
 *   </ErrorBoundary>
 */
class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = {hasError: false, error: null, errorInfo: null};
    }

    static getDerivedStateFromError(error) {
        // Update state so next render shows fallback UI
        return {hasError: true, error};
    }

    componentDidCatch(error, errorInfo) {
        // Log the error for debugging
        console.error('ErrorBoundary caught an error:', error);
        console.error('Component stack:', errorInfo?.componentStack);
        this.setState({errorInfo});
    }

    handleReset = () => {
        this.setState({hasError: false, error: null, errorInfo: null});
    };

    handleReload = () => {
        window.location.reload();
    };

    render() {
        if (this.state.hasError) {
            // Allow custom fallback UI
            if (this.props.fallback) {
                return this.props.fallback;
            }

            const {error} = this.state;
            const errorMessage = error?.message || 'An unexpected error occurred';

            return (
                <Box style={{padding: '2em'}}>
                    <Message kind='error' icon='warning sign' title='Something went wrong'>
                        <p>{errorMessage}</p>
                        <ButtonGroup>
                            <Button onClick={this.handleReset} role='primary' icon='refresh'>
                                Try Again
                            </Button>
                            <Button onClick={this.handleReload} icon='redo'>
                                Reload Page
                            </Button>
                        </ButtonGroup>
                    </Message>
                </Box>
            );
        }

        return this.props.children;
    }
}

/**
 * A minimal error boundary for inline components that shows a simple error message.
 */
class InlineErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = {hasError: false};
    }

    static getDerivedStateFromError() {
        return {hasError: true};
    }

    componentDidCatch(error, errorInfo) {
        console.error('InlineErrorBoundary caught:', error, errorInfo?.componentStack);
    }

    render() {
        if (this.state.hasError) {
            return (
                <Panel>
                    <Message kind='error' icon='warning'>
                        Failed to load this section
                    </Message>
                </Panel>
            );
        }
        return this.props.children;
    }
}

export default ErrorBoundary;
export {ErrorBoundary, InlineErrorBoundary};
