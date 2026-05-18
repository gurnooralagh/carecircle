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
import { useToast } from '../store/toast'

const schema = z
  .object({
    full_name: z.string().min(2, 'Full name is required'),
    email: z.string().email('Enter a valid email'),
    password: z.string().min(8, 'Password must be at least 8 characters'),
    confirm_password: z.string(),
  })
  .refine((d) => d.password === d.confirm_password, {
    message: 'Passwords do not match',
    path: ['confirm_password'],
  })

type FormData = z.infer<typeof schema>

export function Signup() {
  const navigate = useNavigate()
  const { login } = useAuthStore()
  const toast = useToast()

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) })

  const onSubmit = async (data: FormData) => {
    try {
      const { data: authData, error } = await supabase.auth.signUp({
        email: data.email,
        password: data.password,
        options: {
          data: { full_name: data.full_name },
        },
      })
      if (error) throw error

      if (authData.session) {
        // Email confirmation is off — session returned immediately
        login(authData.session.access_token, authData.user?.id ?? '')
        try {
          await api.post('/api/auth/set-role', {
            role: 'guardian',
            full_name: data.full_name,
            email: data.email,
          })
        } catch { /* non-blocking */ }
        navigate('/onboarding')
      } else {
        // Email confirmation is on — show check-your-email screen
        navigate('/check-email', { state: { email: data.email, full_name: data.full_name } })
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Signup failed. Please try again.'
      toast.error(msg)
    }
  }

  return (
    <AuthLayout title="Create your account" subtitle="Start caring smarter for your family">
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4 mt-6">
        <Input
          label="Full name"
          type="text"
          autoComplete="name"
          placeholder="Jane Smith"
          error={errors.full_name?.message}
          {...register('full_name')}
        />
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          error={errors.email?.message}
          {...register('email')}
        />
        <Input
          label="Password"
          type="password"
          autoComplete="new-password"
          placeholder="At least 8 characters"
          error={errors.password?.message}
          {...register('password')}
        />
        <Input
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          placeholder="Repeat password"
          error={errors.confirm_password?.message}
          {...register('confirm_password')}
        />
        <Button type="submit" fullWidth loading={isSubmitting} className="mt-2">
          Create account
        </Button>
      </form>
      <p className="text-sm text-text-secondary text-center mt-4">
        Already have an account?{' '}
        <Link to="/login" className="text-accent-primary hover:underline font-medium">
          Log in
        </Link>
      </p>
    </AuthLayout>
  )
}
