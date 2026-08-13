/**
 * LocationPicker.tsx — Data-centre location selector with autocomplete.
 *
 * Designed to live inside the VerdictBand as a prominent center column.
 *
 * Behaviour
 * ---------
 * • Display mode: shows "📍 City, Region" + UTC offset with a small "change" link.
 * • Edit mode: text input with an instant-filter dropdown of known locations.
 *   Suggestions match on city name, US state, country name, and ZIP-code prefix.
 *   The user can also type a ZIP code (e.g. "90210") and the dropdown shows the
 *   matching city.
 * • On submit the input is sent to PUT /api/location for geocoding via Mistral.
 *   The endpoint accepts any valid city / state / country / ZIP string and returns
 *   a 422 for unrecognisable addresses.
 * • The onLocationChanged callback fires after a successful change so the parent
 *   can refresh the solar-preview badge.
 */

import { useState, useEffect, useRef, useCallback } from 'react'

// ---------------------------------------------------------------------------
// Location model
// ---------------------------------------------------------------------------

interface Location {
  name:                 string
  lat:                  number
  lon:                  number
  utc_offset_h:         number   // standard-time offset (never changes)
  current_utc_offset_h: number   // DST-aware live offset — use this for display/clocks
  climate_hint:         string
  ambient_temp_base_c:  number
}

export interface LocationPickerProps {
  onLocationChanged?: (loc: Location) => void
}

// ---------------------------------------------------------------------------
// Suggestion catalogue — curated list for instant client-side autocomplete.
// Each entry: [display name, UTC standard offset, zip codes / area codes (optional)]
// ---------------------------------------------------------------------------

interface SuggestionEntry {
  name: string
  utc:  number
  tz?:  string     // IANA timezone identifier for DST-aware offset computation
  tags: string[]   // additional search tokens (state abbrev, country, zip prefix)
}

