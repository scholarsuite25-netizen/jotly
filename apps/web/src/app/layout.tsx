import type { Metadata } from "next";
import "../styles.css";

export const metadata: Metadata = {
  title: "Jotly — NEXUS Meeting Intelligence",
  description:
    "Every Conversation Becomes Knowledge. Every Document Finds Its Voice.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
