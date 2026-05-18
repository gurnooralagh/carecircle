import React from 'react'
import { Spinner } from './Spinner'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  fullWidth?: boolean
  children: React.ReactNode
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  fullWidth = false,
  children,
  disabled,
  className = '',
  ...props
}: ButtonProps) {
  const base =
    'inline-flex items-center justify-center gap-2 font-medium rounded-xl transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed select-none'

  const variants: Record<string, string> = {
    primary:
      'bg-accent-primary text-white hover:bg-[#0A5858] focus:ring-accent-primary',
    secondary:
      'bg-bg-secondary text-text-primary hover:bg-border focus:ring-border',
    outline:
      'border border-border text-text-primary bg-transparent hover:bg-bg-secondary focus:ring-border',
    ghost: 'text-text-secondary hover:bg-bg-secondary focus:ring-border',
    danger:
      'bg-severity-critical text-white hover:bg-red-700 focus:ring-red-500',
  }

  const sizes: Record<string, string> = {
    sm: 'text-sm px-3 h-9',
    md: 'text-sm px-4 h-11',
    lg: 'text-base px-6 h-12',
  }

  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={`${base} ${variants[variant]} ${sizes[size]} ${fullWidth ? 'w-full' : ''} ${className}`}
    >
      {loading && <Spinner size="sm" color={variant === 'primary' ? 'white' : 'teal'} />}
      {children}
    </button>
  )
}
