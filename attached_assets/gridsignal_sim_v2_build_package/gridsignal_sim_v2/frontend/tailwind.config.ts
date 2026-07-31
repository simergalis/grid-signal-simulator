import type { Config } from 'tailwindcss'

export default {
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // GridSignal design language — dark operational palette
        canvas:  '#0d1117',
        surface: '#161b22',
        border:  '#30363d',
        muted:   '#8b949e',
        text:    '#e6edf3',
        accent:  '#58a6ff',
        warn:    '#f0883e',
        danger:  '#f85149',
        ok:      '#3fb950',
        // Mockup colour vocabulary (§4 of UI-IMPLEMENTATION-PLAN)
        teal:     '#3fb6a8',   // confirms readiness, healthy flow, compute
        gold:     '#e0a458',   // gas turbine / generation
        solar:    '#f2c94c',   // solar / yellow
        battery:  '#4a9fe0',   // battery, cooling
        violet:   '#9b8ce0',   // optimisation agents
        islanded: '#5a6673',   // inactive / not connected / grey
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config