const SUGGESTIONS: SuggestionEntry[] = [
  // Default site
  { name: 'SV1 - Silicon Valley, California', utc: -8, tz: 'America/Los_Angeles',          tags: ['sv1', 'silicon valley', 'san jose', 'santa clara', 'ca', 'us', 'usa', '950', '951', '954', '955'] },
  // United States
  { name: 'New York, NY',        utc: -5,   tz: 'America/New_York',                        tags: ['ny', 'us', 'usa', '100', '101', '102', '103', '104'] },
  { name: 'Los Angeles, CA',     utc: -8,   tz: 'America/Los_Angeles',                     tags: ['la', 'ca', 'us', 'usa', '900', '901', '902', '903'] },
  { name: 'Chicago, IL',         utc: -6,   tz: 'America/Chicago',                         tags: ['il', 'us', 'usa', '606', '607', '608'] },
  { name: 'Houston, TX',         utc: -6,   tz: 'America/Chicago',                         tags: ['tx', 'us', 'usa', '770', '771', '772'] },
  { name: 'Phoenix, AZ',         utc: -7,   tz: 'America/Phoenix',                         tags: ['az', 'us', 'usa', '850', '851', '852', '853'] },
  { name: 'Philadelphia, PA',    utc: -5,   tz: 'America/New_York',                        tags: ['pa', 'us', 'usa', '190', '191', '192'] },
  { name: 'San Antonio, TX',     utc: -6,   tz: 'America/Chicago',                         tags: ['tx', 'us', 'usa', '782', '783'] },
  { name: 'San Diego, CA',       utc: -8,   tz: 'America/Los_Angeles',                     tags: ['ca', 'us', 'usa', '919', '920', '921', '922'] },
  { name: 'Dallas, TX',          utc: -6,   tz: 'America/Chicago',                         tags: ['tx', 'us', 'usa', '752', '753', '754'] },
  { name: 'San Jose, CA',        utc: -8,   tz: 'America/Los_Angeles',                     tags: ['ca', 'us', 'usa', '950', '951'] },
  { name: 'Austin, TX',          utc: -6,   tz: 'America/Chicago',                         tags: ['tx', 'us', 'usa', '787', '788'] },
  { name: 'San Francisco, CA',   utc: -8,   tz: 'America/Los_Angeles',                     tags: ['sf', 'ca', 'us', 'usa', '940', '941', '942', '943', '944', '945', '946'] },
  { name: 'Seattle, WA',         utc: -8,   tz: 'America/Los_Angeles',                     tags: ['wa', 'us', 'usa', '980', '981', '982', '983', '984'] },
  { name: 'Denver, CO',          utc: -7,   tz: 'America/Denver',                          tags: ['co', 'us', 'usa', '800', '801', '802', '803', '804', '805'] },
  { name: 'Nashville, TN',       utc: -6,   tz: 'America/Chicago',                         tags: ['tn', 'us', 'usa', '370', '371', '372'] },
  { name: 'Las Vegas, NV',       utc: -8,   tz: 'America/Los_Angeles',                     tags: ['nv', 'us', 'usa', '889', '890', '891'] },
  { name: 'Portland, OR',        utc: -8,   tz: 'America/Los_Angeles',                     tags: ['or', 'us', 'usa', '970', '971', '972'] },
  { name: 'Boston, MA',          utc: -5,   tz: 'America/New_York',                        tags: ['ma', 'us', 'usa', '021', '022', '023', '024', '025'] },
  { name: 'Miami, FL',           utc: -5,   tz: 'America/New_York',                        tags: ['fl', 'us', 'usa', '330', '331', '332', '333'] },
  { name: 'Atlanta, GA',         utc: -5,   tz: 'America/New_York',                        tags: ['ga', 'us', 'usa', '303', '304', '305', '306'] },
  { name: 'Minneapolis, MN',     utc: -6,   tz: 'America/Chicago',                         tags: ['mn', 'us', 'usa', '554', '555', '556'] },
  { name: 'Washington, DC',      utc: -5,   tz: 'America/New_York',                        tags: ['dc', 'us', 'usa', '200', '201', '202', '203', '204', '205'] },
  { name: 'Baltimore, MD',       utc: -5,   tz: 'America/New_York',                        tags: ['md', 'us', 'usa', '210', '211', '212', '213'] },
  { name: 'Charlotte, NC',       utc: -5,   tz: 'America/New_York',                        tags: ['nc', 'us', 'usa', '282', '283'] },
  { name: 'Raleigh, NC',         utc: -5,   tz: 'America/New_York',                        tags: ['nc', 'us', 'usa', '276', '277', '278'] },
  { name: 'Columbus, OH',        utc: -5,   tz: 'America/New_York',                        tags: ['oh', 'us', 'usa', '430', '431', '432'] },
  { name: 'Indianapolis, IN',    utc: -5,   tz: 'America/Indiana/Indianapolis',             tags: ['in', 'us', 'usa', '460', '461', '462'] },
  { name: 'Kansas City, MO',     utc: -6,   tz: 'America/Chicago',                         tags: ['mo', 'ks', 'us', 'usa', '640', '641', '642'] },
  { name: 'Sacramento, CA',      utc: -8,   tz: 'America/Los_Angeles',                     tags: ['ca', 'us', 'usa', '942', '957', '958'] },
  { name: 'Orlando, FL',         utc: -5,   tz: 'America/New_York',                        tags: ['fl', 'us', 'usa', '328', '329', '347'] },
  { name: 'Tampa, FL',           utc: -5,   tz: 'America/New_York',                        tags: ['fl', 'us', 'usa', '335', '336', '337'] },
  { name: 'Pittsburgh, PA',      utc: -5,   tz: 'America/New_York',                        tags: ['pa', 'us', 'usa', '150', '151', '152', '153'] },
  { name: 'Oklahoma City, OK',   utc: -6,   tz: 'America/Chicago',                         tags: ['ok', 'us', 'usa', '730', '731'] },
  { name: 'Salt Lake City, UT',  utc: -7,   tz: 'America/Denver',                          tags: ['ut', 'us', 'usa', '840', '841', '842'] },
  { name: 'Richmond, VA',        utc: -5,   tz: 'America/New_York',                        tags: ['va', 'us', 'usa', '230', '231', '232'] },
  { name: 'New Orleans, LA',     utc: -6,   tz: 'America/Chicago',                         tags: ['la', 'us', 'usa', '700', '701', '703'] },
  { name: 'Honolulu, HI',        utc: -10,  tz: 'Pacific/Honolulu',                        tags: ['hi', 'us', 'usa', '968'] },
  { name: 'Anchorage, AK',       utc: -9,   tz: 'America/Anchorage',                       tags: ['ak', 'us', 'usa', '995', '996', '997'] },
  { name: 'Beverly Hills, CA',   utc: -8,   tz: 'America/Los_Angeles',                     tags: ['ca', 'us', 'usa', '90210'] },
  // Canada
  { name: 'Toronto, Canada',     utc: -5,   tz: 'America/Toronto',                         tags: ['on', 'ontario', 'ca', 'canada'] },
  { name: 'Vancouver, Canada',   utc: -8,   tz: 'America/Vancouver',                       tags: ['bc', 'british columbia', 'ca', 'canada'] },
  { name: 'Montreal, Canada',    utc: -5,   tz: 'America/Toronto',                         tags: ['qc', 'quebec', 'ca', 'canada'] },
  { name: 'Calgary, Canada',     utc: -7,   tz: 'America/Edmonton',                        tags: ['ab', 'alberta', 'ca', 'canada'] },
  { name: 'Ottawa, Canada',      utc: -5,   tz: 'America/Toronto',                         tags: ['on', 'ontario', 'ca', 'canada'] },
  { name: 'Edmonton, Canada',    utc: -7,   tz: 'America/Edmonton',                        tags: ['ab', 'alberta', 'ca', 'canada'] },
  // Europe
  { name: 'London, UK',          utc: 0,    tz: 'Europe/London',                           tags: ['england', 'gb', 'britain', 'uk'] },
  { name: 'Paris, France',       utc: 1,    tz: 'Europe/Paris',                            tags: ['fr', 'france'] },
  { name: 'Berlin, Germany',     utc: 1,    tz: 'Europe/Berlin',                           tags: ['de', 'germany'] },
  { name: 'Madrid, Spain',       utc: 1,    tz: 'Europe/Madrid',                           tags: ['es', 'spain'] },
  { name: 'Barcelona, Spain',    utc: 1,    tz: 'Europe/Madrid',                           tags: ['es', 'spain'] },
  { name: 'Rome, Italy',         utc: 1,    tz: 'Europe/Rome',                             tags: ['it', 'italy'] },
  { name: 'Milan, Italy',        utc: 1,    tz: 'Europe/Rome',                             tags: ['it', 'italy'] },
  { name: 'Amsterdam, Netherlands', utc: 1, tz: 'Europe/Amsterdam',                        tags: ['nl', 'netherlands', 'holland'] },
  { name: 'Brussels, Belgium',   utc: 1,    tz: 'Europe/Brussels',                         tags: ['be', 'belgium'] },
  { name: 'Vienna, Austria',     utc: 1,    tz: 'Europe/Vienna',                           tags: ['at', 'austria'] },
  { name: 'Zurich, Switzerland', utc: 1,    tz: 'Europe/Zurich',                           tags: ['ch', 'switzerland', 'swiss'] },
  { name: 'Stockholm, Sweden',   utc: 1,    tz: 'Europe/Stockholm',                        tags: ['se', 'sweden'] },
  { name: 'Oslo, Norway',        utc: 1,    tz: 'Europe/Oslo',                             tags: ['no', 'norway'] },
  { name: 'Copenhagen, Denmark', utc: 1,    tz: 'Europe/Copenhagen',                       tags: ['dk', 'denmark'] },
  { name: 'Helsinki, Finland',   utc: 2,    tz: 'Europe/Helsinki',                         tags: ['fi', 'finland'] },
  { name: 'Warsaw, Poland',      utc: 1,    tz: 'Europe/Warsaw',                           tags: ['pl', 'poland'] },
  { name: 'Prague, Czech Republic', utc: 1, tz: 'Europe/Prague',                           tags: ['cz', 'czech', 'czechia'] },
  { name: 'Budapest, Hungary',   utc: 1,    tz: 'Europe/Budapest',                         tags: ['hu', 'hungary'] },
  { name: 'Bucharest, Romania',  utc: 2,    tz: 'Europe/Bucharest',                        tags: ['ro', 'romania'] },
  { name: 'Athens, Greece',      utc: 2,    tz: 'Europe/Athens',                           tags: ['gr', 'greece'] },
  { name: 'Lisbon, Portugal',    utc: 0,    tz: 'Europe/Lisbon',                           tags: ['pt', 'portugal'] },
  { name: 'Dublin, Ireland',     utc: 0,    tz: 'Europe/Dublin',                           tags: ['ie', 'ireland'] },
  { name: 'Edinburgh, UK',       utc: 0,    tz: 'Europe/London',                           tags: ['scotland', 'gb', 'uk'] },
  { name: 'Moscow, Russia',      utc: 3,    tz: 'Europe/Moscow',                           tags: ['ru', 'russia'] },
  { name: 'Istanbul, Turkey',    utc: 3,    tz: 'Europe/Istanbul',                         tags: ['tr', 'turkey', 'turkiye'] },
  { name: 'Kiev, Ukraine',       utc: 2,    tz: 'Europe/Kiev',                             tags: ['ua', 'ukraine'] },
  // Middle East & Africa
  { name: 'Dubai, UAE',          utc: 4,    tz: 'Asia/Dubai',                              tags: ['ae', 'uae', 'united arab emirates', 'emirates'] },
  { name: 'Abu Dhabi, UAE',      utc: 4,    tz: 'Asia/Dubai',                              tags: ['ae', 'uae', 'united arab emirates'] },
  { name: 'Riyadh, Saudi Arabia', utc: 3,   tz: 'Asia/Riyadh',                             tags: ['sa', 'saudi'] },
  { name: 'Tel Aviv, Israel',    utc: 2,    tz: 'Asia/Jerusalem',                          tags: ['il', 'israel'] },
  { name: 'Cairo, Egypt',        utc: 2,    tz: 'Africa/Cairo',                            tags: ['eg', 'egypt'] },
  { name: 'Lagos, Nigeria',      utc: 1,    tz: 'Africa/Lagos',                            tags: ['ng', 'nigeria'] },
  { name: 'Nairobi, Kenya',      utc: 3,    tz: 'Africa/Nairobi',                          tags: ['ke', 'kenya'] },
  { name: 'Johannesburg, South Africa', utc: 2, tz: 'Africa/Johannesburg',                 tags: ['za', 'south africa', 'rsa'] },
  { name: 'Cape Town, South Africa',    utc: 2, tz: 'Africa/Johannesburg',                 tags: ['za', 'south africa', 'rsa'] },
  { name: 'Casablanca, Morocco', utc: 1,    tz: 'Africa/Casablanca',                       tags: ['ma', 'morocco'] },
  // Asia-Pacific
  { name: 'Tokyo, Japan',        utc: 9,    tz: 'Asia/Tokyo',                              tags: ['jp', 'japan'] },
  { name: 'Osaka, Japan',        utc: 9,    tz: 'Asia/Tokyo',                              tags: ['jp', 'japan'] },
  { name: 'Seoul, South Korea',  utc: 9,    tz: 'Asia/Seoul',                              tags: ['kr', 'korea', 'south korea'] },
  { name: 'Beijing, China',      utc: 8,    tz: 'Asia/Shanghai',                           tags: ['cn', 'china'] },
  { name: 'Shanghai, China',     utc: 8,    tz: 'Asia/Shanghai',                           tags: ['cn', 'china'] },
  { name: 'Shenzhen, China',     utc: 8,    tz: 'Asia/Shanghai',                           tags: ['cn', 'china'] },
  { name: 'Hong Kong',           utc: 8,    tz: 'Asia/Hong_Kong',                          tags: ['hk', 'hong kong', 'china'] },
  { name: 'Singapore',           utc: 8,    tz: 'Asia/Singapore',                          tags: ['sg', 'singapore'] },
  { name: 'Taipei, Taiwan',      utc: 8,    tz: 'Asia/Taipei',                             tags: ['tw', 'taiwan'] },
  { name: 'Bangkok, Thailand',   utc: 7,    tz: 'Asia/Bangkok',                            tags: ['th', 'thailand'] },
  { name: 'Kuala Lumpur, Malaysia', utc: 8, tz: 'Asia/Kuala_Lumpur',                       tags: ['my', 'malaysia'] },
  { name: 'Jakarta, Indonesia',  utc: 7,    tz: 'Asia/Jakarta',                            tags: ['id', 'indonesia'] },
  { name: 'Manila, Philippines', utc: 8,    tz: 'Asia/Manila',                             tags: ['ph', 'philippines'] },
  { name: 'Ho Chi Minh City, Vietnam', utc: 7, tz: 'Asia/Ho_Chi_Minh',                    tags: ['vn', 'vietnam'] },
  { name: 'Mumbai, India',       utc: 5.5,  tz: 'Asia/Kolkata',                            tags: ['in', 'india', 'bombay'] },
  { name: 'Delhi, India',        utc: 5.5,  tz: 'Asia/Kolkata',                            tags: ['in', 'india', 'new delhi'] },
  { name: 'Bangalore, India',    utc: 5.5,  tz: 'Asia/Kolkata',                            tags: ['in', 'india', 'bengaluru'] },
  { name: 'Chennai, India',      utc: 5.5,  tz: 'Asia/Kolkata',                            tags: ['in', 'india', 'madras'] },
  { name: 'Hyderabad, India',    utc: 5.5,  tz: 'Asia/Kolkata',                            tags: ['in', 'india'] },
  { name: 'Karachi, Pakistan',   utc: 5,    tz: 'Asia/Karachi',                            tags: ['pk', 'pakistan'] },
  { name: 'Islamabad, Pakistan', utc: 5,    tz: 'Asia/Karachi',                            tags: ['pk', 'pakistan'] },
  { name: 'Dhaka, Bangladesh',   utc: 6,    tz: 'Asia/Dhaka',                              tags: ['bd', 'bangladesh'] },
  { name: 'Colombo, Sri Lanka',  utc: 5.5,  tz: 'Asia/Colombo',                            tags: ['lk', 'sri lanka'] },
  { name: 'Yangon, Myanmar',     utc: 6.5,  tz: 'Asia/Rangoon',                            tags: ['mm', 'myanmar', 'burma'] },
  { name: 'Sydney, Australia',   utc: 10,   tz: 'Australia/Sydney',                        tags: ['nsw', 'au', 'australia'] },
  { name: 'Melbourne, Australia', utc: 10,  tz: 'Australia/Melbourne',                     tags: ['vic', 'au', 'australia'] },
  { name: 'Brisbane, Australia', utc: 10,   tz: 'Australia/Brisbane',                      tags: ['qld', 'au', 'australia'] },
  { name: 'Perth, Australia',    utc: 8,    tz: 'Australia/Perth',                         tags: ['wa', 'au', 'australia'] },
  { name: 'Auckland, New Zealand', utc: 12, tz: 'Pacific/Auckland',                        tags: ['nz', 'new zealand'] },
  // Latin America
  { name: 'Mexico City, Mexico', utc: -6,   tz: 'America/Mexico_City',                     tags: ['mx', 'mexico', 'cdmx'] },
  { name: 'São Paulo, Brazil',   utc: -3,   tz: 'America/Sao_Paulo',                       tags: ['br', 'brazil', 'sao paulo', 'saoPaulo'] },
  { name: 'Rio de Janeiro, Brazil', utc: -3, tz: 'America/Sao_Paulo',                      tags: ['br', 'brazil', 'rio'] },
  { name: 'Buenos Aires, Argentina', utc: -3, tz: 'America/Argentina/Buenos_Aires',         tags: ['ar', 'argentina'] },
  { name: 'Santiago, Chile',     utc: -4,   tz: 'America/Santiago',                        tags: ['cl', 'chile'] },
  { name: 'Lima, Peru',          utc: -5,   tz: 'America/Lima',                            tags: ['pe', 'peru'] },
  { name: 'Bogotá, Colombia',    utc: -5,   tz: 'America/Bogota',                          tags: ['co', 'colombia', 'bogota'] },
]

