import '../globals.css'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'CarbonPilot - Knowledge-Enhanced Construction Embodied Carbon Quantification Platform',
  description: 'Knowledge-Enhanced Construction Embodied Carbon Quantification Platform',
  icons: {
    icon: '/favicon.svg', // Path to the SVG favicon in the public directory
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="h-full bg-gray-50">
      <body className="h-full">
        {children}
      </body>
    </html>
  )
}