/* eslint-disable no-restricted-globals */
// A worker for the fallout (pool.js): the past days', or the bursts'.
import {serveFallout} from './work.js';

serveFallout(self);
