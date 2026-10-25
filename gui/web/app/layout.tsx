import type { Metadata } from "next";
import { Suspense, type ReactNode } from "react";
import "./globals.css";
import ApiWarmUp from "@/components/ApiWarmUp";
import AuthGate from "@/components/AuthGate";
import HintLayer from "@/components/Hint";
import Nav from "@/components/Nav";
import SavingOverlay from "@/components/SavingOverlay";
import { T } from "@/lib/text";

export const metadata: Metadata = {
  title: T.appName,
  description: T.appDescription,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ja">
      <body>
        <AuthGate>
          <Nav />
          {/* 画面は useSearchParams を読むので、next build の静的な書き出しでは読めるまで待つ境界が要る */}
          <main>
            <Suspense>{children}</Suspense>
          </main>
          <HintLayer />
          <SavingOverlay />
          <ApiWarmUp />
        </AuthGate>
      </body>
    </html>
  );
}
