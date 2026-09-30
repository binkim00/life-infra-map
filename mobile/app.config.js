const DEFAULT_DJANGO_API =
  "https://life-infra-map-db.taile29cc8.ts.net/django/api";
const PRODUCTION_ENDPOINTS = {
  EXPO_PUBLIC_DJANGO_API_BASE_URL: "https://yeogiljido.com/django/api",
  EXPO_PUBLIC_SPRING_API_BASE_URL: "https://yeogiljido.com/spring/api",
  EXPO_PUBLIC_KAKAO_MAP_EMBED_URL: "https://yeogiljido.com/kakao-map-embed.html",
};

module.exports = ({ config }) => {
  const isProduction = process.env.EAS_BUILD_PROFILE === "production";
  if (isProduction) {
    const invalidNames = Object.entries(PRODUCTION_ENDPOINTS)
      .filter(([name, expected]) => process.env[name] !== expected)
      .map(([name]) => name);
    if (invalidNames.length) {
      throw new Error(
        `Production builds require public endpoints for: ${invalidNames.join(", ")}`,
      );
    }
  }

  const djangoApi =
    process.env.EXPO_PUBLIC_DJANGO_API_BASE_URL || DEFAULT_DJANGO_API;
  const allowHttpApi = djangoApi.startsWith("http://");
  const nextConfig = {
    ...config,
    name: isProduction ? "여기일지도" : "여기일지도 (테스트)",
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
