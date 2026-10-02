import type { Metadata } from "next";
import { Suspense, type ReactNode } from "react";
import "./globals.css";
import AuthGate from "@/components/AuthGate";
import Nav from "@/components/Nav";
import ResumeLastPage from "@/components/ResumeLastPage";
import { MetaProvider } from "@/lib/meta";
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
          <MetaProvider>
            <Nav />
            <Suspense>
              <ResumeLastPage />
            </Suspense>
            {/* 画面は useSearchParams を読むので、next build の静的な書き出しでは読めるまで待つ境界が要る */}
            <main>
              <Suspense>{children}</Suspense>
            </main>
          </MetaProvider>
        </AuthGate>
      </body>
    </html>
  );
}
