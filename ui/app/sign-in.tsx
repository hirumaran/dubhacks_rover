import React, { useState } from "react";
import { Text } from "react-native";
import { Redirect } from "expo-router";
import { Back, Button, Field, Page, s } from "../src/components/ui";
import { check, configured, supabase } from "../src/lib/supabase";
import { useSession } from "../src/lib/session";

export default function SignIn() {
  const { session } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (session) return <Redirect href="/(tabs)" />;
  async function signIn() {
    setBusy(true);
    setError("");
    try {
      if (!configured)
        throw new Error(
          "HuskyFind is missing its server configuration. Contact the project team.",
        );
      check(
        await supabase.auth.signInWithPassword({
          email: email.trim(),
          password,
        }),
      );
      setPassword("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Page>
      <Back />
      <Text style={s.label}>WELCOME TO HUSKYFIND</Text>
      <Text style={s.title}>Your campus. Your account.</Text>
      <Text style={s.body}>
        Sign in with the HuskyFind account provided by your project team. Use a
        separate HuskyFind password here; enter UW NetID passwords only on the
        university’s official sign-in page.
      </Text>
      <Field
        label="Email"
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="email-address"
        textContentType="username"
        autoComplete="email"
      />
      <Field
        label="HuskyFind account password"
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        textContentType="password"
        autoComplete="current-password"
        onSubmitEditing={() => {
          if (email.trim() && password && !busy) void signIn();
        }}
      />
      {!!error && (
        <Text accessibilityRole="alert" style={[s.body, { color: "#9E3B36" }]}>
          {error}
        </Text>
      )}
      <Button
        title={busy ? "Signing in…" : "Sign in"}
        onPress={signIn}
        disabled={busy || !email.trim() || !password}
      />
      <Text style={s.small}>
        Need an account or a password reset? Contact the HuskyFind project team.
      </Text>
    </Page>
  );
}
