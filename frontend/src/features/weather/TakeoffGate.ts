import { createContext, useContext } from 'react'

/**
 * True while a rain warning suspends NEW takeoffs (Feature 020). Controls that would start a
 * flight read it to explain why they are off; the backend refuses the takeoff either way.
 */
const TakeoffsSuspendedContext = createContext(false)

export const TakeoffsSuspendedProvider = TakeoffsSuspendedContext.Provider

export const useTakeoffsSuspended = () => useContext(TakeoffsSuspendedContext)

export const TAKEOFFS_SUSPENDED_REASON =
  'Rain warning: new takeoffs are suspended until the warning is cleared.'
