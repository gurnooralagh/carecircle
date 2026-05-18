import { useState, useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useNavigate } from 'react-router-dom'
import { AuthLayout } from '../components/layout/AuthLayout'
import { Input } from '../components/ui/Input'
import { Button } from '../components/ui/Button'
import { supabase } from '../lib/supabase'
import { useToast } from '../store/toast'

const schema = z
  .object({
    password: z.string().min(8, 'Password must be at least 8 characters'),
    confirm_password: z.string(),
  })
  .refine((d) => d.password === d.confirm_password, {
    message: 'Passwords do not match',
    path: ['confirm_password'],
  })

type FormData = z.infer<typeof schema>

export function ResetPassword() {
  const navigate = useNavigate()
  const toast = useToast()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    // Check if Supabase already processed the recovery token before this component mounted
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) setReady(true)
    })

    const { data: { subscription } } = supabase.auth.onAuthStateChange((event) => {
      if (event === 'PASSWORD_RECOVERY' || event === 'SIGNED_IN') {
        setReady(true)
      }
    })
    return () => subscription.unsubscribe()
  }, [])

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) })

  const onSubmit = async (data: FormData) => {
    const { error } = await supabase.auth.updateUser({ password: data.password })
    if (error) {
      toast.error(error.message)
      return
    }
    // Sign out so the user logs in fresh with their new password
    await supabase.auth.signOut()
    toast.success('Password updated. Please log in with your new password.')
    navigate('/login')
  }

  if (!ready) {
    return (
      <AuthLayout title="Reset your password">
        <div className="py-6 text-center">
          <p className="text-sm text-text-secondary">
            Waiting for verification… If you arrived here from a reset email, please wait a moment.
          </p>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout title="Set a new password">
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4 mt-6">
        <Input
          label="New password"
          type="password"
          autoComplete="new-password"
          placeholder="At least 8 characters"
          error={errors.password?.message}
          {...register('password')}
        />
        <Input
          label="Confirm new password"
          type="password"
          autoComplete="new-password"
          placeholder="Repeat new password"
          error={errors.confirm_password?.message}
          {...register('confirm_password')}
        />
        <Button type="submit" fullWidth loading={isSubmitting} className="mt-2">
          Update password
        </Button>
      </form>
    </AuthLayout>
  )
}
