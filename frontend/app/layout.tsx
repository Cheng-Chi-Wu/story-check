import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, IBM_Plex_Sans_Condensed } from "next/font/google";
import "./globals.css";

const sans = IBM_Plex_Sans({ variable: "--font-plex-sans", subsets: ["latin"], weight: ["400", "500", "600"] });
const condensed = IBM_Plex_Sans_Condensed({
  variable: "--font-plex-condensed",
  subsets: ["latin"],
  weight: ["500", "600"],
});
const mono = IBM_Plex_Mono({ variable: "--font-plex-mono", subsets: ["latin"], weight: ["400", "500"] });

export const metadata: Metadata = {
  title: "Story Check - ASCE 7-22 irregularity and drift review",
  description: "Check ETABS results for torsional irregularity, soft stories and story drift under ASCE 7-22 Chapter 12.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${sans.variable} ${condensed.variable} ${mono.variable} h-full antialiased`}>
      <body className="min-h-full">{children}</body>
    </html>
  );
}
