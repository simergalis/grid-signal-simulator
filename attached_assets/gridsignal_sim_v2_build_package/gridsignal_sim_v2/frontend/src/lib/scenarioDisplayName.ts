const SCENARIO_DISPLAY_NAMES: Record<string, string> = {
  'proxim8-5mw-24h-queue': 'Proxim8 with queue-stress',
}

export function getScenarioDisplayName(scenarioId: string, fallbackName: string): string {
  return SCENARIO_DISPLAY_NAMES[scenarioId] ?? fallbackName
}
