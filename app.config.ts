import { ExpoConfig, ConfigContext } from "expo/config";
export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: "HuskyFind",
  slug: "huskyfind",
  android: {
    ...config.android,
    config: { googleMaps: { apiKey: process.env.GOOGLE_MAPS_API_KEY || "" } },
  },
  extra: {
    eas: { projectId: process.env.EXPO_PUBLIC_EAS_PROJECT_ID || undefined },
  },
});
