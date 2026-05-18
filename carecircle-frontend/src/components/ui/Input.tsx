import React from 'react'

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string
  error?: string
  hint?: string
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, id, className = '', ...props }, ref) => {
    const inputId = id ?? label.toLowerCase().replace(/\s+/g, '-')

    return (
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor={inputId}
          className="text-sm font-medium text-text-primary"
        >
          {label}
        </label>
        <input
          ref={ref}
          id={inputId}
          {...props}
          className={`h-11 px-3 rounded-xl border bg-bg-card text-text-primary placeholder:text-text-muted text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent ${
            error ? 'border-severity-critical' : 'border-border'
          } ${className}`}
        />
        {error && (
          <p className="text-sm text-severity-critical" role="alert">
            {error}
          </p>
        )}
        {hint && !error && (
          <p className="text-sm text-text-muted">{hint}</p>
        )}
      </div>
    )
  }
)

Input.displayName = 'Input'
