import axios from 'axios';
import { API_URL, TRENDING_LIMIT_DEFAULT } from './constants';

const api = axios.create({
    baseURL: API_URL,
    timeout: 15000, // 15s timeout to prevent UI hang
    headers: {
        'Content-Type': 'application/json',
    },
});

export interface Movie {
    id: number;
    title: string;
    poster_path?: string;
    backdrop_path?: string;
    tagline?: string;
    director?: string;
    cast?: string;
    keywords?: string;
    vote_average: number;
    vote_count: number;
    overview?: string;
    genres?: string[] | string;
    release_date?: string;
    runtime?: number;
    budget?: number;
    revenue?: number;
    homepage?: string;
    imdb_id?: string;
    tmdb_id?: number;
    reason?: string;
    content_score?: number;
    semantic_score?: number;
    profile_score?: number;
    collaborative_score?: number;
    quality_score?: number;
    popularity_score?: number;
    hybrid_score?: number;
    match_score?: number;
    score?: number;
    weighted_rating?: number;
    cinevault_qualities?: string[];
    original_language?: string;
}

export interface ChatMessage {
    role: 'user' | 'assistant';
    content: string;
}

export interface ChatResponse {
    response: string;
    sources?: any[];
}

export interface SearchFilters {
    q?: string;
    genre?: string;
    director?: string;
    actor?: string;
    min_rating?: number;
    max_rating?: number;
    year_from?: number;
    year_to?: number;
    sort_by?: 'vote_average' | 'release_date' | 'title' | 'vote_count';
    sort_order?: 'asc' | 'desc';
    page?: number;
    per_page?: number;
}

export interface DiscoveryRequest {
    query?: string;
    user_id?: number;
    liked_movie_ids?: number[];
    liked_titles?: string[];
    excluded_movie_ids?: number[];
    limit?: number;
    min_rating?: number;
    diversity_factor?: number;
    use_reranker?: boolean;
}

// Private helper to extract movie lists consistently
const parseItems = (data: any): Movie[] => data.items || data.results || data.movies || [];

