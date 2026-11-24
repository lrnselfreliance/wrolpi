/* eslint-disable no-restricted-globals */
// A worker for the past days' fallout (climatePool.js).
import {serveClimateDays} from './climatology.js';

serveClimateDays(self);
