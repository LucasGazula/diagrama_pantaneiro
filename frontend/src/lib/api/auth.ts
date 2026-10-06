import type { JwtLoginResponse, UserRead } from "$lib/types/api";

import { apiRequest, ApiError } from "./client";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export async function register(email: string, password: string): Promise<UserRead> {
  return apiRequest<UserRead>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function login(email: string, password: string): Promise<JwtLoginResponse> {
  const body = new URLSearchParams({ username: email, password }).toString();
  const response = await fetch(`${BASE_URL}/api/auth/jwt/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) {
    throw new ApiError(response.status, "login failed");
  }
  return (await response.json()) as JwtLoginResponse;
}

export async function getCurrentUser(): Promise<UserRead> {
  return apiRequest<UserRead>("/users/me");
}

export async function logout(): Promise<void> {
  await apiRequest<void>("/auth/jwt/logout", { method: "POST" });
}
