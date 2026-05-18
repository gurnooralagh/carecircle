import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { usePolling } from '../hooks/usePolling'
import { Button } from './ui/Button'

interface ProcessingScreenProps {
  textVariants: string[]
  onStatusReady: () => void
  pollFn: () => Promise<{ status: string }>
  readyStatus?: string
  failedStatus?: string
}

export function ProcessingScreen({
  textVariants,
  onStatusReady,
  pollFn,
  readyStatus = 'ready',
  failedStatus = 'failed',
}: ProcessingScreenProps) {
  const [textIndex, setTextIndex] = useState(0)
  const [failed, setFailed] = useState(false)

  // Cycle text every 3s
  useEffect(() => {
    const timer = setInterval(() => {
      setTextIndex((i) => (i + 1) % textVariants.length)
    }, 3000)
    return () => clearInterval(timer)
  }, [textVariants.length])

  usePolling({
    pollFn,
    onReady: onStatusReady,
    onFailed: () => setFailed(true),
    readyStatus,
    failedStatus,
    interval: 3000,
    enabled: !failed,
  })

  if (failed) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6 px-4 text-center">
        <div className="w-16 h-16 rounded-full bg-[#FEF2F2] flex items-center justify-center">
          <span className="text-2xl text-severity-critical">!</span>
        </div>
        <div>
          <h2 className="text-xl font-semibold text-text-primary mb-1">
            Something went wrong
          </h2>
          <p className="text-sm text-text-secondary">
            We couldn't complete the analysis. Please try again.
          </p>
        </div>
        <Button onClick={() => window.location.reload()} variant="outline">
          Try again
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-8 px-4">
      {/* Pulsing circle */}
      <div className="relative flex items-center justify-center">
        <motion.div
          className="w-24 h-24 rounded-full bg-[#E6F4F4]"
          animate={{ scale: [1, 1.1, 1] }}
          transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        />
        <motion.div
          className="absolute w-14 h-14 rounded-full bg-accent-primary"
          animate={{ scale: [1, 1.05, 1] }}
          transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut', delay: 0.2 }}
        />
      </div>

      {/* Cycling text */}
      <div className="h-8 flex items-center justify-center">
        <AnimatePresence mode="wait">
          <motion.p
            key={textIndex}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.3 }}
            className="text-base text-text-secondary text-center"
          >
            {textVariants[textIndex]}
          </motion.p>
        </AnimatePresence>
      </div>
    </div>
  )
}
