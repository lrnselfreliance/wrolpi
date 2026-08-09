import {mount} from 'cypress/react'

// Cypress 14 dropped the separate cypress/react18 entry point; cypress/react mounts React 18 itself.
Cypress.Commands.add('mount', mount);
