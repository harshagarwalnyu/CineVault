'use client';

import { useState } from 'react';
import MovieConnections from '../../components/MovieConnections';
import { movieApi } from '../../api';

export default function ConnectionsPage() {
    const [movieId, setMovieId] = useState<number | null>(null);
    const [search, setSearch] = useState('');

    const handleSearch = async () => {
        if (!search) return;
        try {
            const results = await movieApi.search(search);
            if (results.length > 0) setMovieId(results[0].id);
        } catch { }
    };

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white p-6 max-w-5xl mx-auto">
            <h1 className="text-3xl font-bold mb-6">Movie Connections</h1>
            <div className="flex gap-2 mb-6">
                <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                    placeholder="Search for a movie..."
                    className="flex-1 bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-white/40 focus:outline-none"
                />
                <button onClick={handleSearch} className="px-6 py-2 bg-white/10 hover:bg-white/20 rounded-lg">Search</button>
            </div>
            {movieId && <MovieConnections movieId={movieId} />}
        </div>
    );
}
