import React, { useEffect, useState } from "react";
import { Alert as NativeAlert, AlertButton, Modal, Platform, Pressable, ScrollView, Text, View } from "react-native";

type Dialog = { title: string; message?: string; buttons: AlertButton[] };
let show: ((value: Dialog) => void) | undefined;
export const Alert = {
  alert(title: string, message?: string, buttons?: AlertButton[]) {
    if (Platform.OS !== "web") return NativeAlert.alert(title, message, buttons);
    show?.({ title, message, buttons: buttons?.length ? buttons : [{ text: "OK" }] });
  },
};

export function DialogHost() {
  const [dialog, setDialog] = useState<Dialog | null>(null);
  useEffect(() => { show = setDialog; return () => { show = undefined; }; }, []);
  if (Platform.OS !== "web" || !dialog) return null;
  return <Modal transparent visible animationType="fade" onRequestClose={() => setDialog(null)}>
    <View style={{ flex: 1, backgroundColor: "rgba(37,27,54,0.5)", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <View accessibilityViewIsModal style={{ width: "100%", maxWidth: 440, maxHeight: "85%", borderRadius: 24, padding: 26, backgroundColor: "#FAF8FC", gap: 18 }}>
        <Text accessibilityRole="header" style={{ fontSize: 23, fontWeight: "700", color: "#251B36" }}>{dialog.title}</Text>
        <ScrollView><Text selectable style={{ fontSize: 16, lineHeight: 24, color: "#71677D" }}>{dialog.message}</Text></ScrollView>
        {dialog.buttons.map((button, index) => <Pressable key={index} accessibilityRole="button" accessibilityLabel={button.text || "OK"} onPress={() => { setDialog(null); button.onPress?.(); }} style={{ minHeight: 48, padding: 15, borderRadius: 16, alignItems: "center", backgroundColor: button.style === "cancel" ? "#EEE8F5" : button.style === "destructive" ? "#993C4B" : "#4B2E83" }}>
          <Text style={{ fontWeight: "700", color: button.style === "cancel" ? "#4B2E83" : "white" }}>{button.text || "OK"}</Text>
        </Pressable>)}
      </View>
    </View>
  </Modal>;
}
