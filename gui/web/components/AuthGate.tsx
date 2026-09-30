"use client";

import { Authenticator, defaultDarkModeOverride, ThemeProvider, type Theme } from "@aws-amplify/ui-react";
import "@aws-amplify/ui-react/styles.css";
import { Amplify } from "aws-amplify";
import type { ReactNode } from "react";
import { amplifyConfig, loginRequired } from "@/lib/auth";

// ssr: トークンをクッキーに置き、`/api/*` の route handler がサーバー側で確かめられるようにする
if (loginRequired) Amplify.configure(amplifyConfig, { ssr: true });

// ボタンとリンクの色を画面の --accent に合わせ、明暗は OS の設定に従う(globals.css と同じ)。
// primary は :root で brand.primary を参照した値に決まってしまうので、brand でなく primary を直に替える
const accent = { 80: "var(--accent)", 90: "var(--accent)", 100: "var(--accent)" };
const theme: Theme = {
  name: "novel",
  tokens: { colors: { primary: accent } },
  overrides: [defaultDarkModeOverride],
};

/** ログインするまで中身(と、中身が読む /api/*)を出さない。使う人は Cognito に直に作るので、登録の画面は隠す */
export default function AuthGate({ children }: { children: ReactNode }) {
  if (!loginRequired) return children;
  return (
    <ThemeProvider theme={theme} colorMode="system">
      <Authenticator hideSignUp>{() => <>{children}</>}</Authenticator>
    </ThemeProvider>
  );
}
