'use client';

import { useEffect, useState } from 'react';
import { movieApi, Movie } from '../api';
import { getSessionId } from '../lib/session';

export default function SessionRail() {
    const [movies, setMovies] = useState<Movie[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const sessionId = getSessionId();
        if (!sessionId) { setLoading(false); return; }

        movieApi.getSessionRecommendations(sessionId)
            .then(setMovies)
            .catch(() => setMovies([]))
            .finally(() => setLoading(false));
    }, []);

    if (loading || movies.length === 0) return null;

    return (
        <div className="space-y-3">
            <h3 className="text-lg font-semibold text-white">Continue Your Vibe</h3>
            <div className="flex gap-4 overflow-x-auto pb-2 scrollbar-hide">
                {movies.map((movie) => (
                    <a
                        key={movie.id}
                        href={`/movie/${movie.id}`}
                        className="flex-shrink-0 w-36 group"
                    >
                        <div className="aspect-[2/3] rounded-lg overflow-hidden bg-white/5">
                            {movie.poster_path ? (
                                <img
                                    src={`https://image.tmdb.org/t/p/w300${movie.poster_path}`}
                                    alt={movie.title}
                                    className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                                />
                            ) : (
                                <div className="w-full h-full flex items-center justify-center text-white/30 text-xs">{movie.title}</div>
                            )}
                        </div>
                        <p className="text-sm text-white/80 mt-1 truncate">{movie.title}</p>
                    </a>
                ))}
            </div>
        </div>
    );
}
