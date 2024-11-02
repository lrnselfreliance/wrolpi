import {mount} from 'cypress/react18'

// Use React 18 for all mounts.
Cypress.Commands.add('mount', mount);
