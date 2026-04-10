import Link from 'next/link';
import { notFound } from 'next/navigation';
import { ArrowUpRight, Languages, Sparkles, Star, Timer } from 'lucide-react';

import MovieCard from '@/components/MovieCard';
import MovieArtwork from '@/components/MovieArtwork';
import Navbar from '@/components/Navbar';
import { getGraphRelatedEntities, getMovieById, getRecommendationsByMovie } from '@/server-api';
import { formatRuntime, formatYear } from '@/utils';

export const revalidate = 300;

export default async function MoviePage({
    params,
}: {
    params: Promise<{ id: string }>;
}) {
    const { id } = await params;
    const movieId = Number(id);
    const movie = await getMovieById(movieId);

    if (!movie) {
        notFound();
    }

    const [recommendations, actors, directors] = await Promise.all([
        getRecommendationsByMovie(movieId),
        getGraphRelatedEntities(movie.title, 'actor'),
        getGraphRelatedEntities(movie.title, 'director'),
    ]);
    const graphRelated = [...actors, ...directors].slice(0, 8);

    return (
        <main className="min-h-screen overflow-x-hidden bg-[var(--color-bg)] text-[var(--color-foreground)]">
            <Navbar />

            <section className="relative isolate min-h-[74svh] overflow-hidden px-4 pt-28 sm:px-8 lg:px-12">
                <div className="absolute inset-0">
                    <MovieArtwork
                        movie={movie}
                        variant="backdrop"
                        priority
                        sizes="100vw"
                        className="absolute inset-0"
                    />
                    <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(9,9,11,0.24),rgba(9,9,11,0.72)_45%,#09090b)]" />
                    <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_18%,rgba(242,193,79,0.18),transparent_28%),radial-gradient(circle_at_80%_0%,rgba(143,45,45,0.2),transparent_30%)]" />
                </div>

                <div className="page-frame relative z-10 flex min-h-[62svh] items-end pb-16">
                    <div className="max-w-4xl">
                        <div className="eyebrow">Feature Dossier</div>
                        <h1 className="display-title mt-5 text-[#f8f1e5]">{movie.title}</h1>
                        <div className="mt-5 flex flex-wrap gap-3 text-sm uppercase tracking-[0.24em] text-[#d8ccb8]">
                            <span>{formatYear(movie.release_date)}</span>
                            <span className="opacity-50">/</span>
                            <span>{formatRuntime(movie.runtime)}</span>
                            <span className="opacity-50">/</span>
                            <span>{movie.original_language?.toUpperCase() || 'EN'}</span>
                        </div>
                        {movie.tagline ? (
                            <p className="mt-5 max-w-2xl text-lg leading-relaxed text-[#d8ccb8]">
                                {movie.tagline}
                            </p>
                        ) : null}
                    </div>
                </div>
            </section>

            <div className="page-frame relative z-20 -mt-[4.5rem] pb-24">
                <section className="grid gap-8 lg:grid-cols-[340px_minmax(0,1fr)]">
                    <aside className="space-y-5">
                        <div className="surface-panel p-4">
                            <MovieArtwork
                                movie={movie}
                                variant="poster"
                                priority
                                sizes="(max-width: 1024px) 60vw, 320px"
                                className="aspect-[2/3] w-full rounded-[1.75rem]"
                            />
                        </div>

                        <div className="surface-panel p-5">
                            <div className="eyebrow">Availability</div>
                            <div className="mt-4 flex flex-col gap-3">
                                {movie.homepage ? (
                                    <Link
                                        href={movie.homepage}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="button-primary w-full px-4 py-3 text-sm"
                                    >
                                        <ArrowUpRight className="h-4 w-4" />
                                        Open Homepage
                                    </Link>
                                ) : (
                                    <div className="rounded-[1.25rem] border border-white/10 bg-white/5 px-4 py-3 text-sm text-[#b9ab94]">
                                        No official homepage available in the current dataset.
                                    </div>
                                )}

                                {movie.cinevault_qualities?.length ? movie.cinevault_qualities.map((quality, index) => (
                                    <div
                                        key={`${quality}-${index}`}
                                        className="rounded-[1.25rem] border border-white/10 bg-black/[0.15] px-4 py-3 text-sm font-semibold text-[#f8f1e5]"
                                    >
                                        Download Signal: {quality}
                                    </div>
                                )) : null}
                            </div>
                        </div>
                    </aside>

                    <div className="space-y-6">
                        <div className="surface-panel p-6 sm:p-8">
                            <div className="grid gap-4 sm:grid-cols-3">
                                <div className="rounded-[1.4rem] border border-white/[0.08] bg-black/[0.18] p-5">
                                    <div className="flex items-center gap-2 text-xs uppercase tracking-[0.24em] text-[#c0b39b]">
                                        <Star className="h-4 w-4 text-[#f2c14f]" />
                                        Audience Pulse
                                    </div>
                                    <div className="mt-4 text-4xl font-semibold text-[#f8f1e5]">
                                        {movie.vote_average > 0 ? movie.vote_average.toFixed(1) : 'N/A'}
                                    </div>
                                    <p className="mt-2 text-sm text-[#b9ab94]">
                                        {movie.vote_count} votes ingested
                                    </p>
                                </div>
                                <div className="rounded-[1.4rem] border border-white/[0.08] bg-black/[0.18] p-5">
                                    <div className="flex items-center gap-2 text-xs uppercase tracking-[0.24em] text-[#c0b39b]">
                                        <Languages className="h-4 w-4 text-[#f2c14f]" />
                                        Language
                                    </div>
                                    <div className="mt-4 text-4xl font-semibold text-[#f8f1e5]">
                                        {movie.original_language?.toUpperCase() || 'EN'}
                                    </div>
                                    <p className="mt-2 text-sm text-[#b9ab94]">
                                        Primary metadata locale
                                    </p>
                                </div>
                                <div className="rounded-[1.4rem] border border-white/[0.08] bg-black/[0.18] p-5">
                                    <div className="flex items-center gap-2 text-xs uppercase tracking-[0.24em] text-[#c0b39b]">
                                        <Timer className="h-4 w-4 text-[#f2c14f]" />
                                        Runtime
                                    </div>
                                    <div className="mt-4 text-4xl font-semibold text-[#f8f1e5]">
                                        {movie.runtime || 'NA'}
                                    </div>
                                    <p className="mt-2 text-sm text-[#b9ab94]">
                                        Minutes in catalog
                                    </p>
                                </div>
                            </div>
                        </div>

                        <div className="surface-panel p-6 sm:p-8">
                            <div className="eyebrow">Synopsis</div>
                            <h2 className="mt-3 text-3xl font-semibold text-[#f8f1e5]">Story and metadata</h2>
                            <p className="mt-5 max-w-3xl text-base leading-relaxed text-[#d8ccb8] sm:text-lg">
                                {movie.overview || 'No synopsis is currently available for this title in the local dataset.'}
                            </p>

                            <div className="mt-6 grid gap-4 sm:grid-cols-2">
                                <div className="rounded-[1.4rem] border border-white/[0.08] bg-black/[0.18] p-5">
                                    <div className="text-xs uppercase tracking-[0.24em] text-[#c0b39b]">Genres</div>
                                    <div className="mt-3 text-lg font-semibold text-[#f8f1e5]">
                                        {Array.isArray(movie.genres) ? movie.genres.join(', ') : (movie.genres || 'Unclassified')}
                                    </div>
                                </div>
                                <div className="rounded-[1.4rem] border border-white/[0.08] bg-black/[0.18] p-5">
                                    <div className="text-xs uppercase tracking-[0.24em] text-[#c0b39b]">Identifiers</div>
                                    <div className="mt-3 text-sm leading-relaxed text-[#d8ccb8]">
                                        IMDb: {movie.imdb_id || 'Unknown'}
                                        <br />
                                        TMDB: {movie.tmdb_id || 'Unknown'}
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div className="surface-panel p-6 sm:p-8">
                            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.24em] text-[#c0b39b]">
                                <Sparkles className="h-4 w-4 text-[#f2c14f]" />
                                Knowledge Graph Insights
                            </div>
                            {graphRelated.length > 0 ? (
                                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                                    {graphRelated.map((entity, index) => (
                                        <div
                                            key={`${entity.name}-${entity.type}-${index}`}
                                            className="rounded-[1.25rem] border border-white/[0.08] bg-black/[0.18] px-4 py-3 text-sm"
                                        >
                                            <div className="font-semibold text-[#f8f1e5]">{entity.name}</div>
                                            <div className="mt-1 uppercase tracking-[0.18em] text-[#b9ab94]">
                                                {entity.type}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <p className="mt-5 text-sm leading-relaxed text-[#b9ab94]">
                                    No related entities were returned for this title in the current graph response.
                                </p>
                            )}
                        </div>

                        <section className="space-y-6">
                            <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                                <div>
                                    <div className="eyebrow">More Like This</div>
                                    <h2 className="text-3xl font-semibold text-[#f8f1e5] sm:text-4xl">
                                        Recommended next watches
                                    </h2>
                                </div>
                                <p className="max-w-xl text-sm leading-relaxed text-[#b9ab94]">
                                    Similarity candidates inherit the same poster rendering and card treatment as the main discovery views.
                                </p>
                            </div>

                            {recommendations.length > 0 ? (
                                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-4">
                                    {recommendations.slice(0, 4).map((recommendation, index) => (
                                        <MovieCard
                                            key={recommendation.id}
                                            movie={recommendation}
                                            priority={index < 2}
                                            showReason
                                        />
                                    ))}
                                </div>
                            ) : (
                                <div className="surface-panel p-6 text-sm text-[#b9ab94]">
                                    No recommendations were returned for this movie yet.
                                </div>
                            )}
                        </section>
                    </div>
                </section>
            </div>
        </main>
    );
}
