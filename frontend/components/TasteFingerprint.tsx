'use client';

import { useEffect, useState } from 'react';
import { movieApi } from '../api';

interface Props {
    userId: number;
}

interface TasteData {
    genres: { name: string; affinity: number }[];
    decades: { decade: string; count: number }[];
    directors: { name: string; avg_rating: number; movies_rated: number }[];
    total_ratings: number;
    average_rating: number;
}

export default function TasteFingerprint({ userId }: Props) {
    const [data, setData] = useState<TasteData | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        movieApi.getUserTasteProfile(userId)
            .then(setData)
            .catch(() => setData(null))
            .finally(() => setLoading(false));
    }, [userId]);

    if (loading) return <div className="text-white/50">Loading taste profile...</div>;
    if (!data) return <div className="text-white/50">No taste data available</div>;

    const maxAffinity = Math.max(...data.genres.map(g => g.affinity), 0.01);

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-lg font-semibold text-white mb-3">Genre Affinities</h3>
                <div className="space-y-2">
                    {data.genres.slice(0, 8).map((genre) => (
                        <div key={genre.name} className="flex items-center gap-3">
                            <span className="text-sm text-white/70 w-24">{genre.name}</span>
                            <div className="flex-1 bg-white/5 rounded-full h-2">
                                <div
                                    className="bg-gradient-to-r from-blue-500 to-purple-500 h-2 rounded-full transition-all"
                                    style={{ width: `${(genre.affinity / maxAffinity) * 100}%` }}
                                />
                            </div>
                            <span className="text-xs text-white/50 w-10 text-right">{(genre.affinity * 10).toFixed(1)}</span>
                        </div>
                    ))}
                </div>
            </div>

            <div>
                <h3 className="text-lg font-semibold text-white mb-3">Decade Preferences</h3>
                <div className="flex flex-wrap gap-2">
                    {data.decades.map((d) => (
                        <span key={d.decade} className="px-3 py-1 bg-white/10 rounded-full text-sm text-white/80">
                            {d.decade}: {d.count} films
                        </span>
                    ))}
                </div>
            </div>

            {data.directors.length > 0 && (
                <div>
                    <h3 className="text-lg font-semibold text-white mb-3">Top Directors</h3>
                    <div className="space-y-1">
                        {data.directors.slice(0, 5).map((d) => (
                            <div key={d.name} className="flex justify-between text-sm">
                                <span className="text-white/80">{d.name}</span>
                                <span className="text-white/50">{d.avg_rating}/10 ({d.movies_rated} films)</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            <div className="text-sm text-white/40">
                Based on {data.total_ratings} ratings (avg: {data.average_rating}/10)
            </div>
        </div>
    );
}