// ---------------------------------------------------------------------------
// Fuzzy filter
// ---------------------------------------------------------------------------

function filterSuggestions(query: string): SuggestionEntry[] {
  const q = query.toLowerCase().trim()
  if (!q) return SUGGESTIONS.slice(0, 8)

  const scored = SUGGESTIONS
    .map(s => {
      const nameLower = s.name.toLowerCase()
      // Exact name prefix: highest score
      if (nameLower.startsWith(q))      return { s, score: 100 }
      // Name contains query: high score
      if (nameLower.includes(q))        return { s, score: 60 }
      // ZIP code prefix
      if (s.tags.some(t => /^\d/.test(t) && t.startsWith(q))) return { s, score: 90 }
      // Tag contains query
      if (s.tags.some(t => t.includes(q))) return { s, score: 40 }
      return { s, score: 0 }
    })
    .filter(x => x.score > 0)
    .sort((a, b) => b.score - a.score)

  return scored.slice(0, 7).map(x => x.s)
}

function utcLabel(offset: number): string {
  if (offset === 0) return 'UTC'
  return `UTC${offset > 0 ? '+' : ''}${offset % 1 === 0 ? offset : offset.toFixed(1)}`
}

/**
 * Compute the current (DST-aware) UTC offset for an IANA timezone using the
 * browser's built-in Intl API.  Returns null if the timezone is unknown or
 * if the browser doesn't support the required Intl features.
 */
