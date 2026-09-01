module.exports = ({ config }) => {
  const allowHttpApi = process.env.EXPO_PUBLIC_ALLOW_HTTP_API === "true";

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
