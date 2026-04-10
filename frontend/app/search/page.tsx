'use client';

import { startTransition, useEffect, useState } from 'react';
import { Search as SearchIcon, Sparkles, SlidersHorizontal, ChevronDown, ChevronUp } from 'lucide-react';

import { Movie, SearchFilters, movieApi } from '@/api';
import MovieCard from '@/components/MovieCard';
import Navbar from '@/components/Navbar';
import PosterMosaic from '@/components/PosterMosaic';
import { SkeletonGrid } from '@/components/SkeletonCard';
import { useToast } from '@/components/Toast';
import { DISCOVERY_PROMPTS } from '@/constants';

function buildActiveFilters(
    query: string,
    genre: string,
    director: string,
    actor: string,
    yearFrom: string,
    yearTo: string,
    minRating: number,
    maxRating: number,
    sortBy: SearchFilters['sort_by'],
    sortOrder: SearchFilters['sort_order'],
    page: number,
): SearchFilters {
    const filters: SearchFilters = {};

    if (query)    filters.q = query;
    if (genre)    filters.genre = genre;
    if (director) filters.director = director;
    if (actor)    filters.actor = actor;

    const yf = parseInt(yearFrom, 10);
    const yt = parseInt(yearTo, 10);
    if (!isNaN(yf)) filters.year_from = yf;
    if (!isNaN(yt)) filters.year_to = yt;

    if (minRating > 0)  filters.min_rating = minRating;
    if (maxRating < 10) filters.max_rating = maxRating;

    filters.sort_by = sortBy;
    filters.sort_order = sortOrder;
    filters.page = page;

    return filters;
}

