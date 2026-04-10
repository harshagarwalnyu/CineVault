'use client';

import { Movie } from '../api';

interface Props {
    movies: Movie[];
    moods: string[];
}

const moodColors: Record<string, string> = {
    happy: 'bg-yellow-500', melancholic: 'bg-blue-500', tense: 'bg-red-500',
    adventurous: 'bg-orange-500', nostalgic: 'bg-amber-500', angry: 'bg-red-700',
    romantic: 'bg-pink-500', intellectual: 'bg-indigo-500', cozy: 'bg-orange-400',
    dark: 'bg-gray-600', inspired: 'bg-emerald-500', whimsical: 'bg-purple-500',
    relaxed: 'bg-teal-500', engaged: 'bg-cyan-500', catharsis: 'bg-violet-500',
};

export default function MoodPlaylist({ movies, moods }: Props) {
    if (!movies.length) return null;

    return (
        <div className="space-y-4">
            <div className="flex items-center gap-1">
                {moods.map((mood, i) => (
                    <div key={i} className="flex items-center gap-1">
                        <span className={`w-3 h-3 rounded-full ${moodColors[mood] || 'bg-white/30'}`} />
                        <span className="text-xs text-white/60 capitalize">{mood}</span>
                        {i < moods.length - 1 && <span className="text-white/20 mx-1">→</span>}
                    </div>
                ))}
            </div>
            <div className="flex gap-4 overflow-x-auto pb-2">
                {movies.map((movie, i) => (
                    <a key={`${movie.id}-${i}`} href={`/movie/${movie.id}`} className="flex-shrink-0 w-40 group">
                        <div className="aspect-[2/3] rounded-lg overflow-hidden bg-white/5 relative">
                            {movie.poster_path ? (
                                <img src={`https://image.tmdb.org/t/p/w300${movie.poster_path}`} alt={movie.title} className="w-full h-full object-cover group-hover:scale-105 transition-transform" />
                            ) : (
                                <div className="w-full h-full flex items-center justify-center text-white/30 text-xs">{movie.title}</div>
                            )}
                            <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 p-2">
                                <span className="text-xs text-white/80 capitalize">{(movie as any).arc_position || ''}</span>
                            </div>
                        </div>
                        <p className="text-sm text-white/80 mt-1 truncate">{movie.title}</p>
                    </a>
                ))}
            </div>
        </div>
    );
}
