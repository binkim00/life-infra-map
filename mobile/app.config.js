const DEFAULT_DJANGO_API =
  "https://life-infra-map-db.taile29cc8.ts.net/django/api";
const PUBLIC_API_ENV_NAMES = [
  "EXPO_PUBLIC_DJANGO_API_BASE_URL",
  "EXPO_PUBLIC_SPRING_API_BASE_URL",
  "EXPO_PUBLIC_KAKAO_MAP_EMBED_URL",
];

module.exports = ({ config }) => {
  if (process.env.EAS_BUILD_PROFILE === "production") {
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

  if (!allowHttpApi) return config;

  return {
    ...config,
    ios: {
      ...config.ios,
      infoPlist: {
        ...config.ios?.infoPlist,
        NSAppTransportSecurity: {
          ...config.ios?.infoPlist?.NSAppTransportSecurity,
          NSAllowsArbitraryLoads: true,
        },
      },
    },
    android: {
      ...config.android,
      usesCleartextTraffic: true,
    },
  };
};
