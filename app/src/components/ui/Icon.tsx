import React from 'react';
import * as Tabler from '@tabler/icons-react';

/*
 * Icons.
 *
 * Semantic UI shipped an icon font; we use Tabler's bundled SVG components, which
 * are tree-shaken at build time and need nothing from the network.
 *
 * Icons never name a color.  They stroke with `currentColor`, inheriting from the
 * button or text that wraps them, so status color and every theme come for free.
 */

/** 16px inline (default), 20px emphasis, 24px page-level. */
export type IconSize = 'small' | 'medium' | 'large';

const sizes: Record<IconSize, number> = {small: 16, medium: 20, large: 24};

/**
 * Semantic icon name -> Tabler component name.
 *
 * Covers every name the app renders today so call sites can migrate without also
 * choosing new icons.  New code should import the Tabler component directly and
 * pass it as `component`; this map exists for the migration, not forever.
 */
const semanticNames: Record<string, keyof typeof Tabler> = {
    'add': 'IconPlus',
    'apple': 'IconBrandApple',
    'archive': 'IconArchive',
    'arrow alternate circle up': 'IconCircleArrowUp',
    'arrow down': 'IconArrowDown',
    'arrow right': 'IconArrowRight',
    'arrow up': 'IconArrowUp',
    'balance scale': 'IconScale',
    'book': 'IconBook',
    'bug': 'IconBug',
    'calculator': 'IconCalculator',
    'calendar': 'IconCalendar',
    'certificate': 'IconCertificate',
    'charset': 'IconLanguage',
    'check': 'IconCheck',
    'check circle': 'IconCircleCheck',
    'checkmark': 'IconCheck',
    'chevron left': 'IconChevronLeft',
    'chevron right': 'IconChevronRight',
    'chrome': 'IconBrandChrome',
    'circle': 'IconCircle',
    'circle notch': 'IconLoader2',
    'circle notched': 'IconLoader2',
    'close': 'IconX',
    'closed captioning': 'IconBadgeCc',
    'columns': 'IconColumns',
    'copy': 'IconCopy',
    'cube': 'IconCube',
    'directory': 'IconFolder',
    'disk': 'IconDatabase',
    'dot circle': 'IconCircleDot',
    'download': 'IconDownload',
    'dropdown': 'IconChevronDown',
    'edit': 'IconEdit',
    'exclamation': 'IconExclamationMark',
    'exclamation triangle': 'IconAlertTriangle',
    'expand arrows alternate': 'IconArrowsMaximize',
    'external': 'IconExternalLink',
    'eye': 'IconEye',
    'eye slash': 'IconEyeOff',
    'file': 'IconFile',
    'file alternate': 'IconFileDescription',
    'file alternate outline': 'IconFileDescription',
    'file archive': 'IconFileZip',
    'file audio': 'IconFileMusic',
    'file code': 'IconFileCode',
    'file excel': 'IconFileSpreadsheet',
    'file pdf': 'IconFileTypePdf',
    'file pdf outline': 'IconFileTypePdf',
    'file powerpoint': 'IconPresentation',
    'file text': 'IconFileText',
    'file video': 'IconFileSmile',
    'file word': 'IconFileText',
    'film': 'IconMovie',
    'filter': 'IconFilter',
    'firefox': 'IconBrandFirefox',
    'folder': 'IconFolder',
    'folder open': 'IconFolderOpen',
    'folder open outline': 'IconFolderOpen',
    'folder outline': 'IconFolder',
    'font': 'IconTypography',
    'globe': 'IconWorld',
    'hand point right': 'IconHandFinger',
    'hdd': 'IconDeviceSdCard',
    'heart': 'IconHeart',
    'heartbeat': 'IconHeartRateMonitor',
    'history': 'IconHistory',
    'image': 'IconPhoto',
    'lightbulb': 'IconBulb',
    'lightbulb outline': 'IconBulb',
    'lightning': 'IconBolt',
    'linkify': 'IconLink',
    'linux': 'IconBrandUbuntu',
    'list': 'IconList',
    'lock': 'IconLock',
    'mail': 'IconMail',
    'map outline': 'IconMap',
    'microchip': 'IconCpu',
    'minus': 'IconMinus',
    'moon': 'IconMoon',
    'moon outline': 'IconMoon',
    'paypal': 'IconBrandPaypal',
    'play': 'IconPlayerPlay',
    'plug': 'IconPlug',
    'plus': 'IconPlus',
    'print': 'IconPrinter',
    'puzzle piece': 'IconPuzzle',
    'qrcode': 'IconQrcode',
    'question': 'IconHelp',
    'redo': 'IconArrowForwardUp',
    'refresh': 'IconRefresh',
    'rss': 'IconRss',
    'save': 'IconDeviceFloppy',
    'search': 'IconSearch',
    'server': 'IconServer',
    'settings': 'IconSettings',
    'share': 'IconShare',
    'shield': 'IconShield',
    'spinner': 'IconLoader2',
    'star': 'IconStarFilled',
    'star outline': 'IconStar',
    'stop': 'IconPlayerStop',
    'sun': 'IconSun',
    'sun outline': 'IconSun',
    'sync': 'IconRefresh',
    'tachometer alternate': 'IconGauge',
    'tag': 'IconTag',
    'terminal': 'IconTerminal2',
    'th': 'IconLayoutGrid',
    'thumbs up': 'IconThumbUp',
    'trash': 'IconTrash',
    'undo': 'IconArrowBackUp',
    'unlock': 'IconLockOpen',
    'upload': 'IconUpload',
    'usb': 'IconUsb',
    'volume up': 'IconVolume',
    'warning': 'IconAlertTriangle',
    'warning circle': 'IconAlertCircle',
    'warning sign': 'IconAlertTriangle',
    'wifi': 'IconWifi',
    'windows': 'IconBrandWindows',
    'wrench': 'IconTool',
    'x': 'IconX',
};

