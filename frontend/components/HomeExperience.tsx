'use client';

import dynamic from 'next/dynamic';
import { startTransition, useDeferredValue, useEffect, useState } from 'react';
import { m as motion } from 'framer-motion';
import { Search, SlidersHorizontal, Sparkles, Star } from 'lucide-react';

import { Movie, movieApi } from '@/api';
import HeroSection from '@/components/HeroSection';
import MovieCard from '@/components/MovieCard';
import PosterMosaic from '@/components/PosterMosaic';
import MovieRow from '@/components/MovieRow';
import Navbar from '@/components/Navbar';
import { SkeletonGrid } from '@/components/SkeletonCard';
import { useToast } from '@/components/Toast';
import { DISCOVERY_PROMPTS, HOME_SIGNAL_PILLS, SEARCH_DEBOUNCE_MS } from '@/constants';

const AgentChat = dynamic(() => import('@/components/AgentChat'), { ssr: false });

const applyFilters = (
    movies: Movie[],
    qualityFilter: string,
    genreFilter: string,
    minRatingFilter: string,
) =>
    movies.filter((movie) => {
        if (qualityFilter) {
            const qualities = movie.cinevault_qualities || [];
            if (!qualities.some((quality) => quality.includes(qualityFilter))) {
                return false;
            }
        }

        const genreStr = Array.isArray(movie.genres) ? movie.genres.join(' ') : (movie.genres || '');
        if (genreFilter && !genreStr.toLowerCase().includes(genreFilter.toLowerCase())) {
            return false;
        }

        if (minRatingFilter && movie.vote_average < Number(minRatingFilter)) {
            return false;
        }

        return true;
    });

interface HomeExperienceProps {
    initialTrending: Movie[];
    initialActionMovies: Movie[];
    initialLatestMovies: Movie[];
}