export const movieApi = {
    getTrending: async (limit = TRENDING_LIMIT_DEFAULT): Promise<Movie[]> => {
        const res = await api.get('/trending', { params: { limit } });
        return parseItems(res.data);
    },

    getMovie: async (id: number): Promise<Movie> => {
        const res = await api.get(`/movies/${id}`);
        return res.data;
    },

    getRecommendations: async (movieId: number): Promise<Movie[]> => {
        const res = await api.get(`/recommendations/similar/${movieId}`);
        return res.data.recommendations || [];
    },

    getPersonalizedRecommendations: async (userId: number): Promise<Movie[]> => {
        const res = await api.get(`/recommendations/personalized/${userId}`);
        return res.data.recommendations || [];
    },

    search: async (query: string): Promise<Movie[]> => {
        const res = await api.get('/movies/search', { params: { q: query } });
        return parseItems(res.data);
    },

    searchFiltered: async (filters: SearchFilters): Promise<{ items: Movie[]; total: number; page: number; total_pages: number }> => {
        const params: Record<string, string | number> = {};
        if (filters.q) params.q = filters.q;
        if (filters.genre) params.genre = filters.genre;
        if (filters.director) params.director = filters.director;
        if (filters.actor) params.actor = filters.actor;
        if (filters.min_rating !== undefined && filters.min_rating > 0) params.min_rating = filters.min_rating;
        if (filters.max_rating !== undefined && filters.max_rating < 10) params.max_rating = filters.max_rating;
        if (filters.year_from) params.year_from = filters.year_from;
        if (filters.year_to) params.year_to = filters.year_to;
        if (filters.sort_by) params.sort_by = filters.sort_by;
        if (filters.sort_order) params.sort_order = filters.sort_order;
        if (filters.page) params.page = filters.page;
        if (filters.per_page) params.per_page = filters.per_page;
        const res = await api.get('/movies/search', { params });
        return res.data;
    },

    searchSemantic: async (query: string, rerank = false): Promise<Movie[]> => {
        const res = await api.get('/movies/semantic-search', {
            params: { q: query, rerank },
        });
        return parseItems(res.data);
    },

    discover: async (payload: DiscoveryRequest): Promise<Movie[]> => {
        const res = await api.post('/recommendations/discover', payload);
        return res.data.recommendations || [];
    },

    visualSearch: async (query: string): Promise<Movie[]> => {
        const res = await api.get('/movies/visual/search', { params: { q: query } });
        return parseItems(res.data);
    },

    getGraphRelated: async (title: string, type = 'movie') => {
        const res = await api.get(`/movies/graph/related/${encodeURIComponent(title)}`, {
            params: { entity_type: type },
        });
        return res.data.related;
    },

    getGraphPath: async (movie1: string, movie2: string) => {
        const res = await api.get('/movies/graph/path', {
            params: { movie1, movie2 },
        });
        return res.data.paths;
    },

    getByGenre: async (genre: string): Promise<Movie[]> => {
        const res = await api.get(`/movies/genre/${encodeURIComponent(genre)}`);
        return parseItems(res.data);
    },

    chat: async (message: string, history: ChatMessage[] = [], sessionId?: string, userId?: number): Promise<ChatResponse> => {
        const res = await api.post('/agent/chat', {
            input: message,
            chat_history: history,
            session_id: sessionId,
            user_id: userId,
        });
        return res.data;
    },

    // ============== Phase 4: New API Methods ==============

    getMoodRecommendations: async (text: string, userId?: number): Promise<Movie[]> => {
        const res = await api.post('/api/v1/recommendations/mood', { text, user_id: userId, limit: 10 });
        return res.data.recommendations || [];
    },

    getSessionRecommendations: async (sessionId: string): Promise<Movie[]> => {
        const res = await api.get(`/api/v1/recommendations/session/${sessionId}`);
        return res.data.recommendations || [];
    },

    trackSessionInteraction: async (sessionId: string, movieId: number, action: string): Promise<void> => {
        await api.post('/api/v1/sessions/track', { session_id: sessionId, movie_id: movieId, action });
    },

    getUserTasteProfile: async (userId: number): Promise<any> => {
        const res = await api.get(`/api/v1/users/${userId}/taste-profile`);
        return res.data;
    },

    getMovieConnections: async (movieId: number): Promise<any> => {
        const movie = await api.get(`/movies/${movieId}`);
        const title = movie.data.title;
        const res = await api.get(`/movies/graph/related/${encodeURIComponent(title)}`);
        return res.data;
    },

    getDirectorFilmography: async (name: string): Promise<any> => {
        const res = await api.get(`/api/v1/directors/${encodeURIComponent(name)}/journey`);
        return res.data;
    },

    getMoviesByDecade: async (decade: string, limit: number = 20): Promise<Movie[]> => {
        const res = await api.get(`/api/v1/recommendations/era/${decade}`, { params: { limit } });
        return res.data.recommendations || [];
    },

    submitOnboardingRatings: async (userId: number, ratings: { movieId: number; rating: number }[]): Promise<void> => {
        await Promise.all(ratings.map(r =>
            api.post('/ratings', { user_id: userId, movie_id: r.movieId, rating: r.rating })
        ));
    },

    getLatest: async (limit = 10): Promise<Movie[]> => {
        const res = await api.get('/latest', { params: { limit } });
        return parseItems(res.data);
    },

    getGenres: async (): Promise<any[]> => {
        const res = await api.get('/genres');
        return res.data;
    },

    getVisualDNA: async (movieId: number): Promise<any> => {
        const res = await api.get(`/api/v1/movies/${movieId}/visual-dna`);
        return res.data;
    },

    getMoodPlaylist: async (duration: string, startMood: string, endMood: string, userId?: number): Promise<any> => {
        const res = await api.post('/api/v1/playlists/mood', {
            duration, starting_mood: startMood, ending_mood: endMood, user_id: userId,
        });
        return res.data;
    },
};