export default function SearchPage() {
    const [query, setQuery] = useState('');
    const [results, setResults] = useState<Movie[]>([]);
    const [isSemantic, setIsSemantic] = useState(false);
    const [isVisual, setIsVisual] = useState(false);
    const [useRerank, setUseRerank] = useState(false);
    const [loading, setLoading] = useState(false);
    const [showcaseMovies, setShowcaseMovies] = useState<Movie[]>([]);

    // Filter state
    const [filtersOpen, setFiltersOpen] = useState(false);
    const [genre, setGenre] = useState('');
    const [director, setDirector] = useState('');
    const [actor, setActor] = useState('');
    const [yearFrom, setYearFrom] = useState('');
    const [yearTo, setYearTo] = useState('');
    const [minRating, setMinRating] = useState(0);
    const [maxRating, setMaxRating] = useState(10);
    const [sortBy, setSortBy] = useState<SearchFilters['sort_by']>('vote_average');
    const [sortOrder, setSortOrder] = useState<SearchFilters['sort_order']>('desc');
    const [genres, setGenres] = useState<{ name: string }[]>([]);
    const [totalResults, setTotalResults] = useState(0);
    const [page, setPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);

    const { toast } = useToast();
    const hasActiveFilters = genre || director || actor || yearFrom || yearTo || minRating > 0 || maxRating < 10;

    useEffect(() => {
        let ignore = false;

        const loadInitial = async () => {
            try {
                const [trending, genreList] = await Promise.all([
                    movieApi.getTrending(8),
                    movieApi.getGenres(),
                ]);
                if (!ignore) {
                    startTransition(() => {
                        setShowcaseMovies(trending || []);
                        setGenres(genreList || []);
                    });
                }
            } catch (error) {
                console.error('Failed to load search showcase:', error);
            }
        };

        void loadInitial();

        return () => {
            ignore = true;
        };
    }, []);

    const handleSearch = async (event?: React.FormEvent, pageOverride?: number) => {
        if (event) event.preventDefault();
        const currentPage = pageOverride ?? 1;
        if (!pageOverride) setPage(1);

        // Semantic/visual modes ignore filters
        if (isVisual || isSemantic) {
            if (!query.trim()) return;
            setLoading(true);
            try {
                const searchResults = isVisual
                    ? await movieApi.visualSearch(query)
                    : await movieApi.discover({
                        query,
                        limit: 24,
                        diversity_factor: 0.3,
                        use_reranker: useRerank,
                    });
                startTransition(() => {
                    setResults(searchResults);
                    setTotalResults(searchResults.length);
                    setTotalPages(1);
                });
            } catch (error) {
                console.error('Search failed:', error);
                toast('Search failed — check your connection and try again.', 'error');
                startTransition(() => setResults([]));
            } finally {
                setLoading(false);
            }
            return;
        }

        // Title mode with filters
        const filters = buildActiveFilters(query, genre, director, actor, yearFrom, yearTo, minRating, maxRating, sortBy, sortOrder, currentPage);
        if (!query.trim() && !hasActiveFilters) return;

        setLoading(true);
        try {
            const data = await movieApi.searchFiltered(filters);
            startTransition(() => {
                setResults(data.items);
                setTotalResults(data.total);
                setPage(data.page);
                setTotalPages(data.total_pages);
            });
        } catch (error) {
            console.error('Search failed:', error);
            toast('Search failed — check your connection and try again.', 'error');
            startTransition(() => setResults([]));
        } finally {
            setLoading(false);
        }
    };

    const clearFilters = () => {
        setGenre(''); setDirector(''); setActor('');
        setYearFrom(''); setYearTo('');
        setMinRating(0); setMaxRating(10);
        setSortBy('vote_average'); setSortOrder('desc');
    };

    return (
        <main className="min-h-screen overflow-x-hidden bg-[var(--color-bg)] text-[var(--color-foreground)]">
            <Navbar />

            <div className="page-frame pt-32 pb-24">
                <section className="grid gap-5 lg:grid-cols-[1.05fr_0.95fr]">
                    <div className="surface-panel p-6 sm:p-8">
                        <div className="eyebrow">Search Lab</div>
                        <h1 className="mt-3 text-4xl font-semibold text-[#f8f1e5] sm:text-5xl">
                            Run title, hybrid, or visual discovery from one command deck.
                        </h1>
                        <p className="mt-4 max-w-2xl text-base leading-relaxed text-[#c0b39b]">
                            This route is tuned for deliberate search sessions, not just homepage grazing. Describe imagery, plot pressure, or emotional finish and pivot between modes instantly.
                        </p>
                    </div>

                    <div className="surface-panel p-6 sm:p-8">
                        <div className="eyebrow">Prompt Starters</div>
                        <div className="mt-4 flex flex-wrap gap-3">
                            {DISCOVERY_PROMPTS.map((prompt) => (
                                <button
                                    key={prompt}
                                    type="button"
                                    onClick={() => {
                                        setQuery(prompt);
                                        setIsSemantic(true);
                                        setIsVisual(false);
                                    }}
                                    className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-[#d8ccb8] transition hover:border-[#f2c14f]/28 hover:text-[#f8f1e5]"
                                >
                                    {prompt}
                                </button>
                            ))}
                        </div>
                    </div>
                </section>

                <section className="surface-panel mt-8 p-6 sm:p-8">
                    <form onSubmit={handleSearch} className="space-y-5">
                        <div className="relative">
                            <SearchIcon className="pointer-events-none absolute left-5 top-1/2 h-5 w-5 -translate-y-1/2 text-[#8b8173]" />
                            <input
                                type="text"
                                value={query}
                                onChange={(event) => setQuery(event.target.value)}
                                placeholder={
                                    isVisual
                                        ? "Visual style, imagery, or atmosphere..."
                                        : isSemantic
                                            ? "Describe the vibe, plot arc, or emotional landing..."
                                            : "Search titles, genres, people, or franchises..."
                                }
                                className="w-full rounded-full border border-white/10 bg-black/25 px-14 py-4 text-base text-[#f8f1e5] outline-none transition focus:border-[#f2c14f]/35"
                            />
                            <button type="submit" className="button-primary absolute right-2 top-2 px-5 py-2.5 text-sm">
                                Search
                            </button>
                        </div>

                        <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
                            <div className="flex flex-wrap gap-2">
                                <button
                                    type="button"
                                    onClick={() => {
                                        setIsSemantic(false);
                                        setIsVisual(false);
                                    }}
                                    className={`segmented-button w-full sm:w-auto ${!isSemantic && !isVisual ? 'segmented-button-active' : ''}`}
                                >
                                    Title
                                </button>
                                <button
                                    type="button"
                                    onClick={() => {
                                        setIsSemantic(true);
                                        setIsVisual(false);
                                    }}
                                    className={`segmented-button w-full sm:w-auto ${isSemantic ? 'segmented-button-active' : ''}`}
                                >
                                    <Sparkles className="h-4 w-4" />
                                    Hybrid Discover
                                </button>
                                <button
                                    type="button"
                                    onClick={() => {
                                        setIsVisual(true);
                                        setIsSemantic(false);
                                    }}
                                    className={`segmented-button w-full sm:w-auto ${isVisual ? 'segmented-button-active' : ''}`}
                                >
                                    Visual Search
                                </button>
                            </div>

                            {isSemantic ? (
                                <button
                                    type="button"
                                    onClick={() => setUseRerank(!useRerank)}
                                    className={`segmented-button w-full sm:w-auto ${useRerank ? 'segmented-button-active' : ''}`}
                                >
                                    Dense Rerank
                                </button>
                            ) : null}
                        </div>
                    </form>
                </section>

                {/* Filter panel — only visible in Title mode */}
                {!isSemantic && !isVisual && (
                    <section className="surface-panel mt-8 p-6 sm:p-8">
                        <button
                            type="button"
                            onClick={() => setFiltersOpen(!filtersOpen)}
                            className="flex w-full items-center justify-between text-left"
                        >
                            <div className="flex items-center gap-3">
                                <SlidersHorizontal className="h-5 w-5 text-[#f2c14f]" />
                                <span className="text-lg font-semibold text-[#f8f1e5]">Filters</span>
                                {hasActiveFilters && (
                                    <span className="rounded-full bg-[#f2c14f]/20 px-2.5 py-0.5 text-xs font-bold text-[#f2c14f]">Active</span>
                                )}
                            </div>
                            {filtersOpen ? <ChevronUp className="h-5 w-5 text-[#8b8173]" /> : <ChevronDown className="h-5 w-5 text-[#8b8173]" />}
                        </button>

                        {filtersOpen && (
                            <div className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
                                {/* Genre */}
                                <div>
                                    <label className="eyebrow mb-2 block">Genre</label>
                                    <select
                                        value={genre}
                                        onChange={(e) => setGenre(e.target.value)}
                                        className="w-full rounded-xl border border-white/10 bg-black/25 px-4 py-3 text-sm text-[#f8f1e5] outline-none transition focus:border-[#f2c14f]/35"
                                    >
                                        <option value="">All Genres</option>
                                        {genres.map((g) => (
                                            <option key={g.name} value={g.name}>{g.name}</option>
                                        ))}
                                    </select>
                                </div>

                                {/* Director */}
                                <div>
                                    <label className="eyebrow mb-2 block">Director</label>
                                    <input
                                        type="text"
                                        value={director}
                                        onChange={(e) => setDirector(e.target.value)}
                                        placeholder="e.g. Nolan, Spielberg"
                                        className="w-full rounded-xl border border-white/10 bg-black/25 px-4 py-3 text-sm text-[#f8f1e5] outline-none transition focus:border-[#f2c14f]/35"
                                    />
                                </div>

                                {/* Actor */}
                                <div>
                                    <label className="eyebrow mb-2 block">Actor</label>
                                    <input
                                        type="text"
                                        value={actor}
                                        onChange={(e) => setActor(e.target.value)}
                                        placeholder="e.g. DiCaprio, Portman"
                                        className="w-full rounded-xl border border-white/10 bg-black/25 px-4 py-3 text-sm text-[#f8f1e5] outline-none transition focus:border-[#f2c14f]/35"
                                    />
                                </div>

                                {/* Sort By */}
                                <div>
                                    <label className="eyebrow mb-2 block">Sort By</label>
                                    <div className="flex gap-2">
                                        <select
                                            value={sortBy}
                                            onChange={(e) => setSortBy(e.target.value as SearchFilters['sort_by'])}
                                            className="flex-1 rounded-xl border border-white/10 bg-black/25 px-4 py-3 text-sm text-[#f8f1e5] outline-none transition focus:border-[#f2c14f]/35"
                                        >
                                            <option value="vote_average">Rating</option>
                                            <option value="release_date">Release Date</option>
                                            <option value="title">Title</option>
                                            <option value="vote_count">Popularity</option>
                                        </select>
                                        <button
                                            type="button"
                                            onClick={() => setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')}
                                            className="rounded-xl border border-white/10 bg-black/25 px-3 py-3 text-xs font-bold text-[#d8ccb8] transition hover:border-[#f2c14f]/35"
                                        >
                                            {sortOrder === 'desc' ? 'DESC' : 'ASC'}
                                        </button>
                                    </div>
                                </div>

                                {/* Year Range */}
                                <div>
                                    <label className="eyebrow mb-2 block">Year Range</label>
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="number"
                                            value={yearFrom}
                                            onChange={(e) => setYearFrom(e.target.value)}
                                            placeholder="From"
                                            min={1888} max={2030}
                                            className="w-full rounded-xl border border-white/10 bg-black/25 px-4 py-3 text-sm text-[#f8f1e5] outline-none transition focus:border-[#f2c14f]/35"
                                        />
                                        <span className="text-[#8b8173]">–</span>
                                        <input
                                            type="number"
                                            value={yearTo}
                                            onChange={(e) => setYearTo(e.target.value)}
                                            placeholder="To"
                                            min={1888} max={2030}
                                            className="w-full rounded-xl border border-white/10 bg-black/25 px-4 py-3 text-sm text-[#f8f1e5] outline-none transition focus:border-[#f2c14f]/35"
                                        />
                                    </div>
                                </div>

                                {/* Rating Range */}
                                <div className="sm:col-span-2">
                                    <label className="eyebrow mb-2 block">Rating: {minRating} – {maxRating}</label>
                                    <div className="flex items-center gap-4">
                                        <input
                                            type="range"
                                            min={0} max={10} step={0.5}
                                            value={minRating}
                                            onChange={(e) => setMinRating(Number(e.target.value))}
                                            className="flex-1 accent-[#f2c14f]"
                                        />
                                        <input
                                            type="range"
                                            min={0} max={10} step={0.5}
                                            value={maxRating}
                                            onChange={(e) => setMaxRating(Number(e.target.value))}
                                            className="flex-1 accent-[#f2c14f]"
                                        />
                                    </div>
                                </div>

                                {/* Clear + Apply */}
                                <div className="flex items-end gap-3 sm:col-span-2 lg:col-span-1">
                                    <button
                                        type="button"
                                        onClick={clearFilters}
                                        className="button-secondary flex-1 py-3 text-sm"
                                    >
                                        Clear
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => handleSearch()}
                                        className="button-primary flex-1 py-3 text-sm"
                                    >
                                        Apply
                                    </button>
                                </div>
                            </div>
                        )}
                    </section>
                )}

                <section className="mt-8 space-y-6">
                    <div className="flex flex-col gap-3 border-b border-white/[0.08] pb-5 md:flex-row md:items-end md:justify-between">
                        <div>
                            <div className="eyebrow">Results</div>
                            <h2 className="mt-2 text-3xl font-semibold text-[#f8f1e5] sm:text-4xl">
                                {loading ? 'Searching the catalog...' : (query || hasActiveFilters) ? `${totalResults} results` : 'Start a search'}
                            </h2>
                        </div>
                        <p className="max-w-xl text-sm leading-relaxed text-[#b9ab94]">
                            {isVisual
                                ? 'Visual mode uses aesthetic descriptors and imagery cues.'
                                : isSemantic
                                    ? 'Hybrid mode blends semantic intent, ranking, and diversity.'
                                    : 'Title mode stays close to exact catalog metadata.'}
                        </p>
                    </div>

                    {loading ? (
                        <SkeletonGrid count={10} />
                    ) : results.length > 0 ? (
                        <>
                            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                                {results.map((movie, index) => (
                                    <MovieCard
                                        key={movie.id}
                                        movie={movie}
                                        priority={index < 4}
                                        showReason={isSemantic}
                                    />
                                ))}
                            </div>
                            {/* Pagination — title mode only */}
                            {!isSemantic && !isVisual && totalPages > 1 && (
                                <div className="flex items-center justify-center gap-4 pt-4">
                                    <button
                                        type="button"
                                        disabled={page <= 1}
                                        onClick={() => { setPage(page - 1); handleSearch(undefined, page - 1); }}
                                        className="button-secondary px-5 py-2.5 text-sm disabled:opacity-30"
                                    >
                                        Previous
                                    </button>
                                    <span className="text-sm text-[#b9ab94]">
                                        Page {page} of {totalPages}
                                    </span>
                                    <button
                                        type="button"
                                        disabled={page >= totalPages}
                                        onClick={() => { setPage(page + 1); handleSearch(undefined, page + 1); }}
                                        className="button-secondary px-5 py-2.5 text-sm disabled:opacity-30"
                                    >
                                        Next
                                    </button>
                                </div>
                            )}
                        </>
                    ) : (query || hasActiveFilters) && !loading ? (
                        <div className="grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
                            <div className="surface-panel p-8">
                                <div className="eyebrow">No Match</div>
                                <h3 className="mt-3 text-3xl font-semibold text-[#f8f1e5]">
                                    No titles matched this search.
                                </h3>
                                <p className="mt-3 max-w-xl text-sm leading-relaxed text-[#b9ab94]">
                                    Try describing the mood instead of exact plot details, or switch back to title mode for precise matching.
                                </p>
                                <div className="mt-6 flex flex-wrap gap-3">
                                    {DISCOVERY_PROMPTS.slice(0, 2).map((prompt) => (
                                        <button
                                            key={prompt}
                                            type="button"
                                            onClick={() => {
                                                setQuery(prompt);
                                                setIsSemantic(true);
                                                setIsVisual(false);
                                            }}
                                            className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-[#d8ccb8] transition hover:border-[#f2c14f]/28 hover:text-[#f8f1e5]"
                                        >
                                            {prompt}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <PosterMosaic movies={showcaseMovies} leadLabel="Catalog Preview" />
                        </div>
                    ) : !query && !hasActiveFilters ? (
                        <div className="grid gap-5 xl:grid-cols-[1.18fr_0.82fr]">
                            <PosterMosaic movies={showcaseMovies} leadLabel="Search Preview" />
                            <div className="surface-panel p-6 sm:p-8">
                                <div className="eyebrow">Mode Deck</div>
                                <h3 className="mt-3 text-3xl font-semibold text-[#f8f1e5]">
                                    Search starts from posters now, not empty explanation cards.
                                </h3>
                                <p className="mt-4 text-sm leading-relaxed text-[#b9ab94] sm:text-base">
                                    Browse a live preview from the catalog, then jump between exact title lookup, hybrid intent search, or visual discovery without leaving this route.
                                </p>
                                <div className="mt-6 grid gap-3">
                                    <div className="rounded-[1.4rem] border border-white/[0.08] bg-black/[0.18] p-4">
                                        <div className="eyebrow">Mode 01</div>
                                        <h4 className="mt-2 text-xl font-semibold text-[#f8f1e5]">Title</h4>
                                        <p className="mt-2 text-sm leading-relaxed text-[#b9ab94]">
                                            Fast metadata lookup for direct catalog navigation.
                                        </p>
                                    </div>
                                    <div className="rounded-[1.4rem] border border-white/[0.08] bg-black/[0.18] p-4">
                                        <div className="eyebrow">Mode 02</div>
                                        <h4 className="mt-2 text-xl font-semibold text-[#f8f1e5]">Hybrid</h4>
                                        <p className="mt-2 text-sm leading-relaxed text-[#b9ab94]">
                                            Better when you know the feeling, tone, or ending but not the title.
                                        </p>
                                    </div>
                                    <div className="rounded-[1.4rem] border border-white/[0.08] bg-black/[0.18] p-4">
                                        <div className="eyebrow">Mode 03</div>
                                        <h4 className="mt-2 text-xl font-semibold text-[#f8f1e5]">Visual</h4>
                                        <p className="mt-2 text-sm leading-relaxed text-[#b9ab94]">
                                            Search from imagery, palette, texture, or scene composition cues.
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    ) : null}
                </section>
            </div>
        </main>
    );
}
