import type { Movie } from '@/api';
import { DEFAULT_GENRE, TRENDING_LIMIT_DEFAULT } from '@/constants';

const API_BASE =
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    'http://localhost:8001';

const parseItems = <T,>(data: any): T[] => data?.items || data?.results || data?.movies || [];

/**
 * Core fetch helper with ISR-friendly caching.
 *
 * @param revalidate  — seconds before Next.js re-fetches in the background.
 *   0  = always revalidate (dynamic)
 *   60 = cache for 1 min then revalidate in background (default)
 */
async function requestJson<T>(
    path: string,
    init?: RequestInit & { revalidate?: number },
): Promise<T | null> {
    const { revalidate = 60, ...fetchInit } = init || {};
    try {
        const response = await fetch(`${API_BASE}${path}`, {
            ...fetchInit,
            next: { revalidate },
            headers: {
                'Content-Type': 'application/json',
                ...(fetchInit?.headers || {}),
            },
        });

        if (!response.ok) {
            throw new Error(`Request failed with ${response.status}`);
        }

        return response.json() as Promise<T>;
    } catch (error) {
        console.error(`Server API request failed for ${path}:`, error);
        return null;
    }
}

export async function getTrendingMovies(limit = TRENDING_LIMIT_DEFAULT): Promise<Movie[]> {
    const data = await requestJson<any>(`/trending?limit=${limit}`, { revalidate: 30 });
    return parseItems<Movie>(data);
}

export async function getLatestMovies(limit = 12): Promise<Movie[]> {
    const data = await requestJson<any>(`/latest?limit=${limit}`, { revalidate: 30 });
    return parseItems<Movie>(data);
}

export async function getMoviesByGenre(genre = DEFAULT_GENRE): Promise<Movie[]> {
    const data = await requestJson<any>(`/movies/genre/${encodeURIComponent(genre)}`, { revalidate: 60 });
    return parseItems<Movie>(data);
}

export async function getMovieById(id: number): Promise<Movie | null> {
    return requestJson<Movie>(`/movies/${id}`, { revalidate: 300 });
}

export async function getRecommendationsByMovie(movieId: number): Promise<Movie[]> {
    const data = await requestJson<any>(`/recommendations/similar/${movieId}`, { revalidate: 300 });
    return data?.recommendations || [];
}

export async function getGraphRelatedEntities(
    title: string,
    type: 'movie' | 'actor' | 'director' = 'movie',
): Promise<Array<{ name: string; type: string }>> {
    const data = await requestJson<any>(
        `/movies/graph/related/${encodeURIComponent(title)}?entity_type=${type}`,
        { revalidate: 600 },
    );
    return data?.related || [];
}
