'use client';

import Link from 'next/link';
import { m as motion, useScroll, useTransform } from 'framer-motion';
import { Compass, Play, Sparkles } from 'lucide-react';

import { Movie } from '@/api';
import MovieArtwork from '@/components/MovieArtwork';
import { formatMatchScore, formatRuntime, formatYear } from '@/utils';

interface HeroSectionProps {
    movie: Movie | null;
}

export default function HeroSection({ movie }: HeroSectionProps) {
    const { scrollY } = useScroll();
    const backgroundY = useTransform(scrollY, [0, 900], [0, 180]);
    const contentY = useTransform(scrollY, [0, 600], [0, 60]);

    if (!movie) {
        return (
            <section className="relative flex min-h-[92svh] items-end overflow-hidden px-4 pb-24 pt-36 sm:px-8 lg:px-12">
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(242,193,79,0.12),_transparent_30%),linear-gradient(160deg,_#09090b,_#171114_55%,_#26191b)]" />
                <div className="page-frame relative z-10">
                    <div className="eyebrow">Cinematic Discovery</div>
                    <h1 className="display-title mt-5 max-w-4xl text-[#f8f1e5]">
                        Movie discovery with editorial weight, fluid motion, and faster first paint.
                    </h1>
                    <p className="mt-6 max-w-2xl text-lg leading-relaxed text-[#cdbfa9]">
                        The backend is reachable, but hero artwork is unavailable for this slot right now. The experience still keeps the motion and search system live.
                    </p>
                    <div className="mt-8 flex flex-wrap gap-4">
                        <Link href="/search" className="button-primary px-6 py-3">
                            <Compass className="h-4 w-4" />
                            Search Catalog
                        </Link>
                    </div>
                </div>
            </section>
        );
    }

    const quality = movie.cinevault_qualities?.[movie.cinevault_qualities.length - 1] || '1080p.WEB';

    return (
        <section className="relative isolate min-h-[110svh] overflow-hidden px-4 pb-24 pt-28 sm:px-8 lg:px-12">
            <motion.div style={{ y: backgroundY }} className="absolute inset-0">
                <MovieArtwork
                    movie={movie}
                    variant="backdrop"
                    priority
                    sizes="100vw"
                    className="absolute inset-0"
                    imageClassName="object-cover object-center"
                />
                <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(7,7,9,0.24),rgba(7,7,9,0.55)_35%,rgba(7,7,9,0.95)_75%,#09090b)]" />
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(242,193,79,0.16),transparent_28%),radial-gradient(circle_at_80%_0%,rgba(160,71,71,0.22),transparent_30%)]" />
            </motion.div>

            <div className="page-frame relative z-10 grid min-h-[80svh] items-end gap-10 lg:grid-cols-[minmax(0,1fr)_360px]">
                <motion.div style={{ y: contentY }} className="max-w-4xl pb-8">
                    <div className="eyebrow">Featured Drop</div>
                    <h1 className="display-title mt-5 text-[#f8f1e5]">
                        {movie.title}
                    </h1>
                    <div className="mt-6 flex flex-wrap items-center gap-3 text-sm uppercase tracking-[0.22em] text-[#d6c8b2]">
                        <span>{formatYear(movie.release_date)}</span>
                        <span className="opacity-50">/</span>
                        <span>{formatRuntime(movie.runtime)}</span>
                        <span className="opacity-50">/</span>
                        <span>{quality}</span>
                        <span className="opacity-50">/</span>
                        <span>{formatMatchScore(movie.vote_average / 10)}</span>
                    </div>
                    <p className="mt-6 max-w-2xl text-lg leading-relaxed text-[#d8ccb8] sm:text-xl">
                        {movie.overview || 'A featured selection from the catalog with strong visual metadata and a polished detail page.'}
                    </p>

                    <div className="mt-8 flex flex-wrap gap-4">
                        <Link href={`/movie/${movie.id}`} className="button-primary px-6 py-3">
                            <Play className="h-4 w-4 fill-current" />
                            Enter Dossier
                        </Link>
                        <a href="#editorial-grid" className="button-secondary px-6 py-3">
                            <Sparkles className="h-4 w-4" />
                            Browse Editorial Cuts
                        </a>
                    </div>
                </motion.div>

                <motion.div
                    style={{ y: contentY }}
                    className="hidden justify-self-end rounded-[2rem] border border-white/10 bg-black/25 p-4 backdrop-blur-md lg:block"
                >
                    <div className="relative w-[320px] overflow-hidden rounded-[1.75rem]">
                        <MovieArtwork
                            movie={movie}
                            variant="poster"
                            priority
                            sizes="320px"
                            className="aspect-[2/3] w-full"
                            imageClassName="object-cover"
                        />
                        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black via-black/55 to-transparent p-5">
                            <div className="text-[0.65rem] uppercase tracking-[0.36em] text-[#f2c14f]">
                                Editor&apos;s Signal
                            </div>
                            <div className="mt-2 text-2xl font-semibold text-[#f8f1e5]">
                                {movie.title}
                            </div>
                        </div>
                    </div>
                </motion.div>
            </div>
        </section>
    );
}
