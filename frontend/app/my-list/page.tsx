'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useSession } from 'next-auth/react';

import { Movie, movieApi } from '@/api';
import MovieArtwork from '@/components/MovieArtwork';
import MovieCard from '@/components/MovieCard';
import Navbar from '@/components/Navbar';
import PosterMosaic from '@/components/PosterMosaic';

export default function MyListPage() {
    const { data: session, status } = useSession();
    const [movies, setMovies] = useState<Movie[]>([]);
    const [previewMovies, setPreviewMovies] = useState<Movie[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let ignore = false;

        async function loadPreview() {
            try {
                const trending = await movieApi.getTrending(8);
                if (!ignore) {
                    setPreviewMovies(trending || []);
                }
            } catch (error) {
                console.error('Failed to load poster preview:', error);
            }
        }

        async function loadRecommendations() {
            if (!session?.user || !('id' in session.user) || !session.user.id) {
                if (!ignore) {
                    setLoading(false);
                }
                return;
            }

            try {
                const recommendations = await movieApi.getPersonalizedRecommendations(
                    Number(session.user.id),
                );
                if (!ignore) {
                    setMovies(recommendations);
                }
            } catch (error) {
                console.error('Failed to load personalized recommendations:', error);
                if (!ignore) {
                    setMovies([]);
                }
            } finally {
                if (!ignore) {
                    setLoading(false);
                }
            }
        }

        void loadPreview();

        if (status === 'loading') {
            return () => {
                ignore = true;
            };
        }

        void loadRecommendations();

        return () => {
            ignore = true;
        };
    }, [session, status]);

    const leadMovie = movies[0];

    return (
        <main className="min-h-screen overflow-x-hidden bg-[var(--color-bg)] text-[var(--color-foreground)]">
            <Navbar />

            <div className="page-frame pt-32 pb-24">
                <section className="grid gap-5 lg:grid-cols-[1fr_0.95fr]">
                    <div className="surface-panel p-6 sm:p-8">
                        <div className="eyebrow">Personal Signal</div>
                        <h1 className="mt-3 text-4xl font-semibold text-[#f8f1e5] sm:text-5xl">
                            Your list now lives inside the same cinematic system.
                        </h1>
                        <p className="mt-4 max-w-2xl text-base leading-relaxed text-[#c0b39b]">
                            Personalized recommendations keep the upgraded poster-first layout, motion language, and richer metadata treatment instead of falling back to a plain grid.
                        </p>
                        {!leadMovie ? (
                            <div className="mt-6 rounded-[1.5rem] border border-white/[0.08] bg-black/[0.18] p-5">
                                <div className="eyebrow">Status</div>
                                <p className="mt-3 text-base leading-relaxed text-[#c0b39b]">
                                    {status === 'loading'
                                        ? 'Loading account signals...'
                                        : status !== 'authenticated'
                                            ? 'Sign in to unlock personalized recommendations.'
                                            : 'Rate a few movies or explore the catalog to grow your recommendation profile.'}
                                </p>
                                {status !== 'authenticated' ? (
                                    <div className="mt-5">
                                        <Link href="/login" className="button-primary px-5 py-3 text-sm">
                                            Go To Login
                                        </Link>
                                    </div>
                                ) : null}
                            </div>
                        ) : null}
                    </div>

                    {!leadMovie ? (
                        <div className="surface-panel overflow-hidden p-0">
                            {previewMovies.length > 0 ? (
                                <div className="p-4 sm:p-5">
                                    <PosterMosaic movies={previewMovies} leadLabel="Preview Wall" />
                                </div>
                            ) : (
                                <div className="p-6 sm:p-8">
                                    <div className="eyebrow">Preview</div>
                                    <p className="mt-4 text-base leading-relaxed text-[#c0b39b]">
                                        Poster previews will appear here as soon as the catalog response lands.
                                    </p>
                                </div>
                            )}
                        </div>
                    ) : (
                        <div className="surface-panel overflow-hidden p-0">
                            <div className="relative min-h-[320px]">
                                <MovieArtwork
                                    movie={leadMovie}
                                    variant="backdrop"
                                    priority
                                    sizes="(max-width: 1024px) 100vw, 45vw"
                                    className="absolute inset-0"
                                />
                                <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(9,9,11,0.12),rgba(9,9,11,0.88))]" />
                                <div className="absolute inset-x-0 bottom-0 p-6 sm:p-8">
                                    <div className="eyebrow">Top Recommendation</div>
                                    <h2 className="mt-3 text-3xl font-semibold text-[#f8f1e5]">
                                        {leadMovie.title}
                                    </h2>
                                    <p className="mt-3 max-w-xl text-sm leading-relaxed text-[#d8ccb8]">
                                        {leadMovie.reason || leadMovie.overview || 'Your lead recommendation is ready for review.'}
                                    </p>
                                </div>
                            </div>
                        </div>
                    )}
                </section>

                {status === 'authenticated' && loading ? (
                    <div className="surface-panel mt-8 p-6 text-sm text-[#b9ab94]">
                        Loading your recommendations...
                    </div>
                ) : null}

                {status === 'authenticated' && !loading && movies.length > 0 ? (
                    <section className="mt-8 space-y-6">
                        <div>
                            <div className="eyebrow">Curated For You</div>
                            <h2 className="mt-2 text-3xl font-semibold text-[#f8f1e5] sm:text-4xl">
                                Personalized poster wall
                            </h2>
                        </div>
                        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                            {movies.map((movie, index) => (
                                <MovieCard
                                    key={movie.id}
                                    movie={movie}
                                    priority={index < 4}
                                    showReason
                                />
                            ))}
                        </div>
                    </section>
                ) : null}
            </div>
        </main>
    );
}
