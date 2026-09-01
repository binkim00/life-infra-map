const DEFAULT_DJANGO_API = "http://100.71.169.91:8000/api";

module.exports = ({ config }) => {
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
