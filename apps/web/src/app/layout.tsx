import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { AppProvider } from "@/components/app-context";
import { AppShell } from "@/components/app-shell";
import { THEME_BOOTSTRAP } from "@/lib/theme";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "ML Forge", template: "%s · ML Forge" },
  description: "Local learning platform for ML engineering",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0c0f13" },
    { media: "(prefers-color-scheme: light)", color: "#f6f7f9" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
      </head>
      <body>
        <AppProvider>
          <AppShell>{children}</AppShell>
        </AppProvider>
      </body>
    </html>
  );
}
