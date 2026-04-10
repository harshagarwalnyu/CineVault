'use client';

import Image from 'next/image';
import { useState } from 'react';

import type { Movie } from '@/api';
import { cn, resolveMovieArtwork, type ArtworkVariant } from '@/utils';

type ArtworkMovie = Pick<Movie, 'title' | 'poster_path' | 'backdrop_path'>;

interface MovieArtworkProps {
    movie: ArtworkMovie;
    variant?: ArtworkVariant;
    priority?: boolean;
    sizes?: string;
    className?: string;
    imageClassName?: string;
}

export default function MovieArtwork({
    movie,
    variant = 'poster',
    priority = false,
    sizes = '(max-width: 768px) 100vw, 50vw',
    className,
    imageClassName,
}: MovieArtworkProps) {
    const [attempt, setAttempt] = useState(0);
    const artwork = resolveMovieArtwork(movie, variant, attempt);

    return (
        <div className={cn('relative isolate overflow-hidden', className)}>
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(242,193,79,0.32),_transparent_42%),linear-gradient(180deg,_rgba(10,10,12,0.04),_rgba(10,10,12,0.72))]" />
            <Image
                src={artwork.src}
                alt={artwork.alt}
                fill
                priority={priority}
                sizes={sizes}
                className={cn('object-cover', imageClassName)}
                unoptimized={artwork.isFallback}
                onError={() => setAttempt((value) => value + 1)}
            />
            {artwork.isFallback && (
                <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/35 to-transparent p-5">
                    <div className="text-[0.65rem] uppercase tracking-[0.35em] text-[#f2c14f]/85">
                        No TMDB Art
                    </div>
                    <div className="mt-2 text-lg font-semibold text-[#f8f1e5]">
                        {movie.title || 'CineVault'}
                    </div>
                </div>
            )}
        </div>
    );
}
