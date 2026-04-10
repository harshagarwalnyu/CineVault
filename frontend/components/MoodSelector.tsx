'use client';

import { useState } from 'react';
import { movieApi, Movie } from '../api';

const MOODS = [
    { name: 'happy', color: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30' },
    { name: 'melancholic', color: 'bg-blue-500/20 text-blue-300 border-blue-500/30' },
    { name: 'tense', color: 'bg-red-500/20 text-red-300 border-red-500/30' },
    { name: 'adventurous', color: 'bg-orange-500/20 text-orange-300 border-orange-500/30' },
    { name: 'nostalgic', color: 'bg-amber-500/20 text-amber-300 border-amber-500/30' },
    { name: 'angry', color: 'bg-red-700/20 text-red-400 border-red-700/30' },
    { name: 'romantic', color: 'bg-pink-500/20 text-pink-300 border-pink-500/30' },
    { name: 'intellectual', color: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30' },
    { name: 'cozy', color: 'bg-orange-400/20 text-orange-200 border-orange-400/30' },
    { name: 'dark', color: 'bg-gray-700/20 text-gray-300 border-gray-600/30' },
    { name: 'inspired', color: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' },
    { name: 'whimsical', color: 'bg-purple-500/20 text-purple-300 border-purple-500/30' },
];

interface Props {
    onRecommendations: (movies: Movie[]) => void;
}

export default function MoodSelector({ onRecommendations }: Props) {
    const [selected, setSelected] = useState<string | null>(null);
    const [freeText, setFreeText] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async () => {
        const query = freeText || selected || '';
        if (!query) return;

        setLoading(true);
        try {
            const movies = await movieApi.getMoodRecommendations(query);
            onRecommendations(movies);
        } catch (err) {
            console.error('Mood search failed:', err);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="space-y-4">
            <h3 className="text-lg font-semibold text-white">How are you feeling?</h3>
            <div className="flex flex-wrap gap-2">
                {MOODS.map((mood) => (
                    <button
                        key={mood.name}
                        onClick={() => { setSelected(mood.name); setFreeText(''); }}
                        className={`px-4 py-2 rounded-full border text-sm capitalize transition-all ${mood.color} ${selected === mood.name ? 'ring-2 ring-white/50 scale-105' : 'opacity-70 hover:opacity-100'}`}
                    >
                        {mood.name}
                    </button>
                ))}
            </div>
            <div className="flex gap-2">
                <input
                    type="text"
                    value={freeText}
                    onChange={(e) => { setFreeText(e.target.value); setSelected(null); }}
                    placeholder="Or describe your mood..."
                    className="flex-1 bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-white/20"
                />
                <button
                    onClick={handleSubmit}
                    disabled={loading || (!selected && !freeText)}
                    className="px-6 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-colors disabled:opacity-40"
                >
                    {loading ? 'Finding...' : 'Find Movies'}
                </button>
            </div>
        </div>
    );
}
