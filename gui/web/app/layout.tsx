import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import Nav from "@/components/Nav";
import { MetaProvider } from "@/lib/meta";

export const metadata: Metadata = {
  title: "novel db",
  description: "ai-novel-core のデータ編集 GUI",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ja">
      <body>
        <MetaProvider>
          <Nav />
          <main>{children}</main>
        </MetaProvider>
      </body>
    </html>
  );
}
