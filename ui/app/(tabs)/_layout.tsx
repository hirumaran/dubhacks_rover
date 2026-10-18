import React from "react";
import { Redirect, Tabs } from "expo-router";
import {
  Compass,
  MapPin,
  Plus,
  Bell,
  User,
  ScanLine,
} from "lucide-react-native";
import { View } from "react-native";
import { useSession } from "../../src/lib/session";
import { State, colors } from "../../src/components/ui";
export default function Layout() {
  const { session, ready } = useSession();
  if (!ready) return <State loading />;
  if (!session) return <Redirect href="/" />;
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.sage,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          position: "absolute",
          bottom: 20,
          left: 16,
          right: 16,
          height: 74,
          paddingBottom: 10,
          paddingTop: 10,
          borderRadius: 26,
          backgroundColor: "white",
          borderTopWidth: 0,
          elevation: 8,
        },
        tabBarLabelStyle: { fontSize: 10, fontWeight: "600" },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Discover",
          tabBarIcon: ({ color }) => <Compass color={color} size={23} />,
        }}
      />
      <Tabs.Screen
        name="map"
        options={{
          title: "Map",
          tabBarIcon: ({ color }) => <MapPin color={color} size={23} />,
        }}
      />
      <Tabs.Screen
        name="report"
        options={{
          title: "Report",
          tabBarIcon: () => (
            <View
              style={{
                backgroundColor: colors.sage,
                padding: 9,
                borderRadius: 16,
                marginTop: -15,
              }}
            >
              <Plus color="white" size={25} />
            </View>
          ),
        }}
      />
      <Tabs.Screen
        name="activity"
        options={{
          title: "Activity",
          tabBarIcon: ({ color }) => <Bell color={color} size={23} />,
        }}
      />
      <Tabs.Screen
        name="scout"
        options={{
          title: "Scout",
          tabBarIcon: ({ color }) => <ScanLine color={color} size={23} />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: "Profile",
          tabBarIcon: ({ color }) => <User color={color} size={23} />,
        }}
      />
    </Tabs>
  );
}
