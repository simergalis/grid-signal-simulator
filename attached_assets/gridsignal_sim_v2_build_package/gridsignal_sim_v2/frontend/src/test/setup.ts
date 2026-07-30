import '@testing-library/jest-dom'

// Recharts uses ResizeObserver (not available in jsdom).
// Provide a no-op mock so ForecastChart mounts without throwing.
global.ResizeObserver = class ResizeObserver {
  observe()   {}
  unobserve() {}
  disconnect() {}
}
