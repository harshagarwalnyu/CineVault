export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
export const TMDB_IMAGE_BASE = 'https://image.tmdb.org/t/p/';

export const SEARCH_DEBOUNCE_MS = 500;
export const TRENDING_LIMIT_DEFAULT = 12;
export const DEFAULT_GENRE = 'Action';

export const DISCOVERY_PROMPTS = [
  'Slow-burn thrillers with elite dialogue',
  'Romantic movies that actually feel cinematic',
  'Big-world sci-fi with emotional payoff',
  'Stylish crime films with cold-blooded tension',
];

export const HOME_SIGNAL_PILLS = [
  'Hybrid taste graph',
  'Poster-first discovery',
  'Motion tuned for 60fps',
];
