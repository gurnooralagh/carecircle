import React from 'react'
import { Link } from 'react-router-dom'
import { PageTransition } from '../ui/PageTransition'

interface AuthLayoutProps {
  children: React.ReactNode
  title: string
  subtitle?: string
}

export function AuthLayout({ children, title, subtitle }: AuthLayoutProps) {
  return (
    <div className="min-h-screen bg-bg-primary flex flex-col items-center justify-center px-4 py-12">
      <PageTransition className="w-full max-w-md">
        <div className="text-center mb-8">
          <Link to="/" className="inline-block">
            <h1 className="text-2xl font-semibold text-accent-primary" style={{ fontFamily: 'Fraunces, serif' }}>
              CareCircle
            </h1>
          </Link>
        </div>
        <div className="bg-bg-card rounded-2xl shadow-sm border border-border p-8">
          <h2 className="text-2xl font-semibold text-text-primary mb-1" style={{ fontFamily: 'Fraunces, serif' }}>
            {title}
          </h2>
          {subtitle && (
            <p className="text-sm text-text-secondary mb-6">{subtitle}</p>
          )}
          {children}
        </div>
      </PageTransition>
    </div>
  )
}
