import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NEXUS AI TRADER",
  description: "Yapay zeka destekli kripto kağıt işlem terminali"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="tr">
      <body>{children}</body>
    </html>
  );
}
