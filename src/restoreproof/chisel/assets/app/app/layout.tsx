/* eslint-disable @next/next/no-page-custom-font -- App Router root layout loads these fonts for every route. */
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Chisel — Feature briefs for product and engineering",
  description:
    "Turn product notes into editable feature briefs with scope, user stories, acceptance criteria, and open questions. Review, save, and export your draft.",
  keywords: [
    "PRD generator",
    "AI product spec",
    "product requirements document",
    "user stories generator",
    "API spec generator",
    "founder tools",
    "Claude AI",
    "sprint planning",
  ],
  authors: [{ name: "Atharva Bagul" }],
  openGraph: {
    title: "Chisel — Feature briefs for product and engineering",
    description:
      "Define the problem, agree on scope, and keep open questions visible before engineering starts building.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <head>
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap"
        />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Geist:wght@100..900&family=Geist+Mono:wght@100..900&display=swap"
        />
      </head>
      <body className="bg-background font-body text-on-surface antialiased selection:bg-primary-container selection:text-on-primary-container">
        {children}
      </body>
    </html>
  );
}
