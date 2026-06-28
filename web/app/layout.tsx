import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Nav } from "@/components/Nav";

export const metadata: Metadata = {
  title: "AI Trainer",
  description: "Персональный тренировочный кокпит",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru">
      <body>
        <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8">
          <Nav />
          {children}
        </div>
      </body>
    </html>
  );
}