function getDSTAwareOffset(tz: string): number | null {
  try {
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      timeZoneName: 'shortOffset',
    })
    const parts = formatter.formatToParts(new Date())
    const offsetPart = parts.find(p => p.type === 'timeZoneName')
    if (!offsetPart) return null
    // offsetPart.value is like "GMT-7", "GMT+5:30", or "GMT"
    if (offsetPart.value === 'GMT') return 0
    const match = offsetPart.value.match(/GMT([+-])(\d+)(?::(\d+))?/)
    if (!match) return null
    const sign    = match[1] === '+' ? 1 : -1
    const hours   = parseInt(match[2]!, 10)
    const minutes = match[3] ? parseInt(match[3], 10) : 0
    return sign * (hours + minutes / 60)
  } catch {
    return null
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function LocationPicker({ onLocationChanged }: LocationPickerProps) {
  const [location,    setLocation]    = useState<Location | null>(null)
  const [editing,     setEditing]     = useState(false)
  const [draft,       setDraft]       = useState('')
  const [loading,     setLoading]     = useState(false)
  const [error,       setError]       = useState<string | null>(null)
  const [suggestions, setSuggestions] = useState<SuggestionEntry[]>([])
  const [activeIdx,   setActiveIdx]   = useState(-1)
  const inputRef  = useRef<HTMLInputElement>(null)
  const listRef   = useRef<HTMLUListElement>(null)

  // Fetch current location on mount
  useEffect(() => {
    fetch('/api/location')
      .then(r => r.ok ? r.json() : null)
      .then((d: Location | null) => { if (d) setLocation(d) })
      .catch(() => {})
  }, [])

  // Open edit mode
  const openEdit = useCallback(() => {
    setDraft(location?.name ?? '')
    setError(null)
    setActiveIdx(-1)
    setSuggestions(filterSuggestions(location?.name ?? ''))
    setEditing(true)
    setTimeout(() => {
      inputRef.current?.select()
    }, 20)
  }, [location?.name])

  // Update suggestions as draft changes
  useEffect(() => {
    if (editing) {
      setSuggestions(filterSuggestions(draft))
      setActiveIdx(-1)
    }
  }, [draft, editing])

  // Live local clock — ticks every second using the DST-aware offset from the API.
  // current_utc_offset_h is computed server-side at request time via zoneinfo.
  const [localTime, setLocalTime] = useState<string>('')
  useEffect(() => {
    function tick() {
      // Prefer current_utc_offset_h (DST-aware) over utc_offset_h (standard-time only)
      const utcOffset = location?.current_utc_offset_h ?? location?.utc_offset_h ?? null
      if (utcOffset === null) { setLocalTime(''); return }
      const localMs  = Date.now() + utcOffset * 3_600_000
      const d        = new Date(localMs)
      const hh       = String(d.getUTCHours()).padStart(2, '0')
      const mm       = String(d.getUTCMinutes()).padStart(2, '0')
      const ss       = String(d.getUTCSeconds()).padStart(2, '0')
      setLocalTime(`${hh}:${mm}:${ss}`)
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [location?.current_utc_offset_h, location?.utc_offset_h])

  async function submit(value: string) {
    const v = value.trim()
    if (!v || loading) return
    setLoading(true)
    setError(null)
    try {
      const resp = await fetch('/api/location', {
        method:  'PUT',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ address: v }),
      })
      const data = await resp.json()
      if (!resp.ok) {
        setError(data.error ?? 'Could not resolve location — try a city name, state, or ZIP code')
        setLoading(false)
        return
      }
      setLocation(data as Location)
      setEditing(false)
      onLocationChanged?.(data as Location)
    } catch {
      setError('Network error — server unreachable')
    } finally {
      setLoading(false)
    }
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx(i => Math.min(i + 1, suggestions.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx(i => Math.max(i - 1, -1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (activeIdx >= 0 && suggestions[activeIdx]) {
        void submit(suggestions[activeIdx].name)
      } else {
        void submit(draft)
      }
    } else if (e.key === 'Escape') {
      setEditing(false)
      setError(null)
    }
  }

  // Use DST-aware offset for the UTC label (e.g. "UTC-7" in summer, not "UTC-8")
  const utc = location?.current_utc_offset_h ?? location?.utc_offset_h ?? null

  // ── DISPLAY MODE ────────────────────────────────────────────────────────────
  if (!editing) {
    return (
      <div className="flex flex-col gap-0.5 flex-shrink-0" style={{ width: 240 }}>
        <div
          className="font-mono text-[9px] uppercase tracking-wider"
          style={{ color: '#4b5764' }}
        >
          DATA CENTRE
        </div>

        {/* City + live local time on the same row */}
        <button
          onClick={openEdit}
          className="text-left group flex items-center justify-between gap-2"
          title="Click to change data-centre location"
          aria-label="Change data-centre location"
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, width: '100%' }}
        >
          <span className="flex items-center gap-1.5 min-w-0">
            <span style={{ fontSize: 11, lineHeight: 1, flexShrink: 0 }}>📍</span>
            <span
              className="font-mono text-sm font-semibold leading-none truncate"
              style={{ color: '#e6edf3' }}
            >
              {location?.name ?? '…'}
            </span>
          </span>
          {localTime && (
            <span
              className="font-mono font-bold leading-none flex-shrink-0"
              style={{ fontSize: 18, color: '#3fb6a8', letterSpacing: '0.04em' }}
            >
              {localTime}
            </span>
          )}
        </button>

        {utc !== null && (
          <div className="font-mono text-[9px] mt-0.5" style={{ color: '#4b5764' }}>
            {utcLabel(utc)}
            <span
              className="ml-2 cursor-pointer transition-colors hover:text-teal-400"
              style={{ color: '#3a4555' }}
              onClick={openEdit}
              role="button"
              tabIndex={0}
              onKeyDown={e => e.key === 'Enter' && openEdit()}
            >
              change ✎
            </span>
          </div>
        )}
      </div>
    )
  }

  // ── EDIT MODE ───────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-0.5 flex-shrink-0 relative" style={{ width: 240 }}>
      <div
        className="font-mono text-[9px] uppercase tracking-wider"
        style={{ color: '#4b5764' }}
      >
        DATA CENTRE
      </div>

      {/* Input row */}
      <div className="flex items-center gap-1">
        <span style={{ fontSize: 11 }}>📍</span>
        <input
          ref={inputRef}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={handleKey}
          placeholder="City, state or ZIP…"
          disabled={loading}
          autoComplete="off"
          spellCheck={false}
          className="font-mono text-sm bg-transparent border-b outline-none flex-1"
          style={{
            color:       '#e6edf3',
            borderColor: error ? '#e05252' : '#3fb6a8',
            paddingBottom: 1,
          }}
        />
        <button
          onClick={() => submit(activeIdx >= 0 ? suggestions[activeIdx]!.name : draft)}
          disabled={loading || !draft.trim()}
          className="font-mono text-[9px] px-2 py-0.5 rounded"
          style={{
            background: '#0d2433',
            color:      loading ? '#4b5764' : '#3fb6a8',
            border:     '1px solid #1e3a50',
            cursor:     loading ? 'wait' : 'pointer',
            flexShrink: 0,
          }}
        >
          {loading ? '…' : 'Apply'}
        </button>
        <button
          onClick={() => { setEditing(false); setError(null) }}
          disabled={loading}
          className="font-mono text-[9px]"
          style={{ color: '#4b5764', background: 'none', border: 'none', cursor: 'pointer', flexShrink: 0 }}
        >
          ✕
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="font-mono text-[9px] mt-0.5 leading-tight" style={{ color: '#e05252' }}>
          {error}
        </div>
      )}

      {/* Autocomplete dropdown */}
      {suggestions.length > 0 && !loading && (
        <ul
          ref={listRef}
          className="absolute rounded border shadow-lg z-50"
          style={{
            top:        '100%',
            left:       0,
            right:      0,
            background: '#111821',
            border:     '1px solid #1e2a36',
            marginTop:  4,
            listStyle:  'none',
            padding:    '3px 0',
          }}
        >
          {suggestions.map((s, i) => (
            <li
              key={s.name}
              onMouseDown={e => { e.preventDefault(); void submit(s.name) }}
              onMouseEnter={() => setActiveIdx(i)}
              className="font-mono cursor-pointer flex items-center justify-between"
              style={{
                fontSize:   11,
                padding:    '4px 10px',
                color:      i === activeIdx ? '#e6edf3' : '#9ba8b5',
                background: i === activeIdx ? '#1a2536' : 'transparent',
              }}
            >
              <span>
                <span style={{ marginRight: 6 }}>📍</span>
                {s.name}
              </span>
              {(() => {
                const liveOffset = s.tz ? getDSTAwareOffset(s.tz) : null
                return liveOffset !== null
                  ? <span style={{ color: '#3a4555', fontSize: 9 }}>{utcLabel(liveOffset)}</span>
                  : null
              })()}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
