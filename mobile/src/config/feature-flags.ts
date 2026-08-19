export const FeatureFlags = {
  floatingMascot: false,
  animatedMascot: false,
  legacyBoneMarkers: false,
} as const;

export type MarkerVisualStyle = "clean-pin" | "legacy-bone";

export const markerVisualStyle: MarkerVisualStyle =
  FeatureFlags.legacyBoneMarkers ? "legacy-bone" : "clean-pin";
