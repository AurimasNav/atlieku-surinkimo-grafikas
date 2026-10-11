import { useColorScheme } from 'react-native';

import type { WasteKind } from '@/lib/schedule';

const light = {
  background: '#F4F6F3',
  surface: '#FFFFFF',
  surfaceMuted: '#E9EDE7',
  text: '#15201A',
  textMuted: '#5E6B63',
  border: '#DCE2DA',
  primary: '#1F7A4D',
  onPrimary: '#FFFFFF',
  warning: '#9A5B00',
  warningSurface: '#FFF3DC',
};

const dark: typeof light = {
  background: '#0E1311',
  surface: '#18201C',
  surfaceMuted: '#222C27',
  text: '#ECF2EE',
  textMuted: '#9AA8A0',
  border: '#2C3832',
  primary: '#4CC38A',
  onPrimary: '#06210F',
  warning: '#F2B65A',
  warningSurface: '#33270F',
};

/** Matches the container colours used in Lithuania. */
export const kindColors: Record<WasteKind, string> = {
  household: '#6B7280',
  packaging: '#E5A50A',
  glass: '#2E9E5B',
};

export const kindIcons = {
  household: 'trash-outline',
  packaging: 'cube-outline',
  glass: 'wine-outline',
} as const satisfies Record<WasteKind, string>;

export type Theme = typeof light;

export function useTheme(): Theme {
  return useColorScheme() === 'dark' ? dark : light;
}

export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 } as const;
export const radius = { sm: 10, md: 16, lg: 24, pill: 999 } as const;
