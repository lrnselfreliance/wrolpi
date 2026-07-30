/*
 * The WROLPi component library: token-driven components built on Mantine.
 *
 * Import from here, not from `@mantine/core` or `semantic-ui-react`:
 *   import {Button, Table, Message} from '../components/ui';
 *
 * Everything resolves its colors through theme tokens, so no component branches
 * on the current theme.  See ui-design.md for the rules and
 * ui-migration-plan.md for how call sites move here.
 */

import './ui.css';

export * from './Icon';
export * from './Button';
export * from './Feedback';
export * from './Surfaces';
export * from './DataTable';
export * from './Inputs';
export * from './Overlays';
export * from './toast';

// Layout primitives are used as-is; they carry no colors of their own.
export {Anchor, Box, Center, Divider, Flex, Grid, Group, Space, Stack, Text, Title} from '@mantine/core';
