import { ExpoConfig, ConfigContext } from "expo/config";
export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: "HuskyFind",
  slug: "huskyfind",
  plugins: [
    ...(config.plugins || []),
    [
      "react-native-maps",
      { androidGoogleMapsApiKey: process.env.GOOGLE_MAPS_API_KEY || "" },
    ],
  ],
  experiments: {
    ...(config.experiments || {}),
    // Static web builds hosted under a subpath (e.g. GitHub Pages) set this.
    ...(process.env.EXPO_WEB_BASE_URL
      ? { baseUrl: process.env.EXPO_WEB_BASE_URL }
      : {}),
  },
  extra: {
    ...config.extra,
    eas: {
      projectId:
        process.env.EXPO_PUBLIC_EAS_PROJECT_ID ||
        "d817ed9d-7e58-4242-b262-f643998bf60a",
    },
  },
});
