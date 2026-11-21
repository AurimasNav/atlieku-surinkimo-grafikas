// The widget library turns these components into a tree by calling them as plain functions;
// the React Compiler's memoisation breaks that.
'use no memo';

import { FlexWidget, TextWidget } from 'react-native-android-widget';

import { kindPalette } from '@/theme';

import type { WidgetModel } from './model';

export const WIDGET_NAME = 'NextPickup';

type HexColor = `#${string}`;

const palettes = {
  light: { from: '#0F6B47', to: '#0A4A31', text: '#FFFFFF', muted: '#D7E8DF', accent: '#C8F169' },
  dark: { from: '#11402C', to: '#0A2A1D', text: '#ECF3EE', muted: '#A9BDB2', accent: '#C8F169' },
} as const satisfies Record<string, Record<string, HexColor>>;

/** The next pickup, in the colours of the app's home screen card. Tapping it opens the app. */
export function NextPickupWidget({ model, scheme }: { model: WidgetModel; scheme: 'light' | 'dark' }) {
  const colors = palettes[scheme];
  return (
    <FlexWidget
      clickAction="OPEN_APP"
      style={{
        height: 'match_parent',
        width: 'match_parent',
        flexDirection: 'column',
        justifyContent: 'space-between',
        padding: 16,
        borderRadius: 24,
        backgroundGradient: { from: colors.from, to: colors.to, orientation: 'TL_BR' },
      }}>
      <FlexWidget style={{ flexDirection: 'column', width: 'match_parent' }}>
        <TextWidget
          text={model.place ?? ''}
          maxLines={1}
          truncate="END"
          style={{ fontSize: 12, color: colors.accent, fontWeight: '700', letterSpacing: 0.08 }}
        />
        {/* No fragments: the widget tree only takes widget elements. */}
        {model.state === 'pickup' && (
          <TextWidget text={model.when} maxLines={1} style={{ fontSize: 28, color: colors.text, fontWeight: '800' }} />
        )}
        {model.state === 'pickup' && (
          <TextWidget text={model.date} maxLines={1} truncate="END" style={{ fontSize: 13, color: colors.muted, fontWeight: '600' }} />
        )}
        {model.state === 'empty' && (
          <TextWidget text={model.message} maxLines={3} style={{ fontSize: 14, color: colors.text, fontWeight: '600' }} />
        )}
      </FlexWidget>
      {model.state === 'pickup' && (
        <FlexWidget style={{ flexDirection: 'row', width: 'match_parent' }}>
          {model.kinds.map(({ kind, name }) => (
            <FlexWidget
              key={kind}
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                marginRight: 6,
                marginTop: 6,
                paddingHorizontal: 10,
                paddingVertical: 4,
                borderRadius: 999,
                backgroundColor: kindPalette[kind].solid as HexColor,
              }}>
              <TextWidget
                text={model.done ? `✓ ${name}` : name}
                style={{ fontSize: 12, color: kindPalette[kind].onSolid as HexColor, fontWeight: '700' }}
              />
            </FlexWidget>
          ))}
        </FlexWidget>
      )}
    </FlexWidget>
  );
}
