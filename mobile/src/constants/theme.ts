/**
 * Below are the colors that are used in the app. The colors are defined in the light and dark mode.
 * There are many other ways to style your app. For example, [Nativewind](https://www.nativewind.dev/), [Tamagui](https://tamagui.dev/), [unistyles](https://reactnativeunistyles.vercel.app), etc.
 */

import "@/global.css";

import { Platform } from "react-native";

export const Colors = {
  light: {
    text: "#17201D",
    background: "#F7F9F8",
    backgroundElement: "#FFFFFF",
    backgroundSelected: "#E9F5F2",
    textSecondary: "#5F6B66",
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
  canvas: "#FAFBF9",
  surface: "#FFFFFF",
  surfaceMuted: "#F0F4F2",
  ink: "#17201D",
  muted: "#5F6B66",
  border: "#DFE7E3",
  accent: "#0F857A",
  accentDark: "#096B63",
  accentSoft: "#E9F5F2",
  coral: "#FF765E",
  coralSoft: "#FFF0ED",
  danger: "#D94B4B",
  dangerSoft: "#FFF0F0",
  amber: "#B7791F",
  amberSoft: "#FFF7E6",
  success: "#16875B",
  successSoft: "#EAF8F1",
  map: "#EAF0E8",
  mapPark: "#CFE4CD",
  warning: "#B7791F",
} as const;

export const Radius = {
  small: 10,
  medium: 16,
  large: 22,
  pill: 999,
} as const;

export const Shadow = {
  card: "0 5px 18px rgba(23, 32, 29, 0.07)",
  raised: "0 10px 28px rgba(23, 32, 29, 0.11)",
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
  twoHalf: 12,
  three: 16,
  threeHalf: 20,
  four: 24,
  five: 32,
  six: 64,
} as const;

export const BottomTabInset = Platform.select({ ios: 86, android: 86 }) ?? 0;
export const MaxContentWidth = 800;
