import React from 'react'

interface CardProps {
  children: React.ReactNode
  className?: string
  onClick?: () => void
  padding?: 'sm' | 'md' | 'lg'
}

export function Card({ children, className = '', onClick, padding = 'md' }: CardProps) {
  const pads = { sm: 'p-4', md: 'p-6', lg: 'p-8' }
  return (
    <div
      onClick={onClick}
      className={`bg-bg-card rounded-xl shadow-sm border border-border ${pads[padding]} ${onClick ? 'cursor-pointer' : ''} ${className}`}
    >
      {children}
    </div>
  )
}
