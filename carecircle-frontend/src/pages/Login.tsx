import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Link, useNavigate } from 'react-router-dom'
import { AuthLayout } from '../components/layout/AuthLayout'
import { Input } from '../components/ui/Input'
import { Button } from '../components/ui/Button'
import { supabase } from '../lib/supabase'
import api from '../lib/api'
import { useAuthStore } from '../store/auth'
import { usePatientStore } from '../store/patient'
import { useToast } from '../store/toast'

const schema = z.object({
  email: z.string().email('Enter a valid email'),
  password: z.string().min(1, 'Password is required'),
})

type FormData = z.infer<typeof schema>

export function Login() {
  const navigate = useNavigate()
  const { login } = useAuthStore()
  const { patient_id, onboarding_complete } = usePatientStore()
  const toast = useToast()

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) })

  const onSubmit = async (data: FormData) => {
    try {
      const { data: authData, error } = await supabase.auth.signInWithPassword({
        email: data.email,
        password: data.password,
      })
      if (error) throw error

      const token = authData.session?.access_token ?? ''
      const userId = authData.user?.id ?? ''
      login(token, userId)

      // Ensure user_profile exists (covers users who signed up with email confirmation)
      try {
        const fullName = authData.user?.user_metadata?.full_name ?? ''
        await api.post('/api/auth/set-role', {
          role: 'guardian',
          full_name: fullName,
          email: data.email,
        })
      } catch { /* already exists or non-blocking */ }

      // Redirect based on onboarding state in localStorage
      if (patient_id && onboarding_complete) {
        navigate('/dashboard')
      } else {
        navigate('/onboarding')
      }
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Login failed. Please check your credentials.'
      toast.error(msg)
    }
  }

  return (
    <AuthLayout title="Welcome back" subtitle="Sign in to your CareCircle account">
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4 mt-6">
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          error={errors.email?.message}
          {...register('email')}
        />
        <div>
          <Input
            label="Password"
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            error={errors.password?.message}
            {...register('password')}
          />
          <Link
            to="/forgot-password"
            className="text-xs text-accent-primary hover:underline mt-1 inline-block"
          >
            Forgot password?
          </Link>
        </div>
        <Button type="submit" fullWidth loading={isSubmitting} className="mt-2">
          Log in
        </Button>
      </form>
      <p className="text-sm text-text-secondary text-center mt-4">
        Don't have an account?{' '}
        <Link to="/signup" className="text-accent-primary hover:underline font-medium">
          Sign up
        </Link>
      </p>
    </AuthLayout>
  )
}
