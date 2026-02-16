import type { ReactNode } from "react";

import "@/app/globals.css";

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>): JSX.Element {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
