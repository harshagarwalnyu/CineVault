'use client';

import { useEffect, useState } from 'react';
import { movieApi } from '../api';

interface FilmEntry {
    id: number;
    title: string;
    release_date: string;
    vote_average: number;
    genres: string[] | string;
    poster_path: string;
}

interface DirectorData {
    director: string;
    total_films: number;
    average_rating: number;
    filmography: FilmEntry[];
}

interface Props {
    directorName: string;
}

export default function DirectorJourney({ directorName }: Props) {
    const [data, setData] = useState<DirectorData | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        movieApi.getDirectorFilmography(directorName)
            .then(setData)
            .catch(() => setData(null))
            .finally(() => setLoading(false));
    }, [directorName]);

    if (loading) return <div className="text-white/50">Loading filmography...</div>;
    if (!data) return <div className="text-white/50">Director not found</div>;

    return (
        <div className="space-y-6">
            <div>
                <h2 className="text-2xl font-bold text-white">{data.director}</h2>
                <p className="text-white/60">{data.total_films} films | Avg rating: {data.average_rating}/10</p>
            </div>
            <div className="relative border-l border-white/20 ml-4 space-y-6">
                {data.filmography.map((film) => (
                    <div key={film.id} className="ml-6 relative">
                        <div className="absolute -left-[1.6rem] top-1 w-3 h-3 rounded-full bg-white/40" />
                        <a href={`/movie/${film.id}`} className="flex gap-3 group">
                            <div className="w-16 aspect-[2/3] rounded bg-white/5 overflow-hidden flex-shrink-0">
                                {film.poster_path ? (
                                    <img src={`https://image.tmdb.org/t/p/w200${film.poster_path}`} alt={film.title} className="w-full h-full object-cover" />
                                ) : (
                                    <div className="w-full h-full flex items-center justify-center text-white/20 text-[10px]">{film.title}</div>
                                )}
                            </div>
                            <div>
                                <p className="text-white group-hover:text-white/80 font-medium">{film.title}</p>
                                <p className="text-sm text-white/50">{film.release_date?.slice(0, 4)} | {film.vote_average}/10</p>
                                <p className="text-xs text-white/40">{Array.isArray(film.genres) ? film.genres.join(', ') : film.genres}</p>
                            </div>
                        </a>
                    </div>
                ))}
            </div>
        </div>
    );
}
