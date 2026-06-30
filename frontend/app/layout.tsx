import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Medical Cohort AI",
  description: "Chat-based cohort analysis workspace",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
