/// <reference types="astro/client" />

declare namespace App {
  interface Locals {
    accessToken: string
    userEmail: string
    lang: string
    sessionToken: string
  }
}

interface Window {
  __authToken: string
  __sessionToken: string
  __getAuthToken: () => Promise<string>
}
