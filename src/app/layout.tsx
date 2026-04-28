import type { Metadata } from "next";
import "./globals.css";
import { AppProvider } from "@/lib/AppContext";
import Shell from "@/components/Shell";

export const metadata: Metadata = {
  title: "PLAMA v2.0 — Persistent Local AI Memory Adapter",
  description: "ローカルLLMのための永続メモリ・ルーティング・バイアス評価環境",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body>
        <AppProvider>
          <Shell>{children}</Shell>
        </AppProvider>
      </body>
    </html>
  );
}
