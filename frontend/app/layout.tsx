import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "ERP Master Data Prep",
  description: "AI-driven master data preparation for ERP schema mapping",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-border bg-white/80 backdrop-blur px-6 py-3 sticky top-0 z-10">
          <div className="container flex items-center justify-between">
            <span className="font-semibold text-sm tracking-tight">ERP Master Data Prep</span>
            <nav className="flex gap-5 text-sm">
              <a href="/" className="text-muted-foreground hover:text-foreground transition-colors">Upload</a>
              <a href="/masters" className="text-muted-foreground hover:text-foreground transition-colors">All files</a>
              <a href="/activity" className="text-muted-foreground hover:text-foreground transition-colors">Activity Log</a>
            </nav>
          </div>
        </header>
        <main className="container max-w-7xl py-8">{children}</main>
      </body>
    </html>
  );
}
