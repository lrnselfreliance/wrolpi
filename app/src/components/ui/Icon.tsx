import React from 'react';
import * as Tabler from '@tabler/icons-react';

/*
 * Icons.
 *
 * Tabler's bundled SVG components, which are tree-shaken at build time and need
 * nothing from the network -- an icon font would have to be fetched, and WROLPi
 * has to draw its interface with no connection at all.
 *
 * Icons never name a color.  They stroke with `currentColor`, inheriting from the
 * button or text that wraps them, so status color and every theme come for free.
 */

/** 16px inline (default), 20px emphasis, 24px page-level. */
export type IconSize = 'small' | 'medium' | 'large';

const sizes: Record<IconSize, number> = {small: 16, medium: 20, large: 24};

/**
 * WROLPi's icon names -> Tabler component names.
 *
 * The app names an icon by what it is for -- `icon='book'`, `icon='arrow left'` --
 * rather than by which component draws it, so hundreds of call sites are not coupled
 * to the icon set.  Swapping Tabler for something else is then this table and nothing
 * else.  New code may pass a Tabler component directly as `component` instead.
 */
const iconNameAliases: Record<string, keyof typeof Tabler> = {
    'add': 'IconPlus',
    'apple': 'IconBrandApple',
    'archive': 'IconArchive',
    'arrow alternate circle up': 'IconCircleArrowUp',
    'arrow down': 'IconArrowDown',
    'arrow left': 'IconArrowLeft',
    'arrow right': 'IconArrowRight',
    'arrow up': 'IconArrowUp',
    'balance scale': 'IconScale',
    'book': 'IconBook',
    'bug': 'IconBug',
    'calculator': 'IconCalculator',
    'calendar': 'IconCalendar',
    'car': 'IconCar',
    'certificate': 'IconCertificate',
    'charset': 'IconLanguage',
    'check': 'IconCheck',
    'check circle': 'IconCircleCheck',
    'checkmark': 'IconCheck',
    'chevron down': 'IconChevronDown',
    'chevron left': 'IconChevronLeft',
    'chevron right': 'IconChevronRight',
    'chrome': 'IconBrandChrome',
    'circle': 'IconCircle',
    'circle notch': 'IconLoader2',
    'circle notched': 'IconLoader2',
    'close': 'IconX',
    'closed captioning': 'IconBadgeCc',
    'closed captioning outline': 'IconBadgeCc',
    'columns': 'IconColumns',
    'cogs': 'IconSettingsCog',
    'comments': 'IconMessages',
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
    'food': 'IconToolsKitchen2',
    'font': 'IconTypography',
    'globe': 'IconWorld',
    'hand point right': 'IconHandFinger',
    'hdd': 'IconDeviceSdCard',
    'heart': 'IconHeart',
    'heartbeat': 'IconHeartRateMonitor',
    'help circle': 'IconHelpCircle',
    'history': 'IconHistory',
    'image': 'IconPhoto',
    'info circle': 'IconInfoCircle',
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
    'signal': 'IconAntennaBars5',
    'spinner': 'IconLoader2',
    'star': 'IconStarFilled',
    'star outline': 'IconStar',
    'stop': 'IconPlayerStop',
    'sun': 'IconSun',
    'sun outline': 'IconSun',
    'sync': 'IconRefresh',
    'tachometer alternate': 'IconGauge',
    'tag': 'IconTag',
    'tags': 'IconTags',
    'terminal': 'IconTerminal2',
    'th': 'IconLayoutGrid',
    'th large': 'IconLayoutGrid',
    'thermometer': 'IconTemperature',
    'thumbs up': 'IconThumbUp',
    'tint': 'IconDroplet',
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
    /**
     * The surface behind the stack, as `{'--icon-stack-bg': 'var(--blue)'}`.  Needed
     * wherever the stack is not on the page background — a filled button, a panel.
     */
    style?: React.CSSProperties;
    className?: string;
}

/**
 * Two icons composed into one symbol — a wifi glyph with a question mark on it,
 * say.
 *
 * The corner glyph gets a background matching the surface so it stays legible
 * over the icon beneath it; see `--icon-stack-bg` in ui.css.
 */
export function IconStack({children, corner, label, style, className}: IconStackProps) {
    return <span
        className={['wrolpi-icon-stack', className].filter(Boolean).join(' ')}
        style={style}
        role='img'
        aria-label={label}
    >
        {children}
        <span className='wrolpi-icon-stack-corner' aria-hidden='true'>{corner}</span>
    </span>
}

export interface IconProps extends Omit<React.SVGProps<SVGSVGElement>, 'name' | 'ref'> {
    /** One of the icon names in `iconNameAliases`. */
    name?: string;
    /** A Tabler component, for new code. */
    component?: React.ComponentType<any>;
    size?: IconSize | number;
    /** Rotate continuously; for spinners and in-progress states. */
    loading?: boolean;
    /** Accessible name.  Omit for decorative icons, which are hidden instead. */
    label?: string;
}

/** Resolve an icon name to its Tabler component, or undefined if unmapped. */
export const resolveIconName = (name: string): React.ComponentType<any> | undefined => {
    const taberName = iconNameAliases[name.trim().toLowerCase()];
    return taberName ? (Tabler[taberName] as React.ComponentType<any>) : undefined;
}

export function Icon({name, component, size = 'small', loading, label, ...props}: IconProps) {
    let Component = component;
    if (!Component && name) {
        Component = resolveIconName(name);
        if (!Component) {
            // Loud on purpose: a silently missing icon leaves a hole in the interface.
            console.error(`No icon named "${name}"; add it to iconNameAliases, or pass a Tabler component.`);
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
