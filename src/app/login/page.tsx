"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { useMusic } from "@/context/MusicContext";
import { LoginView } from "@/components/views/LoginView";

export default function LoginPage() {
  const router = useRouter();
  const { currentUser } = useMusic();

  return (
    <LoginView
      currentUser={currentUser}
      onNavigate={(route) => router.push(route)}
    />
  );
}
