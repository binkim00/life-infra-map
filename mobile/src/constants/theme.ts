/**
 * Below are the colors that are used in the app. The colors are defined in the light and dark mode.
 * There are many other ways to style your app. For example, [Nativewind](https://www.nativewind.dev/), [Tamagui](https://tamagui.dev/), [unistyles](https://reactnativeunistyles.vercel.app), etc.
 */

import "@/global.css";

import { Platform } from "react-native";

export const Colors = {
  light: {
    text: "#222222",
    background: "#FFF9EF",
    backgroundElement: "#FFFFFF",
    backgroundSelected: "#EFE8DC",
    textSecondary: "#686159",
  },
  dark: {
    text: "#F8F5EF",
    background: "#171614",
    backgroundElement: "#24211D",
    backgroundSelected: "#353029",
    textSecondary: "#C6BEB2",
  },
} as const;

export const Palette = {
  canvas: "#FFF9EF",
  surface: "#FFFFFF",
  surfaceMuted: "#F7F3EC",
  ink: "#222222",
  muted: "#686159",
  border: "#E7E0D5",
  accent: "#0F766E",
  accentSoft: "#E6F4F1",
  map: "#EAF0E8",
  mapPark: "#CFE4CD",
  warning: "#A16207",
} as const;

export const Radius = {
  small: 10,
  medium: 16,
  large: 24,
  pill: 999,
} as const;

export const Shadow = {
  card: "0 10px 30px rgba(52, 44, 35, 0.08)",
  marker: "0 5px 12px rgba(34, 34, 34, 0.2)",
} as const;

export type ThemeColor = keyof typeof Colors.light & keyof typeof Colors.dark;

export const Fonts = Platform.select({
  ios: {
    /** iOS `UIFontDescriptorSystemDesignDefault` */
    sans: "system-ui",
    /** iOS `UIFontDescriptorSystemDesignSerif` */
    serif: "ui-serif",
    /** iOS `UIFontDescriptorSystemDesignRounded` */
    rounded: "ui-rounded",
    /** iOS `UIFontDescriptorSystemDesignMonospaced` */
    mono: "ui-monospace",
  },
  default: {
    sans: "normal",
    serif: "serif",
    rounded: "normal",
    mono: "monospace",
  },
  web: {
    sans: "var(--font-display)",
    serif: "var(--font-serif)",
    rounded: "var(--font-rounded)",
    mono: "var(--font-mono)",
  },
});

export const Spacing = {
  half: 2,
  one: 4,
  two: 8,
  three: 16,
  four: 24,
  five: 32,
  six: 64,
} as const;

export const BottomTabInset = Platform.select({ ios: 50, android: 80 }) ?? 0;
export const MaxContentWidth = 800;
