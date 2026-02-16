"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";

import { AuthScreen } from "@/components/auth-screen";
import { createBrowserClientBundle } from "@/lib/browser-client";

export default function LoginPage(): JSX.Element {
  const router = useRouter();
  const bundle = useMemo(() => createBrowserClientBundle(), []);

  return (
    <AuthScreen
      mode="login"
      client={bundle.client}
      onAuthenticated={() => {
        router.push("/dashboard");
      }}
    />
  );
}
