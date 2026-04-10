'use client';

import { useState } from 'react';
import MoodSelector from '../../components/MoodSelector';
import { Movie } from '../../api';

export default function MoodPage() {
    const [movies, setMovies] = useState<Movie[]>([]);

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white p-6 max-w-7xl mx-auto">
            <h1 className="text-3xl font-bold mb-6">Mood Discovery</h1>
            <MoodSelector onRecommendations={setMovies} />

            {movies.length > 0 && (
                <div className="mt-8">
                    <h2 className="text-xl font-semibold mb-4">Recommendations</h2>
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
                        {movies.map((movie) => (
                            <a key={movie.id} href={`/movie/${movie.id}`} className="group">
                                <div className="aspect-[2/3] rounded-lg overflow-hidden bg-white/5">
                                    {movie.poster_path ? (
                                        <img src={`https://image.tmdb.org/t/p/w300${movie.poster_path}`} alt={movie.title} className="w-full h-full object-cover group-hover:scale-105 transition-transform" />
                                    ) : (
                                        <div className="w-full h-full flex items-center justify-center text-white/30 text-xs p-2 text-center">{movie.title}</div>
                                    )}
                                </div>
                                <p className="text-sm text-white/80 mt-1 truncate">{movie.title}</p>
                                {movie.reason && <p className="text-xs text-white/40 truncate">{movie.reason}</p>}
                            </a>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
