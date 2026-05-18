import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Link } from 'react-router-dom'
import { CheckCircle } from 'lucide-react'
import { AuthLayout } from '../components/layout/AuthLayout'
import { Input } from '../components/ui/Input'
import { Button } from '../components/ui/Button'
import { supabase } from '../lib/supabase'

const schema = z.object({
  email: z.string().email('Enter a valid email'),
})

type FormData = z.infer<typeof schema>

export function ForgotPassword() {
  const [sent, setSent] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) })

  const [submitError, setSubmitError] = useState<string | null>(null)

  const onSubmit = async (data: FormData) => {
    setSubmitError(null)
    const { error } = await supabase.auth.resetPasswordForEmail(data.email, {
      redirectTo: `${window.location.origin}/reset-password`,
    })
    if (error) {
      setSubmitError(error.message)
      return
    }
    setSent(true)
  }

  if (sent) {
    return (
      <AuthLayout title="Check your email">
        <div className="flex flex-col items-center gap-4 py-6 text-center">
          <div className="w-12 h-12 rounded-full bg-[#F0FDF4] flex items-center justify-center">
            <CheckCircle className="w-6 h-6 text-[#16A34A]" />
          </div>
          <p className="text-sm text-text-secondary">
            If an account exists for that email, we've sent a password reset link.
          </p>
          <Link
            to="/login"
            className="text-sm text-accent-primary hover:underline font-medium"
          >
            Back to login
          </Link>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title="Forgot password?"
      subtitle="We'll send you a link to reset it"
    >
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4 mt-6">
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          error={errors.email?.message}
          {...register('email')}
        />
        {submitError && (
          <p className="text-sm text-severity-critical bg-[#FEF2F2] px-3 py-2 rounded-lg">
            {submitError}
          </p>
        )}
        <Button type="submit" fullWidth loading={isSubmitting} className="mt-2">
          Send reset link
        </Button>
      </form>
      <p className="text-sm text-text-secondary text-center mt-4">
        Remembered it?{' '}
        <Link to="/login" className="text-accent-primary hover:underline font-medium">
          Back to login
        </Link>
      </p>
    </AuthLayout>
  )
}
