'use client';

import { useEffect, useState } from 'react';
import { movieApi, Movie } from '../api';

interface Props {
    userId: number;
    onComplete: () => void;
}

export default function OnboardingFlow({ userId, onComplete }: Props) {
    const [movies, setMovies] = useState<Movie[]>([]);
    const [ratings, setRatings] = useState<Record<number, number>>({});
    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        movieApi.getTrending(20)
            .then(setMovies)
            .catch(() => setMovies([]))
            .finally(() => setLoading(false));
    }, []);

    const ratedCount = Object.keys(ratings).length;

    const handleRate = (movieId: number, rating: number) => {
        setRatings((prev) => ({ ...prev, [movieId]: rating }));
    };

    const handleSubmit = async () => {
        setSubmitting(true);
        try {
            const ratingList = Object.entries(ratings).map(([movieId, rating]) => ({
                movieId: Number(movieId),
                rating,
            }));
            await movieApi.submitOnboardingRatings(userId, ratingList);
            onComplete();
        } catch (err) {
            console.error('Submit failed:', err);
        } finally {
            setSubmitting(false);
        }
    };

    if (loading) return <div className="text-white/50 text-center py-12">Loading movies...</div>;

    return (
        <div className="space-y-6">
            <div className="text-center">
                <h2 className="text-2xl font-bold text-white">Rate at least 10 movies</h2>
                <p className="text-white/60 mt-1">This helps us understand your taste ({ratedCount}/10)</p>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
                {movies.map((movie) => (
                    <div key={movie.id} className="space-y-2">
                        <div className="aspect-[2/3] rounded-lg overflow-hidden bg-white/5">
                            {movie.poster_path ? (
                                <img
                                    src={`https://image.tmdb.org/t/p/w300${movie.poster_path}`}
                                    alt={movie.title}
                                    className="w-full h-full object-cover"
                                />
                            ) : (
                                <div className="w-full h-full flex items-center justify-center text-white/30 text-xs p-2 text-center">{movie.title}</div>
                            )}
                        </div>
                        <p className="text-xs text-white/80 truncate">{movie.title}</p>
                        <div className="flex gap-0.5">
                            {[2, 4, 6, 8, 10].map((star) => (
                                <button
                                    key={star}
                                    onClick={() => handleRate(movie.id, star)}
                                    className={`w-5 h-5 rounded text-xs ${ratings[movie.id] >= star ? 'bg-yellow-500 text-black' : 'bg-white/10 text-white/40'}`}
                                >
                                    {star / 2}
                                </button>
                            ))}
                        </div>
                    </div>
                ))}
            </div>

            <div className="text-center">
                <button
                    onClick={handleSubmit}
                    disabled={ratedCount < 10 || submitting}
                    className="px-8 py-3 bg-white text-black rounded-lg font-semibold disabled:opacity-40 hover:bg-white/90 transition-colors"
                >
                    {submitting ? 'Submitting...' : `Continue (${ratedCount}/10)`}
                </button>
            </div>
        </div>
    );
}
