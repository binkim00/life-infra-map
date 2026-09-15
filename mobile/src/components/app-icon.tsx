import { SymbolView, type AndroidSymbol, type SFSymbol } from "expo-symbols";
import { type ColorValue, type StyleProp, type ViewStyle } from "react-native";

export function AppIcon({ ios, android, size = 22, color, style }: {
  ios: SFSymbol;
  android: AndroidSymbol;
  size?: number;
  color: ColorValue;
  style?: StyleProp<ViewStyle>;
}) {
  return <SymbolView name={{ ios, android, web: android }} size={size} tintColor={color} style={style} />;
}