export default function HomeExperience({
    initialTrending,
    initialActionMovies,
    initialLatestMovies,
}: HomeExperienceProps) {
    const [searchQuery, setSearchQuery] = useState('');
    const [searchMode, setSearchMode] = useState<'title' | 'vibe'>('title');
    const [qualityFilter, setQualityFilter] = useState('');
    const [genreFilter, setGenreFilter] = useState('');
    const [minRatingFilter, setMinRatingFilter] = useState('');
    const [searchResults, setSearchResults] = useState<Movie[]>([]);
    const [isSearching, setIsSearching] = useState(false);

    const { toast } = useToast();
    const deferredQuery = useDeferredValue(searchQuery.trim());
    const heroMovie =
        initialTrending.find((movie) => movie.backdrop_path || movie.poster_path) ||
        initialLatestMovies.find((movie) => movie.backdrop_path || movie.poster_path) ||
        initialTrending[0] ||
        initialActionMovies[0] ||
        null;

    useEffect(() => {
        let ignore = false;

        if (!deferredQuery) {
            setSearchResults([]);
            setIsSearching(false);
            return undefined;
        }

        const timer = window.setTimeout(async () => {
            setIsSearching(true);
            try {
                const results = searchMode === 'vibe'
                    ? await movieApi.discover({
                        query: deferredQuery,
                        limit: 24,
                        diversity_factor: 0.28,
                    })
                    : await movieApi.search(deferredQuery);

                if (!ignore) {
                    startTransition(() => setSearchResults(results || []));
                }
            } catch (error) {
                console.error('Search failed:', error);
                toast('Search failed — check your connection and try again.', 'error');
                if (!ignore) {
                    startTransition(() => setSearchResults([]));
                }
            } finally {
                if (!ignore) {
                    setIsSearching(false);
                }
            }
        }, SEARCH_DEBOUNCE_MS);

        return () => {
            ignore = true;
            window.clearTimeout(timer);
        };
    }, [deferredQuery, searchMode]);

    const filteredTrending = applyFilters(
        initialTrending,
        qualityFilter,
        genreFilter,
        minRatingFilter,
    );
    const filteredAction = applyFilters(
        initialActionMovies,
        qualityFilter,
        genreFilter,
        minRatingFilter,
    );
    const filteredLatest = applyFilters(
        initialLatestMovies,
        qualityFilter,
        genreFilter,
        minRatingFilter,
    );
    const filteredSearchResults = applyFilters(
        searchResults,
        qualityFilter,
        genreFilter,
        minRatingFilter,
    );
    const showcaseMovies = Array.from(
        new Map(
            [...filteredLatest, ...filteredTrending, ...filteredAction].map((movie) => [movie.id, movie]),
        ).values(),
    );

    return (
        <main className="min-h-screen overflow-x-hidden bg-[var(--color-bg)] text-[var(--color-foreground)]">
            <Navbar />
            <HeroSection movie={heroMovie} />

            <div className="page-frame relative z-20 -mt-[4.5rem] pb-24">
                <motion.section
                    initial={{ opacity: 0, y: 32 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6, ease: 'easeOut' }}
                    className="surface-panel sticky top-24 z-30 mb-12 overflow-hidden p-5 sm:p-6"
                >
                    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
                        <div className="space-y-4">
                            <div className="eyebrow">Live Search Console</div>
                            <div className="relative">
                                <Search className="pointer-events-none absolute left-5 top-1/2 h-5 w-5 -translate-y-1/2 text-[#8b8173]" />
                                <input
                                    className="w-full rounded-full border border-white/10 bg-black/25 px-14 py-4 text-base text-[#f8f1e5] outline-none transition focus:border-[#f2c14f]/35"
                                    placeholder={
                                        searchMode === 'vibe'
                                            ? 'Describe tone, tempo, plot shape, or emotional finish...'
                                            : 'Search titles, genres, directors, or cast...'
                                    }
                                    value={searchQuery}
                                    onChange={(event) => setSearchQuery(event.target.value)}
                                />
                            </div>
                            <div className="flex flex-wrap gap-3">
                                {DISCOVERY_PROMPTS.map((prompt) => (
                                    <button
                                        key={prompt}
                                        type="button"
                                        onClick={() => {
                                            setSearchMode('vibe');
                                            setSearchQuery(prompt);
                                        }}
                                        className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-[#d8ccb8] transition hover:border-[#f2c14f]/28 hover:text-[#f8f1e5]"
                                    >
                                        {prompt}
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div className="grid gap-4 md:grid-cols-2">
                            <div className="rounded-[1.5rem] border border-white/[0.08] bg-black/[0.22] p-4">
                                <div className="flex items-center gap-2 text-xs uppercase tracking-[0.25em] text-[#c0b39b]">
                                    <SlidersHorizontal className="h-4 w-4 text-[#f2c14f]" />
                                    Mode
                                </div>
                                <div className="mt-4 flex gap-2">
                                    <button
                                        type="button"
                                        className={`segmented-button ${searchMode === 'title' ? 'segmented-button-active' : ''}`}
                                        onClick={() => setSearchMode('title')}
                                    >
                                        Title Search
                                    </button>
                                    <button
                                        type="button"
                                        className={`segmented-button ${searchMode === 'vibe' ? 'segmented-button-active' : ''}`}
                                        onClick={() => setSearchMode('vibe')}
                                    >
                                        Hybrid Discover
                                    </button>
                                </div>
                                <div className="mt-4 flex flex-wrap gap-2">
                                    {HOME_SIGNAL_PILLS.map((pill) => (
                                        <span key={pill} className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs uppercase tracking-[0.2em] text-[#b9ab94]">
                                            {pill}
                                        </span>
                                    ))}
                                </div>
                            </div>

                            <div className="rounded-[1.5rem] border border-white/[0.08] bg-black/[0.22] p-4">
                                <div className="flex items-center gap-2 text-xs uppercase tracking-[0.25em] text-[#c0b39b]">
                                    <Sparkles className="h-4 w-4 text-[#f2c14f]" />
                                    Refine
                                </div>
                                <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
                                    <select
                                        className="rounded-2xl border border-white/10 bg-black/25 px-3 py-3 text-sm text-[#f8f1e5] outline-none"
                                        value={qualityFilter}
                                        onChange={(event) => setQualityFilter(event.target.value)}
                                    >
                                        <option value="">All quality</option>
                                        <option value="720p">720p</option>
                                        <option value="1080p">1080p</option>
                                        <option value="2160p">2160p</option>
                                    </select>
                                    <select
                                        className="rounded-2xl border border-white/10 bg-black/25 px-3 py-3 text-sm text-[#f8f1e5] outline-none"
                                        value={genreFilter}
                                        onChange={(event) => setGenreFilter(event.target.value)}
                                    >
                                        <option value="">All genres</option>
                                        <option value="Action">Action</option>
                                        <option value="Drama">Drama</option>
                                        <option value="Science Fiction">Sci-Fi</option>
                                        <option value="Thriller">Thriller</option>
                                    </select>
                                    <select
                                        className="rounded-2xl border border-white/10 bg-black/25 px-3 py-3 text-sm text-[#f8f1e5] outline-none"
                                        value={minRatingFilter}
                                        onChange={(event) => setMinRatingFilter(event.target.value)}
                                    >
                                        <option value="">All ratings</option>
                                        <option value="9">9+</option>
                                        <option value="8">8+</option>
                                        <option value="7">7+</option>
                                    </select>
                                </div>
                            </div>
                        </div>
                    </div>
                </motion.section>

                {searchQuery ? (
                    <section className="space-y-8">
                        <div className="flex flex-col gap-4 border-b border-white/[0.08] pb-6 md:flex-row md:items-end md:justify-between">
                            <div>
                                <div className="eyebrow">Search Output</div>
                                <h2 className="mt-2 text-3xl font-semibold text-[#f8f1e5] sm:text-4xl">
                                    {isSearching
                                        ? 'Searching the catalog...'
                                        : `${filteredSearchResults.length} results for "${searchQuery}"`}
                                </h2>
                            </div>
                            <p className="max-w-xl text-sm leading-relaxed text-[#b9ab94]">
                                {searchMode === 'vibe'
                                    ? 'Hybrid discover weighs natural language, rating priors, and diversity to avoid stale clones.'
                                    : 'Title mode stays precise, fast, and poster-first for scanning.'}
                            </p>
                        </div>

                        {isSearching ? (
                            <SkeletonGrid count={8} />
                        ) : filteredSearchResults.length > 0 ? (
                            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                                {filteredSearchResults.map((movie, index) => (
                                    <MovieCard
                                        key={movie.id}
                                        movie={movie}
                                        priority={index < 4}
                                        showReason={searchMode === 'vibe'}
                                    />
                                ))}
                            </div>
                        ) : !isSearching ? (
                            <div className="grid gap-5 xl:grid-cols-[0.78fr_1.22fr]">
                                <div className="surface-panel p-8">
                                    <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border border-[#f2c14f]/28 bg-[#f2c14f]/10 text-[#f2c14f] xl:mx-0">
                                        <Star className="h-5 w-5" />
                                    </div>
                                    <h3 className="mt-5 text-2xl font-semibold text-[#f8f1e5]">
                                        Nothing matched this pass.
                                    </h3>
                                    <p className="mt-3 max-w-xl text-sm leading-relaxed text-[#b9ab94]">
                                        Try easing the filters, switching to Hybrid Discover, or describing the tone rather than plot details.
                                    </p>
                                    <div className="mt-6 flex flex-wrap gap-3">
                                        {DISCOVERY_PROMPTS.slice(0, 2).map((prompt) => (
                                            <button
                                                key={prompt}
                                                type="button"
                                                onClick={() => {
                                                    setSearchMode('vibe');
                                                    setSearchQuery(prompt);
                                                }}
                                                className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-[#d8ccb8] transition hover:border-[#f2c14f]/28 hover:text-[#f8f1e5]"
                                            >
                                                {prompt}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                                <PosterMosaic movies={showcaseMovies} leadLabel="Try These Instead" />
                            </div>
                        ) : null}
                    </section>
                ) : (
                    <div className="space-y-14">
                        <section className="grid gap-5 xl:grid-cols-[0.78fr_1.22fr]">
                            <div className="surface-panel p-6 sm:p-8">
                                <div className="eyebrow">Why It Feels Different</div>
                                <h2 className="mt-3 text-3xl font-semibold text-[#f8f1e5] sm:text-4xl">
                                    The catalog opens with live posters instead of static explanation blocks.
                                </h2>
                                <p className="mt-4 max-w-2xl text-base leading-relaxed text-[#c0b39b]">
                                    Discovery now starts from artwork-rich titles, a live backdrop hero, and a showcase reel built from the same API data powering search and recommendations.
                                </p>
                                <div className="mt-6 grid gap-3 sm:grid-cols-3">
                                    <div className="rounded-[1.4rem] border border-white/[0.08] bg-black/[0.18] p-4">
                                        <div className="text-[0.68rem] uppercase tracking-[0.28em] text-[#c0b39b]">Live Titles</div>
                                        <div className="mt-3 text-3xl font-semibold text-[#f8f1e5]">
                                            {showcaseMovies.length}
                                        </div>
                                        <p className="mt-2 text-sm text-[#b9ab94]">Poster-led selections assembled from trending, latest, and action rails.</p>
                                    </div>
                                    <div className="rounded-[1.4rem] border border-white/[0.08] bg-black/[0.18] p-4">
                                        <div className="text-[0.68rem] uppercase tracking-[0.28em] text-[#c0b39b]">Artwork</div>
                                        <div className="mt-3 text-3xl font-semibold text-[#f8f1e5]">
                                            TMDB
                                        </div>
                                        <p className="mt-2 text-sm text-[#b9ab94]">Backdrop and poster fallbacks now stay visible across hero, rails, and search results.</p>
                                    </div>
                                    <div className="rounded-[1.4rem] border border-white/[0.08] bg-black/[0.18] p-4">
                                        <div className="text-[0.68rem] uppercase tracking-[0.28em] text-[#c0b39b]">Motion</div>
                                        <div className="mt-3 text-3xl font-semibold text-[#f8f1e5]">
                                            Lenis
                                        </div>
                                        <p className="mt-2 text-sm text-[#b9ab94]">The poster wall keeps the same restrained movement language as the rest of the app.</p>
                                    </div>
                                </div>
                            </div>
                            <PosterMosaic movies={showcaseMovies} leadLabel="Live Showcase" />
                        </section>

                        <MovieRow
                            eyebrow="Popular Right Now"
                            title="Current downloads and high-velocity picks."
                            description="A ranked rail built for fast poster scanning with stronger hover detail and motion-safe transitions."
                            movies={filteredTrending.slice(0, 12)}
                            showRank
                        />

                        <MovieRow
                            eyebrow="New Arrivals"
                            title="Fresh from the theaters."
                            description="The latest and greatest releases from 2025 and 2026."
                            movies={filteredLatest.slice(0, 12)}
                        />

                        <section id="editorial-grid" className="space-y-6">
                            <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                                <div>
                                    <div className="eyebrow">Editorial Grid</div>
                                    <h2 className="text-3xl font-semibold text-[#f8f1e5] sm:text-4xl">
                                        Posters are part of the interface now.
                                    </h2>
                                </div>
                                <p className="max-w-xl text-sm leading-relaxed text-[#b9ab94]">
                                    Records with TMDB paths now surface posters or backdrops first. Missing records fall back to branded art instead of blank space.
                                </p>
                            </div>
                            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-4">
                                {filteredTrending.slice(0, 8).map((movie, index) => (
                                    <MovieCard key={movie.id} movie={movie} priority={index < 4} />
                                ))}
                            </div>
                        </section>

                        <MovieRow
                            eyebrow="Action Voltage"
                            title="Punchier titles for high-tempo sessions."
                            description="Genre-specific picks still inherit the same motion, poster handling, and metadata treatment."
                            movies={filteredAction.slice(0, 10)}
                        />

                        <section id="signals" className="grid gap-5 lg:grid-cols-3">
                            <div className="surface-panel p-6">
                                <div className="eyebrow">Signal 01</div>
                                <h3 className="mt-3 text-2xl font-semibold text-[#f8f1e5]">
                                    Cinematic shell
                                </h3>
                                <p className="mt-3 text-sm leading-relaxed text-[#b9ab94]">
                                    A single visual system now spans nav, heroes, rails, detail views, and account routes.
                                </p>
                            </div>
                            <div className="surface-panel p-6">
                                <div className="eyebrow">Signal 02</div>
                                <h3 className="mt-3 text-2xl font-semibold text-[#f8f1e5]">
                                    Search-first command dock
                                </h3>
                                <p className="mt-3 text-sm leading-relaxed text-[#b9ab94]">
                                    Discovery stays visible and sticky, so users can pivot without losing context mid-scroll.
                                </p>
                            </div>
                            <div className="surface-panel p-6">
                                <div className="eyebrow">Signal 03</div>
                                <h3 className="mt-3 text-2xl font-semibold text-[#f8f1e5]">
                                    Motion with restraint
                                </h3>
                                <p className="mt-3 text-sm leading-relaxed text-[#b9ab94]">
                                    Motion is used for depth, hierarchy, and scan speed, not for decorative lag.
                                </p>
                            </div>
                        </section>
                    </div>
                )}
            </div>

            <AgentChat />
        </main>
    );
}
