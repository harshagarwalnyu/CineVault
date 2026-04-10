'use client';

import Link from 'next/link';
import { m as motion } from 'framer-motion';
import { ArrowUpRight, Sparkles, Star } from 'lucide-react';

import { Movie } from '@/api';
import MovieArtwork from '@/components/MovieArtwork';
import { cn, formatMatchScore, formatYear } from '@/utils';

interface MovieCardProps {
    movie: Movie;
    rank?: number;
    className?: string;
    priority?: boolean;
    showReason?: boolean;
}

export default function MovieCard({
    movie,
    rank,
    className,
    priority = false,
    showReason = false,
}: MovieCardProps) {
    const genres = Array.isArray(movie.genres)
        ? movie.genres.slice(0, 2)
        : typeof movie.genres === 'string'
            ? movie.genres.split(/[,|]/).map((g) => g.trim()).filter(Boolean).slice(0, 2)
            : [];
    const score = movie.hybrid_score && movie.hybrid_score > 0
        ? movie.hybrid_score / 100
        : movie.score || movie.vote_average / 10;

    return (
        <Link href={`/movie/${movie.id}`} className={cn('group block', className)}>
            <motion.article
                whileHover={{ y: -10, scale: 1.015 }}
                transition={{ type: 'spring', stiffness: 220, damping: 24 }}
                className="poster-card"
            >
                <div className="relative aspect-[2/3] overflow-hidden rounded-[1.75rem]">
                    <MovieArtwork
                        movie={movie}
                        variant="poster"
                        priority={priority}
                        sizes="(max-width: 768px) 50vw, (max-width: 1280px) 25vw, 18vw"
                        className="absolute inset-0"
                        imageClassName="transition duration-700 group-hover:scale-[1.04]"
                    />

                    <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(5,5,6,0.05),rgba(5,5,6,0.12)_40%,rgba(5,5,6,0.85))]" />
                    <div className="absolute inset-x-0 top-0 flex items-start justify-between p-4">
                        {rank ? (
                            <div className="rounded-full border border-[#f2c14f]/35 bg-black/[0.45] px-3 py-1 text-xs font-semibold tracking-[0.24em] text-[#f2c14f]">
                                #{rank}
                            </div>
                        ) : (
                            <div className="rounded-full border border-white/10 bg-black/[0.35] px-3 py-1 text-[0.68rem] uppercase tracking-[0.22em] text-[#efe6d5]">
                                {formatYear(movie.release_date)}
                            </div>
                        )}

                        {movie.cinevault_qualities?.length ? (
                            <div className="rounded-full border border-white/10 bg-black/[0.35] px-3 py-1 text-[0.68rem] uppercase tracking-[0.22em] text-[#efe6d5]">
                                {movie.cinevault_qualities[movie.cinevault_qualities.length - 1]}
                            </div>
                        ) : null}
                    </div>

                    <div className="absolute inset-x-0 bottom-0 space-y-3 p-4">
                        <div className="flex items-center gap-2 text-[0.68rem] uppercase tracking-[0.25em] text-[#c0b39b]">
                            <Sparkles className="h-3.5 w-3.5 text-[#f2c14f]" />
                            {formatMatchScore(score)}
                        </div>
                        <div>
                            <h3 className="line-clamp-2 text-xl font-semibold leading-tight text-[#f8f1e5]">
                                {movie.title}
                            </h3>
                            <div className="mt-2 flex flex-wrap gap-2">
                                {genres.length > 0 ? genres.map((genre) => (
                                    <span
                                        key={`${movie.id}-${genre}`}
                                        className="rounded-full border border-white/10 bg-white/[0.06] px-2.5 py-1 text-[0.68rem] uppercase tracking-[0.18em] text-[#d8ccb8]"
                                    >
                                        {genre}
                                    </span>
                                )) : (
                                    <span className="rounded-full border border-white/10 bg-white/[0.06] px-2.5 py-1 text-[0.68rem] uppercase tracking-[0.18em] text-[#d8ccb8]">
                                        Editorial
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>

                    <div className="pointer-events-none absolute inset-0 flex flex-col justify-between rounded-[1.75rem] border border-white/[0.08] opacity-0 transition duration-300 group-hover:opacity-100">
                        <div className="flex justify-end p-4">
                            <div className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-[#f2c14f]/35 bg-black/50 text-[#f2c14f]">
                                <ArrowUpRight className="h-4 w-4" />
                            </div>
                        </div>
                        <div className="p-4">
                            <div className="rounded-[1.25rem] border border-white/10 bg-black/[0.45] p-4 backdrop-blur-md">
                                <div className="flex items-center gap-2 text-sm text-[#f8f1e5]">
                                    <Star className="h-4 w-4 fill-[#f2c14f] text-[#f2c14f]" />
                                    <span className="font-semibold">
                                        {movie.vote_average > 0 ? movie.vote_average.toFixed(1) : 'N/A'}
                                    </span>
                                    <span className="text-[#c0b39b]">audience pulse</span>
                                </div>
                                <p className="mt-3 line-clamp-3 text-sm leading-relaxed text-[#d8ccb8]">
                                    {showReason && movie.reason
                                        ? movie.reason
                                        : movie.overview || 'Poster art is available, but plot detail has not been ingested for this title yet.'}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </motion.article>
        </Link>
    );
}
