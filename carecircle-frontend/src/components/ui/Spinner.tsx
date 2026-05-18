interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  color?: 'teal' | 'white' | 'gray'
}

export function Spinner({ size = 'md', color = 'teal' }: SpinnerProps) {
  const sizes = { sm: 'w-4 h-4', md: 'w-6 h-6', lg: 'w-8 h-8' }
  const colors = {
    teal: 'border-accent-primary border-t-transparent',
    white: 'border-white border-t-transparent',
    gray: 'border-text-muted border-t-transparent',
  }
  return (
    <div
      role="status"
      aria-label="Loading"
      className={`${sizes[size]} rounded-full border-2 animate-spin ${colors[color]}`}
    />
  )
}
