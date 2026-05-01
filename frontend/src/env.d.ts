/// <reference types="astro/client" />

declare namespace App {
  interface Locals {
    accessToken: string
    userEmail: string
  }
}

interface Window {
  __authToken: string
  __getAuthToken: () => Promise<string>
}
