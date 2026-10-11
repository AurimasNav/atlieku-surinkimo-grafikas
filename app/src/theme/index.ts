import { useColorScheme } from 'react-native';

import type { WasteKind } from '@/lib/schedule';

const light = {
  background: '#F4F5F0',
  surface: '#FFFFFF',
  surfaceMuted: '#EBEDE6',
  text: '#0D1712',
  textMuted: '#5B675F',
  border: '#E2E5DD',
  primary: '#0F6B47',
  primaryDeep: '#0A4A31',
  onPrimary: '#FFFFFF',
  accent: '#C8F169',
  warning: '#8A4B00',
  warningSurface: '#FFF0D6',
};

const dark: typeof light = {
  background: '#090D0B',
  surface: '#131A16',
  surfaceMuted: '#1C2520',
  text: '#ECF3EE',
  textMuted: '#93A29A',
  border: '#232D27',
  primary: '#3DD68C',
  primaryDeep: '#0F3B28',
  onPrimary: '#04170D',
  accent: '#C8F169',
  warning: '#F5B759',
  warningSurface: '#2E2410',
};

export type Theme = typeof light & { dark: boolean };

export function useTheme(): Theme {
  const isDark = useColorScheme() === 'dark';
  return { ...(isDark ? dark : light), dark: isDark };
}

/** Container colours used in Lithuania: graphite (mixed), yellow (packaging), green (glass). */
export const kindPalette: Record<WasteKind, { solid: string; onSolid: string; soft: string; softDark: string }> = {
  household: { solid: '#2E3440', onSolid: '#FFFFFF', soft: '#E6E8ED', softDark: '#262B33' },
  packaging: { solid: '#FFC53D', onSolid: '#3B2A00', soft: '#FFF2CC', softDark: '#3A2F10' },
  glass: { solid: '#1FAF6E', onSolid: '#FFFFFF', soft: '#D9F4E6', softDark: '#123726' },
};

export const kindIcons = {
  household: 'trash',
  packaging: 'cube',
  glass: 'wine',
} as const satisfies Record<WasteKind, string>;

export const fonts = {
  regular: 'Manrope_500Medium',
  medium: 'Manrope_600SemiBold',
  bold: 'Manrope_700Bold',
  heavy: 'Manrope_800ExtraBold',
} as const;

export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32, xxl: 48 } as const;
export const radius = { sm: 12, md: 18, lg: 28, xl: 36, pill: 999 } as const;
