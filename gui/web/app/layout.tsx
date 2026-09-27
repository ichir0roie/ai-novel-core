import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import Nav from "@/components/Nav";
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
        <MetaProvider>
          <Nav />
          <main>{children}</main>
        </MetaProvider>
      </body>
    </html>
  );
}