export interface IconStackProps {
    /** The main glyph. */
    children: React.ReactNode;
    /** A smaller glyph pinned to the bottom-right, qualifying the first. */
    corner: React.ReactNode;
    /** Accessible name for the pair; the two glyphs mean one thing together. */
    label: string;
}

/**
 * Two icons composed into one symbol — a wifi glyph with a question mark on it,
 * say.  Replaces Semantic's IconGroup.
 *
 * The corner glyph gets a background matching the surface so it stays legible
 * over the icon beneath it.
 */
export function IconStack({children, corner, label}: IconStackProps) {
    return <span className='wrolpi-icon-stack' role='img' aria-label={label}>
        {children}
        <span className='wrolpi-icon-stack-corner' aria-hidden='true'>{corner}</span>
    </span>
}

export interface IconProps extends Omit<React.SVGProps<SVGSVGElement>, 'name' | 'ref'> {
    /** A Semantic UI icon name, for migrated call sites. */
    name?: string;
    /** A Tabler component, for new code. */
    component?: React.ComponentType<any>;
    size?: IconSize | number;
    /** Rotate continuously; for spinners and in-progress states. */
    loading?: boolean;
    /** Accessible name.  Omit for decorative icons, which are hidden instead. */
    label?: string;
}

/** Resolve a Semantic icon name to its Tabler component, or undefined if unmapped. */
export const resolveIconName = (name: string): React.ComponentType<any> | undefined => {
    const taberName = semanticNames[name.trim().toLowerCase()];
    return taberName ? (Tabler[taberName] as React.ComponentType<any>) : undefined;
}

export function Icon({name, component, size = 'small', loading, label, ...props}: IconProps) {
    let Component = component;
    if (!Component && name) {
        Component = resolveIconName(name);
        if (!Component) {
            // Loud on purpose: a silently missing icon leaves a hole in the interface.
            console.error(`No icon for Semantic name "${name}"; pass a Tabler component instead.`);
            Component = Tabler.IconHelpCircle;
        }
    }
    if (!Component) {
        console.error('Icon requires `name` or `component`.');
        return null;
    }

    const pixels = typeof size === 'number' ? size : sizes[size];
    return <Component
        size={pixels}
        stroke={2}
        className={loading ? 'wrolpi-icon-spin' : undefined}
        aria-hidden={label ? undefined : 'true'}
        aria-label={label}
        role={label ? 'img' : undefined}
        {...props}
    />
}
