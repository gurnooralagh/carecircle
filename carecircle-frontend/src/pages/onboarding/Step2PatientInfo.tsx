import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Input } from '../../components/ui/Input'
import { Button } from '../../components/ui/Button'
import type { PatientFormData } from './OnboardingLayout'

const GENDERS = ['Male', 'Female', 'Other'] as const

const schema = z.object({
  full_name: z.string().min(2, 'Full name is required'),
  date_of_birth: z.string().min(1, 'Date of birth is required'),
  weight_kg: z.string().optional(),
  height_cm: z.string().optional(),
  city: z.string().optional(),
  state: z.string().optional(),
})

type FormData = z.infer<typeof schema>

interface Step2PatientInfoProps {
  onNext: (data: PatientFormData) => void
}

export function Step2PatientInfo({ onNext }: Step2PatientInfoProps) {
  const [gender, setGender] = useState<'Male' | 'Female' | 'Other'>('Male')

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormData>({ resolver: zodResolver(schema) })

  const onSubmit = (data: FormData) => {
    onNext({
      full_name: data.full_name,
      date_of_birth: data.date_of_birth,
      gender,
      weight_kg: data.weight_kg ? parseFloat(data.weight_kg) : undefined,
      height_cm: data.height_cm ? parseFloat(data.height_cm) : undefined,
      city: data.city || undefined,
      state: data.state || undefined,
    })
  }

  return (
    <div className="pt-4">
      <h2
        className="text-2xl font-normal text-text-primary mb-1"
        style={{ fontFamily: 'Fraunces, serif' }}
      >
        Tell us about your loved one
      </h2>
      <p className="text-sm text-text-secondary mb-8">
        This helps us personalise the analysis.
      </p>

      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-5">
        <Input
          label="Full name"
          type="text"
          placeholder="e.g. Rajesh Sharma"
          error={errors.full_name?.message}
          {...register('full_name')}
        />
        <Input
          label="Date of birth"
          type="date"
          error={errors.date_of_birth?.message}
          {...register('date_of_birth')}
        />

        {/* Gender pill selector */}
        <div>
          <p className="text-sm font-medium text-text-primary mb-2">Gender</p>
          <div className="flex gap-2">
            {GENDERS.map((g) => (
              <button
                key={g}
                type="button"
                onClick={() => setGender(g)}
                className={`flex-1 h-10 rounded-xl border text-sm font-medium transition-colors cursor-pointer ${
                  gender === g
                    ? 'bg-accent-primary border-accent-primary text-white'
                    : 'border-border text-text-secondary hover:border-accent-primary hover:text-accent-primary'
                }`}
              >
                {g}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Weight (kg) — optional"
            type="number"
            placeholder="e.g. 72"
            error={errors.weight_kg?.message}
            {...register('weight_kg')}
          />
          <Input
            label="Height (cm) — optional"
            type="number"
            placeholder="e.g. 168"
            error={errors.height_cm?.message}
            {...register('height_cm')}
          />
        </div>

        <Input
          label="City — optional"
          type="text"
          placeholder="e.g. Jaipur"
          error={errors.city?.message}
          {...register('city')}
        />

        <Input
          label="State — optional"
          type="text"
          placeholder="e.g. Rajasthan"
          error={errors.state?.message}
          {...register('state')}
        />

        <Button type="submit" fullWidth size="lg" className="mt-2">
          Continue
        </Button>
      </form>
    </div>
  )
}
