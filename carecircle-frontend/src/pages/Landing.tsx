import { Link } from 'react-router-dom'
import { Upload, Cpu, CheckCircle, ArrowRight } from 'lucide-react'
import { motion } from 'framer-motion'

const HOW_IT_WORKS = [
  {
    icon: Upload,
    title: 'Upload documents',
    description:
      "Upload prescriptions, lab reports, or discharge summaries for your loved one.",
  },
  {
    icon: Cpu,
    title: 'We analyse everything',
    description:
      'Our AI reads every document, checks for drug interactions, and identifies what needs attention.',
  },
  {
    icon: CheckCircle,
    title: 'You get clear answers',
    description:
      'No jargon. Just clear explanations of what matters and exactly what to do next.',
  },
]

export function Landing() {
  return (
    <div className="min-h-screen bg-bg-primary flex flex-col">
      {/* Top nav */}
      <nav className="px-6 py-4 flex items-center justify-between max-w-5xl mx-auto w-full">
        <span
          className="text-xl font-semibold text-accent-primary"
          style={{ fontFamily: 'Fraunces, serif' }}
        >
          CareCircle
        </span>
        <div className="flex gap-3">
          <Link
            to="/login"
            className="text-sm font-medium text-text-secondary hover:text-text-primary transition-colors px-4 h-10 flex items-center"
          >
            Log in
          </Link>
          <Link
            to="/signup"
            className="text-sm font-medium text-white bg-accent-primary hover:bg-[#0A5858] transition-colors px-4 h-10 flex items-center rounded-xl"
          >
            Get started
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="flex-1 flex flex-col items-center justify-center text-center px-6 pt-16 pb-24 max-w-3xl mx-auto w-full">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <h1
            className="text-4xl sm:text-5xl md:text-6xl font-normal text-text-primary leading-tight mb-6"
            style={{ fontFamily: 'Fraunces, serif' }}
          >
            Know what your loved one's health{' '}
            <span className="text-accent-primary italic">means.</span>
          </h1>
          <p className="text-lg text-text-secondary max-w-xl mx-auto mb-10">
            Upload prescriptions and medical reports. CareCircle analyses everything and
            explains what matters — in plain language, not medical jargon.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              to="/signup"
              className="inline-flex items-center justify-center gap-2 h-12 px-6 rounded-xl bg-accent-primary text-white text-base font-medium hover:bg-[#0A5858] transition-colors"
            >
              Get started free
              <ArrowRight className="w-4 h-4" />
            </Link>
            <a
              href="#how-it-works"
              className="inline-flex items-center justify-center h-12 px-6 rounded-xl border border-border text-base font-medium text-text-primary hover:bg-bg-secondary transition-colors"
            >
              See how it works
            </a>
          </div>
        </motion.div>
      </section>

      {/* How it works */}
      <section
        id="how-it-works"
        className="py-20 px-6 bg-bg-secondary"
      >
        <div className="max-w-4xl mx-auto">
          <h2
            className="text-3xl font-normal text-text-primary text-center mb-12"
            style={{ fontFamily: 'Fraunces, serif' }}
          >
            How it works
          </h2>
          <div className="grid sm:grid-cols-3 gap-6">
            {HOW_IT_WORKS.map((step, i) => (
              <motion.div
                key={step.title}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1, duration: 0.4 }}
                className="bg-bg-card rounded-xl border border-border p-6 shadow-sm"
              >
                <div className="w-11 h-11 rounded-xl bg-[#E6F4F4] flex items-center justify-center mb-4">
                  <step.icon className="w-5 h-5 text-accent-primary" />
                </div>
                <h3 className="text-lg font-semibold text-text-primary mb-2">{step.title}</h3>
                <p className="text-sm text-text-secondary leading-relaxed">{step.description}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA footer */}
      <section className="py-20 px-6 text-center bg-bg-primary">
        <div className="max-w-xl mx-auto">
          <h2
            className="text-3xl font-normal text-text-primary mb-4"
            style={{ fontFamily: 'Fraunces, serif' }}
          >
            Your loved ones deserve better care.
          </h2>
          <p className="text-base text-text-secondary mb-8">
            Join families who use CareCircle to stay on top of their loved one's health.
          </p>
          <Link
            to="/signup"
            className="inline-flex items-center justify-center gap-2 h-12 px-8 rounded-xl bg-accent-primary text-white text-base font-medium hover:bg-[#0A5858] transition-colors"
          >
            Start for free
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </section>
    </div>
  )
}
