const DEFAULT_DJANGO_API =
  "https://life-infra-map-db.taile29cc8.ts.net/django/api";
const PUBLIC_API_ENV_NAMES = [
  "EXPO_PUBLIC_DJANGO_API_BASE_URL",
  "EXPO_PUBLIC_SPRING_API_BASE_URL",
  "EXPO_PUBLIC_KAKAO_MAP_EMBED_URL",
];

module.exports = ({ config }) => {
  const isProduction = process.env.EAS_BUILD_PROFILE === "production";
  if (isProduction) {
    const invalidNames = PUBLIC_API_ENV_NAMES.filter((name) => {
      const value = process.env[name] || "";
      return !value.startsWith("https://");
    });
    if (invalidNames.length) {
      throw new Error(
        `Production builds require HTTPS values for: ${invalidNames.join(", ")}`,
      );
    }
  }

  const djangoApi =
    process.env.EXPO_PUBLIC_DJANGO_API_BASE_URL || DEFAULT_DJANGO_API;
  const allowHttpApi = djangoApi.startsWith("http://");
  const nextConfig = {
    ...config,
    name: isProduction ? "생활 인프라 지도" : "생활 인프라 지도 (테스트)",
    android: {
      ...config.android,
      package: isProduction
        ? "com.binkim00.lifeinframap"
        : "com.binkim00.lifeinframap.test",
      ...(allowHttpApi ? { usesCleartextTraffic: true } : {}),
    },
  };

  if (!allowHttpApi) return nextConfig;

  return {
    ...nextConfig,
    ios: {
      ...nextConfig.ios,
      infoPlist: {
        ...nextConfig.ios?.infoPlist,
        NSAppTransportSecurity: {
          ...nextConfig.ios?.infoPlist?.NSAppTransportSecurity,
          NSAllowsArbitraryLoads: true,
        },
      },
    },
  };
};
