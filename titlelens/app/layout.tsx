import type { Metadata, Viewport } from 'next'
import { Sora, IBM_Plex_Mono, DM_Serif_Display } from 'next/font/google'
import { Toaster } from 'sonner'
import './globals.css'

const sora = Sora({
  subsets: ['latin'],
  variable: '--font-sora',
})

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-ibm-plex-mono',
})

const dmSerifDisplay = DM_Serif_Display({
  subsets: ['latin'],
  weight: '400',
  variable: '--font-dm-serif-display',
})

export const metadata: Metadata = {
  title: 'Deedly — Buyer Confidence Platform',
  description: 'Risk isn\'t a property. It\'s a network. Deedly maps real estate risk by analyzing relationships, patterns, and signals hiding around every address.',
}

export const viewport: Viewport = {
  themeColor: '#050A30',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className={`${sora.variable} ${ibmPlexMono.variable} ${dmSerifDisplay.variable}`}>
      <body className="font-sans antialiased bg-background text-foreground" suppressHydrationWarning>
        {children}
        <Toaster
          theme="dark"
          toastOptions={{
            style: {
              background: 'var(--card)',
              border: '1px solid var(--border)',
              color: 'var(--foreground)',
            },
          }}
        />
      </body>
    </html>
  )
}
