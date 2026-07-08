'use client';

import { useState } from 'react';
import { Movie } from '../api';

const DECADES = ['1950s', '1960s', '1970s', '1980s', '1990s', '2000s', '2010s', '2020s'];

export default function TimeMachine() {
    const [selected, setSelected] = useState<string | null>(null);
    const [movies, setMovies] = useState<Movie[]>([]);
    const [context, setContext] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSelect = async (decade: string) => {
        setSelected(decade);
        setLoading(true);
        try {
            const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/recommendations/era/${decade}?limit=20`);
            const data = await res.json();
            setMovies(data.recommendations || []);
            setContext(data.context || '');
        } catch {
            setMovies([]);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap gap-2">
                {DECADES.map((decade) => (
                    <button
                        key={decade}
                        onClick={() => handleSelect(decade)}
                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${selected === decade ? 'bg-white text-black' : 'bg-white/10 text-white/70 hover:bg-white/20'}`}
                    >
                        {decade}
                    </button>
                ))}
            </div>
            {context && <p className="text-white/60 italic">{context}</p>}
            {loading && <p className="text-white/50">Loading...</p>}
            {!loading && movies.length > 0 && (
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
                            <p className="text-xs text-white/40">{movie.vote_average}/10</p>
                        </a>
                    ))}
                </div>
            )}
        </div>
    );
}
