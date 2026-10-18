import { check, supabase } from "./supabase";
// The OS deep link and browser session can deliver the same PKCE callback.
const exchanges = new Map<string, Promise<void>>();
export function exchangeCode(code: string) {
  const existing = exchanges.get(code);
  if (existing) return existing;
  const promise = supabase.auth.exchangeCodeForSession(code).then((result) => {
    check(result);
  });
  exchanges.set(code, promise);
  return promise;
}
